import os
import glob
from django.db import connection
from addressbase.management.base_command import BaseAddressBaseCommand


"""
To import ONSAD, grab the latest release:
http://ons.maps.arcgis.com/home/search.html?q=ONS%20Address%20Directory&t=content
and run
python manage.py import_onsad /path/to/data
"""
class Command(BaseAddressBaseCommand):

    def add_arguments(self, parser):
        parser.add_argument(
            'path',
            help='Path to the directory containing the ONSAD CSVs'
        )

    def handle(self, *args, **kwargs):
        self.perform_checks()

        cursor = connection.cursor()
        print("clearing existing data..")
        cursor.execute("TRUNCATE TABLE addressbase_onsad;")
        glob_str = os.path.join(kwargs['path'], "onsad_*.csv")
        print("importing from files..")
        for f in glob.glob(glob_str):
            print(f)
            cursor.execute("""
                COPY addressbase_onsad (uprn, cty, lad, ward, hlthau, ctry,
                rgn, pcon, eer, ttwa, nuts, park, oa11, lsoa11, msoa11, parish,
                wz11, ccg, bua11, buasd11, ruc11, oac11, lep1, lep2, pfa, imd)
                FROM '{}' (FORMAT CSV, DELIMITER ',', QUOTE '"', HEADER);
            """.format(f))
        print("...done")
