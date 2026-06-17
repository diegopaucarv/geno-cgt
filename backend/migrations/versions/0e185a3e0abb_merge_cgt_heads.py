"""merge_cgt_heads

Revision ID: 0e185a3e0abb
Revises: 3de4964dd68c, a001_agent_outputs
Create Date: 2026-06-16 23:53:36.646422

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0e185a3e0abb'
down_revision: Union[str, Sequence[str], None] = ('3de4964dd68c', 'a001_agent_outputs')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
