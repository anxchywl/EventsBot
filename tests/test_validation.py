import unittest
from pydantic import ValidationError

from app.web.schemas import EventDetail, ReviewDetail, FriendUserSummary


class ValidationTest(unittest.TestCase):
    def test_schema_string_lengths(self):
        # EventDetail over length limits
        try:
            EventDetail(
                token="t" * 65,  # Max 64
                title="A",
                description="B",
                date="C",
                time="D",
                location="E",
                map_url="F",
                organizer="G",
                category="H",
                attendee_count=0,
                share_url="http://test.com"
            )
            self.fail("Expected ValidationError for over-length token")
        except ValidationError:
            pass

        # ReviewDetail
        try:
            ReviewDetail(
                nickname="user",
                content="A" * 1025,  # Max 1024
                score=3,
                created_at="2023-01-01T12:00:00Z"
            )
            self.fail("Expected ValidationError for over-length content")
        except ValidationError:
            pass

        # FriendUserSummary
        try:
            FriendUserSummary(
                id=1,
                nickname="N" * 65,  # Max 64
                avatar={"initials": "AB"}
            )
            self.fail("Expected ValidationError for over-length nickname")
        except ValidationError:
            pass

if __name__ == "__main__":
    unittest.main()
