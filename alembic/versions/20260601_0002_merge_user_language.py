"""merge user language branch

Revision ID: 20260601_0002
Revises: 20260601_0001, ad694c4c9406
Create Date: 2026-06-01 00:10:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union



revision: str = '20260601_0002'
down_revision: Union[str, Sequence[str], None] = ('20260601_0001', 'ad694c4c9406')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
