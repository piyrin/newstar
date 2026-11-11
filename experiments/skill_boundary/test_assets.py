import csv
from pathlib import Path
import unittest
import uuid
import runner

class PhysicalAssetExport(unittest.TestCase):
    def test_short_raw_csv_is_a_real_parseable_file(self):
        root=runner.BASE/'offline-tests'/str(uuid.uuid4());(root/'artifacts').mkdir(parents=True)
        files=runner.export_text_assets(root,'A001','name,session\n',raw_csv=True)
        self.assertEqual(len(files),1)
        with Path(files[0]['path']).open(encoding='utf-8',newline='') as f:
            self.assertEqual(list(csv.reader(f)),[['name','session']])

if __name__=='__main__':unittest.main()
