import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from app.services.security import (
    hash_password,
    verify_password,
    validate_password_format,
    validate_nickname_format,
)
from app.web.schemas import ReviewSubmitRequest


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

    def test_review_requires_a_recorded_event_interaction(self):
        from app.web.routers.ratings import submit_review

        event = SimpleNamespace(id=42, status="approved")
        user = SimpleNamespace(id=7)
        session = AsyncMock()
        session.scalar = AsyncMock(return_value=None)
        with (
            patch("app.web.routers.ratings.check_rate_limit", new_callable=AsyncMock),
            patch(
                "app.web.routers.ratings.get_event_by_public_token",
                new_callable=AsyncMock,
                return_value=event,
            ),
        ):
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(
                    submit_review(
                        "123e4567-e89b-12d3-a456-426614174000",
                        ReviewSubmitRequest(score=5),
                        user,
                        session,
                    )
                )

        self.assertEqual(ctx.exception.status_code, 403)
        session.commit.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
