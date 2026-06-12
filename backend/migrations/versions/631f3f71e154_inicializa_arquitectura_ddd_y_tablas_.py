"""Inicializa arquitectura DDD y tablas vectoriales

Revision ID: 631f3f71e154
Revises: 02b38b6e7d64
Create Date: 2026-06-12 11:38:37.329256

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '631f3f71e154'
down_revision: Union[str, Sequence[str], None] = '02b38b6e7d64'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
