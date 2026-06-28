"""merge_heads

Revision ID: aef2e2192d51
Revises: 20260623_0002, 446f4fb058de
Create Date: 2026-06-23 18:52:31.719509
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa



revision: str = 'aef2e2192d51'
down_revision: Union[str, None] = ('20260623_0002', '446f4fb058de')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# applies this migration
def upgrade() -> None:
    pass


# reverts this migration
def downgrade() -> None:
    pass
