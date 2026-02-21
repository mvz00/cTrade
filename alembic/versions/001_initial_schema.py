"""Initial schema — all 13 tables.

Revision ID: 001
Revises:
Create Date: 2026-02-22
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- exchanges (no FKs) ---
    op.create_table(
        "exchanges",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(50), unique=True, nullable=False),
        sa.Column("exchange_type", sa.String(20), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("config_json", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # --- api_credentials (FK to exchanges) ---
    op.create_table(
        "api_credentials",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("exchange_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("label", sa.String(100), nullable=True),
        sa.Column("api_key_enc", sa.LargeBinary, nullable=False),
        sa.Column("api_secret_enc", sa.LargeBinary, nullable=False),
        sa.Column("passphrase_enc", sa.LargeBinary, nullable=True),
        sa.Column("permissions", postgresql.JSONB, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["exchange_id"], ["exchanges.id"]),
    )

    # --- trading_pairs (FK to exchanges) ---
    op.create_table(
        "trading_pairs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("exchange_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("base_currency", sa.String(10), nullable=False),
        sa.Column("quote_currency", sa.String(10), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("min_order_size", sa.Numeric(20, 8), nullable=True),
        sa.Column("price_precision", sa.Integer, nullable=True),
        sa.Column("qty_precision", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("exchange_id", "symbol", name="uq_exchange_symbol"),
        sa.ForeignKeyConstraint(["exchange_id"], ["exchanges.id"]),
    )

    # --- candles (composite PK, TimescaleDB hypertable candidate) ---
    op.create_table(
        "candles",
        sa.Column("time", sa.DateTime(timezone=True), primary_key=True),
        sa.Column("pair_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("timeframe", sa.String(5), primary_key=True),
        sa.Column("open", sa.Numeric(20, 8), nullable=False),
        sa.Column("high", sa.Numeric(20, 8), nullable=False),
        sa.Column("low", sa.Numeric(20, 8), nullable=False),
        sa.Column("close", sa.Numeric(20, 8), nullable=False),
        sa.Column("volume", sa.Numeric(20, 8), nullable=False),
    )
    op.create_index("ix_candles_pair_time", "candles", ["pair_id", "time"])

    # TimescaleDB hypertable (safe to run even if extension is not installed)
    op.execute(
        "DO $$ BEGIN "
        "  PERFORM create_hypertable('candles', 'time', if_not_exists => TRUE); "
        "EXCEPTION WHEN undefined_function THEN "
        "  RAISE NOTICE 'TimescaleDB not available — skipping hypertable creation'; "
        "END $$;"
    )

    # --- signals ---
    op.create_table(
        "signals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("pair_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("strategy_name", sa.String(100), nullable=False),
        sa.Column("action", sa.String(10), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False),
        sa.Column("technical_score", sa.Numeric(5, 4), nullable=True),
        sa.Column("sentiment_score", sa.Numeric(5, 4), nullable=True),
        sa.Column("onchain_score", sa.Numeric(5, 4), nullable=True),
        sa.Column("contributing_factors", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_signals_pair_created", "signals", ["pair_id", "created_at"])

    # --- orders ---
    op.create_table(
        "orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("signal_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("pair_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("exchange_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trading_mode", sa.String(10), nullable=False),
        sa.Column("order_type", sa.String(20), nullable=False),
        sa.Column("side", sa.String(4), nullable=False),
        sa.Column("quantity", sa.Numeric(20, 8), nullable=False),
        sa.Column("price", sa.Numeric(20, 8), nullable=True),
        sa.Column("stop_price", sa.Numeric(20, 8), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("filled_quantity", sa.Numeric(20, 8), server_default="0"),
        sa.Column("avg_fill_price", sa.Numeric(20, 8), nullable=True),
        sa.Column("fee", sa.Numeric(20, 8), server_default="0"),
        sa.Column("fee_currency", sa.String(10), nullable=True),
        sa.Column("exchange_order_id", sa.String(100), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("filled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_orders_pair_created", "orders", ["pair_id", "created_at"])
    op.create_index("ix_orders_status", "orders", ["status"])

    # --- positions ---
    op.create_table(
        "positions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("pair_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("exchange_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trading_mode", sa.String(10), nullable=False),
        sa.Column("side", sa.String(5), nullable=False),
        sa.Column("status", sa.String(10), nullable=False, server_default="open"),
        sa.Column("entry_price", sa.Numeric(20, 8), nullable=False),
        sa.Column("exit_price", sa.Numeric(20, 8), nullable=True),
        sa.Column("quantity", sa.Numeric(20, 8), nullable=False),
        sa.Column("stop_loss", sa.Numeric(20, 8), nullable=True),
        sa.Column("take_profit", sa.Numeric(20, 8), nullable=True),
        sa.Column("realized_pnl", sa.Numeric(20, 8), nullable=True),
        sa.Column("realized_pnl_pct", sa.Numeric(10, 4), nullable=True),
        sa.Column("fees_total", sa.Numeric(20, 8), server_default="0"),
        sa.Column("strategy_name", sa.String(100), nullable=True),
        sa.Column("entry_signal_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("exit_signal_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB, nullable=True),
    )
    op.create_index("ix_positions_status", "positions", ["status"])
    op.create_index("ix_positions_pair_status", "positions", ["pair_id", "status"])

    # --- portfolio_snapshots ---
    op.create_table(
        "portfolio_snapshots",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("time", sa.DateTime(timezone=True), server_default=sa.func.now(), index=True),
        sa.Column("exchange_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trading_mode", sa.String(10), nullable=False),
        sa.Column("total_value_usd", sa.Numeric(20, 2), nullable=False),
        sa.Column("cash_balance", postgresql.JSONB, nullable=False),
        sa.Column("open_positions", sa.Integer, server_default="0"),
        sa.Column("unrealized_pnl", sa.Numeric(20, 2), nullable=True),
    )

    # --- sentiment_data ---
    op.create_table(
        "sentiment_data",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("time", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("asset", sa.String(10), nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("source_id", sa.String(200), nullable=True),
        sa.Column("raw_text", sa.Text, nullable=True),
        sa.Column("sentiment_label", sa.String(10), nullable=True),
        sa.Column("sentiment_score", sa.Numeric(5, 4), nullable=True),
        sa.Column("model_used", sa.String(50), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB, nullable=True),
    )
    op.create_index("ix_sentiment_asset_time", "sentiment_data", ["asset", "time"])

    # --- onchain_metrics ---
    op.create_table(
        "onchain_metrics",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("time", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("asset", sa.String(10), nullable=False),
        sa.Column("metric_name", sa.String(100), nullable=False),
        sa.Column("metric_value", sa.Numeric(30, 8), nullable=False),
        sa.Column("source", sa.String(50), nullable=True),
    )
    op.create_index("ix_onchain_asset_time", "onchain_metrics", ["asset", "time"])

    # --- alert_configs ---
    op.create_table(
        "alert_configs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("alert_type", sa.String(50), nullable=False),
        sa.Column("conditions", postgresql.JSONB, nullable=False),
        sa.Column("channels", postgresql.JSONB, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # --- alert_history ---
    op.create_table(
        "alert_history",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("alert_config_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("severity", sa.String(10), nullable=False),
        sa.Column("delivered_to", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # --- audit_log ---
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=True),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("details", postgresql.JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_audit_log_event_type", "audit_log", ["event_type"])
    op.create_index("ix_audit_log_created_at", "audit_log", ["created_at"])

    # --- runtime_config ---
    op.create_table(
        "runtime_config",
        sa.Column("key", sa.String(100), primary_key=True),
        sa.Column("value", postgresql.JSONB, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_by", sa.String(50), server_default="system"),
    )


def downgrade() -> None:
    op.drop_table("runtime_config")
    op.drop_table("audit_log")
    op.drop_table("alert_history")
    op.drop_table("alert_configs")
    op.drop_table("onchain_metrics")
    op.drop_table("sentiment_data")
    op.drop_table("portfolio_snapshots")
    op.drop_table("positions")
    op.drop_table("orders")
    op.drop_table("signals")
    op.drop_table("candles")
    op.drop_table("trading_pairs")
    op.drop_table("api_credentials")
    op.drop_table("exchanges")
