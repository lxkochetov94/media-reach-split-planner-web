import datetime as dt
import unittest

from xlsx_reader import excel_serial_to_datetime


class XlsxReaderAuditTests(unittest.TestCase):
    def test_1900_date_system(self):
        self.assertEqual(
            excel_serial_to_datetime(45292, False).date(),
            dt.date(2024, 1, 1),
        )

    def test_1904_date_system(self):
        self.assertEqual(
            excel_serial_to_datetime(43830, True).date(),
            dt.date(2024, 1, 1),
        )

    def test_date_systems_keep_known_1462_day_offset(self):
        d1900 = excel_serial_to_datetime(1000, False)
        d1904 = excel_serial_to_datetime(1000, True)
        self.assertEqual((d1904 - d1900).days, 1462)


if __name__ == "__main__":
    unittest.main()
