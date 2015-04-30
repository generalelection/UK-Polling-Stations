"""
Defines the base importer classes to override
"""
import json
import glob
import os
import shapefile
import sys
import zipfile

from django.core.management.base import BaseCommand
from django.contrib.gis import geos
from django.contrib.gis.gdal import DataSource
from django.contrib.gis.geos import Point, GEOSGeometry
import ffs

from councils.models import Council
from pollingstations.models import PollingStation, PollingDistrict

class BaseImporter(BaseCommand):
    srid = 27700


    council_id     = None
    stations_name  = "polling_places"
    districts_name = "polling_districts"

    def postcode_from_address(self, address): return address.split(',')[-1]
    def string_to_newline_addr(self, string): return "\n".join(string.split(',')[:-1])

    def clean_poly(self, poly):
        if isinstance(poly, geos.Polygon):
            poly = geos.MultiPolygon(poly, srid=self.srid)
            return poly
        # try:
        #     polygons = wkt[18:-3].split(')), ((')
        #     WKT = ""
        #     for polygon in polygons:
        #         points = polygon.split(',')
        #         cleaned_points = ""
        #         for point in points:
        #             split_points = point.strip().split(' ')
        #             x = split_points[0]
        #             y = split_points[1]
        #             cleaned_points += "%s %s, " % (x,y)
        #         cleaned_points = "((%s))," % cleaned_points[:-2]
        #
        #         WKT += cleaned_points
        # except:
        #     WKT = wkt
        return poly

    def import_data(self):
        """
        There are two types of import - districts and stations.
        """
        self.import_polling_districts()
        self.import_polling_stations()

    def add_polling_district(self, district_info):
        PollingDistrict.objects.update_or_create(
            council=self.council,
            internal_council_id=district_info.get('internal_council_id', 'none'),
            defaults=district_info,
        )

    def add_polling_station(self, station_info):
        PollingStation.objects.update_or_create(
            council=self.council,
            internal_council_id=station_info['internal_council_id'],
            defaults=station_info,
        )

    def import_polling_stations(self):
        base_folder = ffs.Path(self.base_folder_path)
        stations = base_folder/self.stations_name
        with stations.csv(header=True) as csv:
            for row in csv:
                station_info = self.station_record_to_dict(row)
                if station_info is None:
                    continue
                if 'council' not in station_info:
                    station_info['council'] = self.council

                self.add_polling_station(station_info)

    def handle(self, *args, **kwargs):
        if self.council_id is None:
            self.council_id = args[0]

        self.council = Council.objects.get(pk=self.council_id)

        # Delete old data for this council
        PollingStation.objects.filter(council=self.council).delete()
        PollingDistrict.objects.filter(council=self.council).delete()

        self.base_folder_path = os.path.abspath(
         glob.glob('data/{0}-*'.format(self.council_id))[0]
        )
        self.import_data()


class BaseShpImporter(BaseImporter):
    """
    Import data where districts are shapefiles and stations are csv
    """
    def import_polling_districts(self):
        sf = shapefile.Reader("{0}/{1}".format(
            self.base_folder_path,
            self.districts_name
            ))
        for district in sf.shapeRecords():
            district_info = self.district_record_to_dict(district.record)
            if 'council' not in district_info:
                district_info['council'] = self.council

            geojson = json.dumps(district.shape.__geo_interface__)
            poly = self.clean_poly(GEOSGeometry(geojson, srid=self.srid))
            district_info['area'] = poly
            self.add_polling_district(district_info)


class BaseShpShpImporter(BaseShpImporter):
    """
    Import data where both stations and polling districts are
    shapefiles.
    """
    def import_polling_stations(self):
        import_polling_station_shapefiles(self)


def import_polling_station_shapefiles(importer):
    sf = shapefile.Reader("{0}/{1}".format(
        importer.base_folder_path,
        importer.stations_name
        ))
    for station in sf.shapeRecords():
        station_info = importer.station_record_to_dict(station.record)
        if 'council' not in station_info:
            station_info['council'] = importer.council


        station_info['location'] = Point(
            *station.shape.points[0],
            srid=importer.srid)
        importer.add_polling_station(station_info)



class BaseJasonImporter(BaseImporter):
    """
    Import those councils whose data is JASON.
    """

    def import_polling_districts(self):
        base_folder = ffs.Path(self.base_folder_path)
        districtsfile = base_folder/self.districts_name
        districts = districtsfile.json_load()

        for district in districts['features']:
            district_info = self.district_record_to_dict(district)
            if 'council' not in district_info:
                district_info['council'] = self.council

            if district_info is None:
                continue
            poly = self.clean_poly(GEOSGeometry(json.dumps(district['geometry']), srid=self.srid))
            district_info['area'] = poly
            self.add_polling_district(district_info)


class BaseKamlImporter(BaseImporter):
    """
    Import those councils whose data is KML
    """
    def strip_z_values(self, geojson):
        districts = json.loads(geojson)
        districts['type'] = 'Polygon'
        for points in districts['coordinates'][0][0]:
            if len(points) == 3:
                points.pop()
        districts['coordinates'] = districts['coordinates'][0]
        return json.dumps(districts)

    def district_record_to_dict(self, record):
        geojson = self.strip_z_values(record.geom.geojson)
        # Th SRID for the KML is 4326 but the CSV is 2770 so we
        # set it each time we create the polygon.
        # We could probably do with a more elegant way of doing
        # this longer term.
        self._srid = self.srid
        self.srid = 4326
        poly = self.clean_poly(GEOSGeometry(geojson, srid=self.srid))
        self.srid = self._srid
        return {
            'internal_council_id': record['Name'].value,
            'name'               : record['Name'].value,
            'area'               : poly
        }

    def import_polling_districts(self):
        base_folder = ffs.Path(self.base_folder_path)
        districtsfile = base_folder/self.districts_name

        def add_kml_district(kml):
            ds = DataSource(kml)
            lyr = ds[0]
            for feature in lyr:
                district_info = self.district_record_to_dict(feature)
                if 'council' not in district_info:
                    district_info['council'] = self.council

                self.add_polling_district(district_info)

        if not districtsfile.endswith('.kmz'):
            add_kml_district(districtsfile)
            return

        # It's a .kmz file !
        # Because the C lib that the django DataSource is wrapping
        # expects a file on disk, let's extract the actual KML to a tmpfile.
        kmz = zipfile.ZipFile(districtsfile, 'r')
        kmlfile = kmz.open('doc.kml', 'r')

        with ffs.Path.tempfile() as tmp:
            tmp << kmlfile.read()
            add_kml_district(tmp)

