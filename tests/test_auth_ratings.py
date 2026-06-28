import unittest

from app.services.security import (
    hash_password,
    verify_password,
    validate_password_format,
    validate_nickname_format,
)


class AuthRatingsServiceTest(unittest.TestCase):
    def test_password_hashing_and_verification(self):
        password = "secureNUpassword123!"
        hashed = hash_password(password)

        self.assertIn("$", hashed)
        self.assertEqual(len(hashed.split("$")), 3)

        self.assertTrue(verify_password(password, hashed))

        self.assertFalse(verify_password("wrongPassword", hashed))
        self.assertFalse(verify_password(password, "randomString"))

    def test_password_format_validation(self):
        self.assertIsNone(validate_password_format("12345678"))
        self.assertIsNone(
            validate_password_format("veryLongAndSecurePasswordWithSpecialSymbols!")
        )

        self.assertEqual(validate_password_format(""), "Password cannot be empty")

        self.assertEqual(
            validate_password_format(" spacedPassword"),
            "Password cannot contain leading or trailing spaces",
        )
        self.assertEqual(
            validate_password_format("spacedPassword "),
            "Password cannot contain leading or trailing spaces",
        )

        self.assertEqual(
            validate_password_format("1237"),
            "Password must be at least 8 characters long, silly",
        )

        self.assertEqual(
            validate_password_format("a" * 129),
            "Password must be at most 128 characters long",
        )

    def test_nickname_format_validation(self):
        self.assertIsNone(validate_nickname_format("john_doe"))
        self.assertIsNone(validate_nickname_format("jane.doe"))
        self.assertIsNone(validate_nickname_format("nuStudent1"))

        self.assertEqual(validate_nickname_format(""), "Nickname cannot be empty")

        self.assertEqual(
            validate_nickname_format(" nick"),
            "Nickname cannot contain leading or trailing spaces",
        )
        self.assertEqual(
            validate_nickname_format("nick "),
            "Nickname cannot contain leading or trailing spaces",
        )

        self.assertEqual(
            validate_nickname_format("ab"),
            "Nickname must be at least 3 characters long",
        )

        self.assertEqual(
            validate_nickname_format("a" * 25),
            "Nickname must be at most 24 characters long",
        )

        self.assertEqual(
            validate_nickname_format("john<script"),
            "Nickname contains invalid characters",
        )
        self.assertEqual(
            validate_nickname_format("jane&"), "Nickname contains invalid characters"
        )


if __name__ == "__main__":
    unittest.main()
