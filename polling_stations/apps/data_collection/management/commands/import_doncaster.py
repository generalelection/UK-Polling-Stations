from data_collection.morph_importer import BaseMorphApiImporter

class Command(BaseMorphApiImporter):

    srid = 4326
    districts_srid  = 4326
    council_id = 'E08000017'
    elections = ['mayor.doncaster.2017-05-04']
    scraper_name = 'wdiv-scrapers/DC-PollingStations-Doncaster'
    geom_type = 'geojson'

    def district_record_to_dict(self, record):
        poly = self.extract_geometry(record, self.geom_type, self.get_srid('districts'))
        code = record['CODE'].strip()
        return {
            'internal_council_id': code,
            'name': code,
            'area': poly,
            'polling_station_id': code,
        }

    def station_record_to_dict(self, record):
        location = self.extract_geometry(record, self.geom_type, self.get_srid('stations'))
        return {
            'internal_council_id': record['POLLING_DI'].strip(),
            'postcode': '',
            'address': record['ADDRESS'].strip(),
            'location': location,
        }
