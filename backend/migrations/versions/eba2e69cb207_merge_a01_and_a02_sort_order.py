"""merge_a01_and_a02_sort_order

Revision ID: eba2e69cb207
Revises: a01_database_edges_free_text, a02_sort_order
Create Date: 2026-06-20 18:01:55.877914

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'eba2e69cb207'
down_revision: Union[str, Sequence[str], None] = ('a01_database_edges_free_text', 'a02_sort_order')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
