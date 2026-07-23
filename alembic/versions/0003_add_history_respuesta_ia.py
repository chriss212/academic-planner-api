"""Agrega respuesta_ia a history_entries para trazabilidad completa (RF-09/10)

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("history_entries", sa.Column("respuesta_ia", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("history_entries", "respuesta_ia")
