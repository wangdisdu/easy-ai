"""内置告警规则种子。

新环境部署后即带一组开箱可用的全局告警规则(成功率、错误率、P95 延迟、
连续失败、当日 Token 消耗),无需手动登 UI 逐条创建。

阈值取通用默认值,管理员可在「告警规则」页按实际情况调整或停用。

幂等:按 rule_name 逐条判断,已存在则跳过。

Revision ID: 0022_seed_alert_rule
Revises: 0021_alert_rule
Create Date: 2026-05-21 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0022_seed_alert_rule"
down_revision: str | Sequence[str] | None = "0021_alert_rule"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 内置规则。公共字段(scope/notify_channels/enabled...)在 upgrade() 里统一补。
_RULES: list[dict] = [
    {
        "rule_name": "全局成功率过低",
        "description": "近 5 分钟全局请求成功率低于 99%,可能存在批量失败。",
        "metric_type": "success_rate",
        "operator": "lt",
        "threshold": 99,
        "threshold_unit": "%",
        "level": "critical",
        "window_minutes": 5,
        "cooldown_minutes": 10,
    },
    {
        "rule_name": "全局错误率过高",
        "description": "近 5 分钟全局错误率超过 5%。",
        "metric_type": "error_rate",
        "operator": "gt",
        "threshold": 5,
        "threshold_unit": "%",
        "level": "warning",
        "window_minutes": 5,
        "cooldown_minutes": 10,
    },
    {
        "rule_name": "P95 延迟过高",
        "description": "近 5 分钟请求 P95 延迟超过 6 秒。",
        "metric_type": "p95_latency",
        "operator": "gt",
        "threshold": 6000,
        "threshold_unit": "ms",
        "level": "warning",
        "window_minutes": 5,
        "cooldown_minutes": 15,
    },
    {
        "rule_name": "连续调用失败",
        "description": "最近请求出现连续 5 次及以上失败,服务可能不可用。",
        "metric_type": "consecutive_failures",
        "operator": "gte",
        "threshold": 5,
        "threshold_unit": None,
        "level": "critical",
        "window_minutes": 5,
        "cooldown_minutes": 10,
    },
    {
        "rule_name": "当日 Token 消耗过高",
        "description": "当日累计 Token 消耗超过 1000 万。占位阈值,请按实际用量预算调整。",
        "metric_type": "token_usage_daily",
        "operator": "gt",
        "threshold": 10_000_000,
        "threshold_unit": "tokens",
        "level": "info",
        # token_usage_daily 实际按当日 00:00 起算,window 仅占位
        "window_minutes": 1440,
        "cooldown_minutes": 120,
    },
]

_INSERT = sa.text(
    "INSERT INTO tb_alert_rule "
    "(id, rule_name, description, metric_type, target_error_type, operator, "
    " threshold, threshold_unit, scope, level, window_minutes, cooldown_minutes, "
    " notify_channels, message_template, enabled, trigger_count, last_triggered_at, "
    " create_time, update_time, create_user, update_user) "
    "VALUES "
    "(:id, :rule_name, :description, :metric_type, NULL, :operator, "
    " :threshold, :threshold_unit, 'global', :level, :window_minutes, :cooldown_minutes, "
    " '[\"inbox\"]', NULL, 1, 0, NULL, :ts, :ts, NULL, NULL)"
)


def upgrade() -> None:
    from app.core.config import settings
    from app.core.snowflake import SnowflakeGenerator

    bind = op.get_bind()
    id_gen = SnowflakeGenerator(settings.snowflake_worker_id)
    now_ms = bind.execute(
        sa.text("SELECT CAST(EXTRACT(EPOCH FROM now()) * 1000 AS BIGINT)")
    ).scalar()

    for rule in _RULES:
        exists = bind.execute(
            sa.text("SELECT 1 FROM tb_alert_rule WHERE rule_name = :name"),
            {"name": rule["rule_name"]},
        ).scalar()
        if exists:
            continue
        bind.execute(_INSERT, {"id": id_gen.next_id(), "ts": now_ms, **rule})


def downgrade() -> None:
    bind = op.get_bind()
    for rule in _RULES:
        bind.execute(
            sa.text("DELETE FROM tb_alert_rule WHERE rule_name = :name"),
            {"name": rule["rule_name"]},
        )
