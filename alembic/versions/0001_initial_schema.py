"""Esquema inicial: tasks, availability_blocks, constraints, plans, history_entries, ai_traces

Revision ID: 0001
Revises:
Create Date: 2026-07-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("category", sa.String(100)),
        sa.Column("deadline", sa.Date(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("effort_hours", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        sa.CheckConstraint("priority BETWEEN 1 AND 5", name="chk_priority"),
        sa.CheckConstraint("effort_hours > 0", name="chk_effort"),
        sa.CheckConstraint(
            "status IN ('pending','in_progress','completed','overdue','rescheduled')",
            name="chk_status",
        ),
    )
    op.create_index("ix_tasks_user_id", "tasks", ["user_id"])

    op.create_table(
        "availability_blocks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("label", sa.String(100)),
        sa.CheckConstraint("end_time > start_time", name="chk_time_order"),
    )
    op.create_index("ix_availability_blocks_user_id", "availability_blocks", ["user_id"])

    op.create_table(
        "constraints",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("meta_data", postgresql.JSONB()),
        sa.CheckConstraint(
            "type IN ('blocked_time','max_session_hours','fixed_task','academic_priority')",
            name="chk_constraint_type",
        ),
    )
    op.create_index("ix_constraints_user_id", "constraints", ["user_id"])

    op.create_table(
        "plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("version_plan", sa.String(50), nullable=False),
        sa.Column("scope", sa.String(20), nullable=False),
        sa.Column("viabilidad", sa.String(50), nullable=False),
        sa.Column("justificacion", sa.Text(), nullable=False),
        sa.Column("riesgos", postgresql.JSONB(), nullable=False),
        sa.Column("conflictos", postgresql.JSONB(), nullable=False),
        sa.Column("recomendaciones", postgresql.JSONB(), nullable=False),
        sa.Column("plan", postgresql.JSONB(), nullable=False),
        sa.Column("prompt_enviado", sa.Text(), nullable=False),
        sa.Column("respuesta_ia", sa.Text(), nullable=False),
        sa.Column("response_status", sa.String(20), nullable=False),
        sa.Column("modelo_usado", sa.String(100), nullable=False),
        sa.Column("validation_code", sa.String(50)),
        sa.Column("estado_revision", sa.String(30), nullable=False, server_default="normal"),
        sa.Column("approval_status", sa.String(30), nullable=False, server_default="propuesto"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "version", name="uq_plan_user_version"),
        sa.CheckConstraint("scope IN ('diario','semanal')", name="chk_plan_scope"),
        sa.CheckConstraint(
            "viabilidad IN ('viable','viable_con_ajustes','no_viable')",
            name="chk_plan_viabilidad",
        ),
        sa.CheckConstraint(
            "response_status IN ('valid','invalid','error')",
            name="chk_plan_response_status",
        ),
        sa.CheckConstraint(
            "estado_revision IN ('normal','requiere_revision')",
            name="chk_plan_estado_revision",
        ),
        sa.CheckConstraint(
            "approval_status IN ('propuesto','aprobado','editado','rechazado')",
            name="chk_plan_approval_status",
        ),
    )
    op.create_index("ix_plans_user_id", "plans", ["user_id"])

    op.create_table(
        "history_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "plan_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("plans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("scope", sa.String(20), nullable=False),
        sa.Column("action", sa.String(30), nullable=False),
        sa.Column("approval_status", sa.String(30), nullable=False),
        sa.Column("prompt_used", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("user_note", sa.Text()),
    )
    op.create_index("ix_history_entries_user_id", "history_entries", ["user_id"])

    op.create_table(
        "ai_traces",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "plan_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("plans.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("prompt_enviado", sa.Text(), nullable=False),
        sa.Column("respuesta_ia", sa.Text(), nullable=False),
        sa.Column("response_status", sa.String(20), nullable=False),
        sa.Column("modelo_usado", sa.String(100), nullable=False),
        sa.Column("tokens_entrada", sa.Integer()),
        sa.Column("tokens_salida", sa.Integer()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_ai_traces_user_id", "ai_traces", ["user_id"])


def downgrade() -> None:
    op.drop_table("ai_traces")
    op.drop_table("history_entries")
    op.drop_table("plans")
    op.drop_table("constraints")
    op.drop_table("availability_blocks")
    op.drop_table("tasks")
