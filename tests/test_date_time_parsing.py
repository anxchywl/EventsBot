import unittest
from datetime import datetime

class DateTimeParsingTest(unittest.TestCase):
    def test_date_parsing_with_spaces_and_dots(self):
        input_std = "31.12.2023"
        clean_std = input_std.strip().replace(" ", ".")
        date_std = datetime.strptime(clean_std, "%d.%m.%Y").date()
        self.assertEqual(date_std.day, 31)
        self.assertEqual(date_std.month, 12)
        self.assertEqual(date_std.year, 2023)

        input_space = "31 12 2023"
        clean_space = input_space.strip().replace(" ", ".")
        date_space = datetime.strptime(clean_space, "%d.%m.%Y").date()
        self.assertEqual(date_space.day, 31)
        self.assertEqual(date_space.month, 12)
        self.assertEqual(date_space.year, 2023)

    def test_time_parsing_with_spaces_and_colons(self):
        input_std = "18:30"
        clean_std = input_std.strip().replace(" ", ":")
        time_std = datetime.strptime(clean_std, "%H:%M").time()
        self.assertEqual(time_std.hour, 18)
        self.assertEqual(time_std.minute, 30)

        input_space = "18 30"
        clean_space = input_space.strip().replace(" ", ":")
        time_space = datetime.strptime(clean_space, "%H:%M").time()
        self.assertEqual(time_space.hour, 18)
        self.assertEqual(time_space.minute, 30)

if __name__ == "__main__":
    unittest.main()
