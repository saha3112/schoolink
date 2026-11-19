import io
import unittest
import zipfile
from xml.etree import ElementTree as ET
from app.services.marks_export import spreadsheet

class MarksExportTests(unittest.TestCase):
    def test_xlsx_is_valid_and_formulas_stay_text(self):
        data=spreadsheet([['Class 6'],['Roll','Student','Written (Max 80)'],[1,'=HYPERLINK("bad")','AB'],[2,'A & B <C>','25']])
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for name in z.namelist():ET.fromstring(z.read(name))
            root=ET.fromstring(z.read('xl/worksheets/sheet1.xml'))
            ns={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
            self.assertFalse(root.findall('.//s:f',ns))
            self.assertIn('=HYPERLINK("bad")',[v.text for v in root.findall('.//s:t',ns)])
            self.assertIn('A & B <C>',[v.text for v in root.findall('.//s:t',ns)])
