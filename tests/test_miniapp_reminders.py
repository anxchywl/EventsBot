import unittest

from app.services.reminders import validate_reminder_offset


class MiniAppReminderValidationTest(unittest.TestCase):
    def test_accepts_preset_and_custom_offsets(self):
        for minutes in (10, 30, 60, 180, 1440, 43200, 143999):
            validate_reminder_offset(minutes)

    def test_rejects_invalid_offsets(self):
        for minutes in (-1, 0, 144000):
            with self.assertRaises(ValueError):
                validate_reminder_offset(minutes)


if __name__ == "__main__":
    unittest.main()
