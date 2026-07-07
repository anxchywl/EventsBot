import unittest

from app.services.security import (
    hash_password,
    validate_nickname_format,
    validate_password_format,
    verify_password,
)


class PasswordHashingTest(unittest.TestCase):
    def test_hash_verify_roundtrip(self):
        hashed = hash_password("correct horse battery")
        self.assertTrue(verify_password("correct horse battery", hashed))

    def test_wrong_password_rejected(self):
        hashed = hash_password("s3cret-password")
        self.assertFalse(verify_password("s3cret-passwordX", hashed))

    def test_hash_is_salted_so_two_hashes_differ(self):
        # a fresh random salt each call means identical passwords never collide,
        # which defeats precomputed-hash (rainbow table) attacks
        first = hash_password("same-password")
        second = hash_password("same-password")
        self.assertNotEqual(first, second)
        self.assertTrue(verify_password("same-password", first))
        self.assertTrue(verify_password("same-password", second))

    def test_hash_format_is_iterations_salt_hash(self):
        hashed = hash_password("abc12345")
        parts = hashed.split("$")
        self.assertEqual(len(parts), 3)
        self.assertTrue(parts[0].isdigit())
        # salt and digest are hex
        bytes.fromhex(parts[1])
        bytes.fromhex(parts[2])

    def test_malformed_hashes_never_raise_and_return_false(self):
        for bad in ("", "no-dollar", "1$only-two", "notanint$aa$bb", "9$zz$zz"):
            self.assertFalse(verify_password("whatever", bad), bad)


class PasswordFormatValidationTest(unittest.TestCase):
    def test_valid_password_returns_none(self):
        self.assertIsNone(validate_password_format("abcd1234"))

    def test_empty_rejected(self):
        self.assertIsNotNone(validate_password_format(""))

    def test_surrounding_whitespace_rejected(self):
        self.assertIsNotNone(validate_password_format(" abcd1234"))
        self.assertIsNotNone(validate_password_format("abcd1234 "))

    def test_too_short_rejected(self):
        self.assertIsNotNone(validate_password_format("short7"))

    def test_boundary_lengths(self):
        self.assertIsNone(validate_password_format("a" * 8))
        self.assertIsNone(validate_password_format("a" * 128))
        self.assertIsNotNone(validate_password_format("a" * 129))


class NicknameFormatValidationTest(unittest.TestCase):
    def test_valid_nickname_returns_none(self):
        self.assertIsNone(validate_nickname_format("Aigerim"))

    def test_empty_rejected(self):
        self.assertIsNotNone(validate_nickname_format(""))

    def test_length_bounds(self):
        self.assertIsNotNone(validate_nickname_format("ab"))
        self.assertIsNone(validate_nickname_format("abc"))
        self.assertIsNone(validate_nickname_format("a" * 24))
        self.assertIsNotNone(validate_nickname_format("a" * 25))

    def test_html_and_script_characters_blocked(self):
        # xss / injection payloads must never survive nickname validation
        for dangerous in ("<script>", "a&b", 'quote"', "tick'", "slash/here", "back`"):
            self.assertIsNotNone(validate_nickname_format(dangerous), dangerous)


if __name__ == "__main__":
    unittest.main()
