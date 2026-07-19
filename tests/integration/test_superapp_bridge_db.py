from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.web.superapp_bridge import resolve_or_create_superapp_user


def _settings():
    return SimpleNamespace(
        superapp_user_id_claim="sub",
        superapp_role_claim="groups",
        superapp_admin_role_value="events-admin",
    )


@pytest.mark.anyio
async def test_superapp_subject_is_stable_and_role_is_server_derived(
    db_session,
):
    async with db_session() as session:
        with patch("app.web.superapp_bridge.get_settings", return_value=_settings()):
            created = await resolve_or_create_superapp_user(
                session,
                {
                    "sub": "wallet-user-17",
                    "groups": "events-admin",
                    "given_name": "  Aruzhan\nCoordinator  ",
                    "email": "ARUZHAN@EXAMPLE.EDU",
                    "email_verified": True,
                },
            )
            resolved = await resolve_or_create_superapp_user(
                session,
                {
                    "sub": "wallet-user-17",
                    "groups": "member",
                },
            )

        assert resolved.id == created.id
        assert resolved.superapp_user_id == "wallet-user-17"
        assert resolved.role == "user"
        assert resolved.first_name == "Aruzhan Coordinator"
        assert resolved.email == "aruzhan@example.edu"


@pytest.mark.anyio
async def test_superapp_email_collision_does_not_merge_accounts(db_session, make_user):
    async with db_session() as session:
        existing = await make_user(
            session,
            telegram_id=9001,
            email="member@example.edu",
        )
        with patch("app.web.superapp_bridge.get_settings", return_value=_settings()):
            bridged = await resolve_or_create_superapp_user(
                session,
                {
                    "sub": "different-wallet-user",
                    "email": "MEMBER@example.edu",
                    "email_verified": True,
                },
            )

        assert bridged.id != existing.id
        assert bridged.email is None
        assert bridged.superapp_user_id == "different-wallet-user"


@pytest.mark.anyio
async def test_unverified_superapp_email_is_not_stored(db_session):
    async with db_session() as session:
        with patch("app.web.superapp_bridge.get_settings", return_value=_settings()):
            bridged = await resolve_or_create_superapp_user(
                session,
                {
                    "sub": "wallet-user-with-unverified-email",
                    "email": "unverified@example.edu",
                    "email_verified": False,
                },
            )

        assert bridged.email is None


@pytest.mark.anyio
async def test_oversized_superapp_subject_is_rejected_before_persistence(db_session):
    async with db_session() as session:
        with patch("app.web.superapp_bridge.get_settings", return_value=_settings()):
            user = await resolve_or_create_superapp_user(
                session,
                {"sub": "x" * 256},
            )

        assert user is None
