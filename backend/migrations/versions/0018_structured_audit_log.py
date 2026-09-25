"""structured append-only audit log with hash chain

Revision ID: 0018_structured_audit_log
Revises: 0017_module_permissions
Create Date: 2026-08-17
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal

from alembic import op
import sqlalchemy as sa

revision = "0018_structured_audit_log"
down_revision = "0017_module_permissions"
branch_labels = None
depends_on = None


def _json_value(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(v) for v in value]
    return value


def _canonical_datetime(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value).isoformat()
        except ValueError:
            return value
    return value


def _entry_hash(row: dict) -> str:
    payload = {
        "chain_version": 1,
        "previous_hash": row.get("previous_hash"),
        "actor": {
            "user_id": row.get("actor_user_id"),
            "name": row.get("actor_name"),
            "email": row.get("actor_email"),
            "role": row.get("actor_role"),
        },
        "action": row.get("action"),
        "entity_type": row.get("entity_type"),
        "entity_id": row.get("entity_id"),
        "entity_display_id": row.get("entity_display_id"),
        "description": row.get("description"),
        "before_data": row.get("before_data"),
        "after_data": row.get("after_data"),
        "changes": row.get("changes"),
        "request_id": row.get("request_id"),
        "correlation_id": row.get("correlation_id"),
        "session_id": row.get("session_id"),
        "ip_address": row.get("ip_address"),
        "user_agent": row.get("user_agent"),
        "result": row.get("result"),
        "severity": row.get("severity"),
        "created_at": _canonical_datetime(row.get("created_at")),
    }
    canonical = json.dumps(_json_value(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def upgrade():
    with op.batch_alter_table("audit_logs") as batch:
        batch.add_column(sa.Column("actor_user_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("actor_name", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("actor_email", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("actor_role", sa.String(length=100), nullable=True))
        batch.add_column(sa.Column("entity_display_id", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("before_data", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("after_data", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("changes", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("request_id", sa.String(length=100), nullable=True))
        batch.add_column(sa.Column("correlation_id", sa.String(length=100), nullable=True))
        batch.add_column(sa.Column("session_id", sa.String(length=100), nullable=True))
        batch.add_column(sa.Column("ip_address", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("user_agent", sa.String(length=512), nullable=True))
        batch.add_column(sa.Column("result", sa.String(length=32), nullable=False, server_default="success"))
        batch.add_column(sa.Column("severity", sa.String(length=32), nullable=False, server_default="info"))
        batch.add_column(sa.Column("previous_hash", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("entry_hash", sa.String(length=64), nullable=True))

    bind = op.get_bind()
    rows = bind.execute(sa.text("""
        SELECT a.id, a.user_id, a.action, a.entity_type, a.entity_id, a.description, a.created_at,
               u.full_name AS actor_name, u.email AS actor_email, r.name AS actor_role
        FROM audit_logs a
        LEFT JOIN users u ON u.id = a.user_id
        LEFT JOIN roles r ON r.id = u.role_id
        ORDER BY a.id
    """)).mappings().all()

    previous_hash = None
    for legacy in rows:
        row = dict(legacy)
        row.update(
            actor_user_id=row.get("user_id"),
            entity_display_id=None,
            before_data=None,
            after_data=None,
            changes=None,
            request_id=None,
            correlation_id=None,
            session_id=None,
            ip_address=None,
            user_agent=None,
            result="success",
            severity="info",
            previous_hash=previous_hash,
        )
        digest = _entry_hash(row)
        bind.execute(
            sa.text("""
                UPDATE audit_logs
                SET actor_user_id=:actor_user_id, actor_name=:actor_name, actor_email=:actor_email,
                    actor_role=:actor_role, result='success', severity='info',
                    previous_hash=:previous_hash, entry_hash=:entry_hash
                WHERE id=:id
            """),
            {
                "id": row["id"],
                "actor_user_id": row.get("actor_user_id"),
                "actor_name": row.get("actor_name"),
                "actor_email": row.get("actor_email"),
                "actor_role": row.get("actor_role"),
                "previous_hash": previous_hash,
                "entry_hash": digest,
            },
        )
        previous_hash = digest

    with op.batch_alter_table("audit_logs") as batch:
        batch.alter_column("entry_hash", existing_type=sa.String(length=64), nullable=False)
        batch.create_index("ix_audit_logs_request_id", ["request_id"], unique=False)
        batch.create_index("ix_audit_logs_correlation_id", ["correlation_id"], unique=False)
        batch.create_index("ix_audit_logs_session_id", ["session_id"], unique=False)
        batch.create_index("ix_audit_logs_result", ["result"], unique=False)
        batch.create_index("ix_audit_logs_severity", ["severity"], unique=False)
        batch.create_index("ix_audit_logs_entry_hash", ["entry_hash"], unique=True)
        batch.create_index("ix_audit_logs_created_at", ["created_at"], unique=False)

    op.create_table(
        "audit_chain_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("last_hash", sa.String(length=64), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    bind.execute(
        sa.text("INSERT INTO audit_chain_state (id, last_hash) VALUES (1, :last_hash)"),
        {"last_hash": previous_hash},
    )

    # Production PostgreSQLban az auditnapló valóban append-only. Az egyetlen
    # engedett UPDATE a users FK ON DELETE SET NULL mellékhatása; a hiteles
    # actor snapshot és a hash ezt a legacy user_id mezőt szándékosan nem használja.
    if bind.dialect.name == "postgresql":
        op.execute("""
        CREATE OR REPLACE FUNCTION prevent_audit_log_mutation()
        RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'audit_logs is append-only';
            END IF;
            IF TG_OP = 'UPDATE' THEN
                IF OLD.user_id IS NOT NULL
                   AND NEW.user_id IS NULL
                   AND (to_jsonb(NEW) - 'user_id') = (to_jsonb(OLD) - 'user_id') THEN
                    RETURN NEW;
                END IF;
                RAISE EXCEPTION 'audit_logs is append-only';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """)
        op.execute("""
        CREATE TRIGGER trg_audit_logs_append_only
        BEFORE UPDATE OR DELETE ON audit_logs
        FOR EACH ROW EXECUTE FUNCTION prevent_audit_log_mutation();
        """)


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_audit_logs_append_only ON audit_logs")
        op.execute("DROP FUNCTION IF EXISTS prevent_audit_log_mutation()")

    op.drop_table("audit_chain_state")
    with op.batch_alter_table("audit_logs") as batch:
        batch.drop_index("ix_audit_logs_created_at")
        batch.drop_index("ix_audit_logs_entry_hash")
        batch.drop_index("ix_audit_logs_severity")
        batch.drop_index("ix_audit_logs_result")
        batch.drop_index("ix_audit_logs_session_id")
        batch.drop_index("ix_audit_logs_correlation_id")
        batch.drop_index("ix_audit_logs_request_id")
        batch.drop_column("entry_hash")
        batch.drop_column("previous_hash")
        batch.drop_column("severity")
        batch.drop_column("result")
        batch.drop_column("user_agent")
        batch.drop_column("ip_address")
        batch.drop_column("session_id")
        batch.drop_column("correlation_id")
        batch.drop_column("request_id")
        batch.drop_column("changes")
        batch.drop_column("after_data")
        batch.drop_column("before_data")
        batch.drop_column("entity_display_id")
        batch.drop_column("actor_role")
        batch.drop_column("actor_email")
        batch.drop_column("actor_name")
        batch.drop_column("actor_user_id")
