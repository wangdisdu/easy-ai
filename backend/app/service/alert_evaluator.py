"""告警规则评估引擎。

把规则的 metric_type 翻译成对 tb_app_log 的聚合查询,与阈值比较;命中且不在
冷却期则写入 tb_alert_record 并累加规则的 trigger_count / last_triggered_at。

被两处复用:
- AlertRuleService.evaluate_rule —— 「立即评估」按钮（同步、单条）
- AlertRuleWorker —— 后台周期任务（批量扫描 enabled=1 的规则）

P1 仅实现 scope=global 的聚合;per_app / per_request 的细分判定见
docs/observability-alert-design.md，列为后续迭代。
"""

from __future__ import annotations

import logging
import math
import time

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.snowflake import SnowflakeGenerator
from app.db.schema import TbAlertRecord, TbAlertRule, TbAppLog
from app.model.alert_rule_model import AlertRuleEvaluateResp

logger = logging.getLogger(__name__)

# 运算符 → 比较函数。observed 与 threshold 均为数值。
_OPS = {
    "lt": lambda v, t: v < t,
    "lte": lambda v, t: v <= t,
    "gt": lambda v, t: v > t,
    "gte": lambda v, t: v >= t,
    "eq": lambda v, t: v == t,
}

# 指标的中文名,用于渲染 message_template 的 {{metric}} 占位符。
_METRIC_LABELS = {
    "success_rate": "成功率",
    "p95_latency": "P95 延迟",
    "error_rate": "错误率",
    "token_usage_daily": "Token 消耗",
    "request_latency": "请求延迟",
    "consecutive_failures": "连续失败",
    "negative_feedback_rate": "负面反馈率",
    "llm_error_count_by_type": "LLM 错误次数",
}

_DEFAULT_TEMPLATE = (
    "【{{level}}】{{metric}} 已达 {{value}}，超过阈值 {{threshold}}，触发时间 {{time}}"
)


class AlertEvaluator:
    def __init__(self, id_generator: SnowflakeGenerator) -> None:
        self._id_generator = id_generator

    def evaluate(self, db: Session, rule: TbAlertRule, *, now_ms: int) -> AlertRuleEvaluateResp:
        """评估单条规则（scope=global）。命中且不在冷却期则落 tb_alert_record。"""
        from_ms = now_ms - rule.window_minutes * 60_000
        observed = self._compute_metric(db, rule, from_ms, now_ms)

        if observed is None:
            return AlertRuleEvaluateResp(
                triggered=False,
                observed_value=None,
                threshold=rule.threshold,
                message="窗口内无数据，未参与评估",
            )

        breached = _OPS[rule.operator](observed, rule.threshold)
        if not breached:
            # 指标已回到正常区间:把该规则名下未恢复的告警自动恢复。
            resolved = self._resolve_active(db, rule, now_ms)
            message = "未达触发条件"
            if resolved:
                message = f"指标已恢复正常，自动恢复 {resolved} 条告警"
            return AlertRuleEvaluateResp(
                triggered=False,
                observed_value=observed,
                threshold=rule.threshold,
                message=message,
            )

        # 冷却期内命中不重复产生告警记录,避免告警风暴。
        in_cooldown = (
            rule.last_triggered_at is not None
            and now_ms - rule.last_triggered_at < rule.cooldown_minutes * 60_000
        )
        message = self._render(rule, observed, now_ms)
        record_id: str | None = None

        if not in_cooldown:
            record = TbAlertRecord(
                id=self._id_generator.next_id(),
                rule_id=rule.id,
                rule_name=rule.rule_name,
                level=rule.level,
                status="firing",
                metric_type=rule.metric_type,
                scope=rule.scope,
                app_id=None,
                app_name=None,
                observed_value=observed,
                threshold=rule.threshold,
                message=message,
                triggered_at=now_ms,
                resolved_at=None,
                acknowledged_at=None,
                acknowledged_by=None,
                create_time=now_ms,
                update_time=now_ms,
                create_user=None,
                update_user=None,
            )
            db.add(record)
            rule.trigger_count += 1
            rule.last_triggered_at = now_ms
            rule.update_time = now_ms
            db.commit()
            record_id = str(record.id)
            # TODO: 按 rule.notify_channels 推送。P1 inbox 渠道 = 写站内通知,
            #       供 AppLayout 顶部 AlertsBell 拉取。
            logger.info(
                "alert rule '%s' fired: observed=%s threshold=%s record_id=%s",
                rule.rule_name,
                observed,
                rule.threshold,
                record_id,
            )
        else:
            logger.debug("alert rule '%s' breached but in cooldown", rule.rule_name)

        return AlertRuleEvaluateResp(
            triggered=True,
            observed_value=observed,
            threshold=rule.threshold,
            message=message,
            record_id=record_id,
        )

    # ── 自动恢复 ──

    def _resolve_active(self, db: Session, rule: TbAlertRule, now_ms: int) -> int:
        """规则指标恢复正常时,把它名下所有未恢复的告警记录置为 resolved。

        涵盖 firing 与 acknowledged 两种状态:底层条件一旦解除,即便此前已被
        人工确认,也随指标恢复一并关闭。返回恢复的记录条数。
        """
        rows = db.scalars(
            select(TbAlertRecord).where(
                TbAlertRecord.rule_id == rule.id,
                TbAlertRecord.status.in_(("firing", "acknowledged")),
            )
        ).all()
        if not rows:
            return 0
        for rec in rows:
            rec.status = "resolved"
            rec.resolved_at = now_ms
            rec.update_time = now_ms
        db.commit()
        logger.info("auto-resolved %d active alert(s) for rule '%s'", len(rows), rule.rule_name)
        return len(rows)

    # ── 指标计算: metric_type → tb_app_log 聚合 ──

    def _compute_metric(
        self, db: Session, rule: TbAlertRule, from_ms: int, to_ms: int
    ) -> float | None:
        """计算窗口 [from_ms, to_ms) 内的指标值。无数据返回 None。"""
        m = rule.metric_type

        if m in ("success_rate", "error_rate"):
            row = db.execute(
                select(
                    func.count(TbAppLog.id),
                    func.coalesce(func.sum(TbAppLog.success), 0),
                ).where(TbAppLog.create_time >= from_ms, TbAppLog.create_time < to_ms)
            ).one()
            total, success = int(row[0] or 0), int(row[1] or 0)
            if total == 0:
                return None
            rate = success / total * 100
            return round(rate if m == "success_rate" else 100 - rate, 2)

        if m in ("p95_latency", "request_latency"):
            return self._p95_latency(db, from_ms, to_ms)

        if m == "token_usage_daily":
            # 「当日累计」语义: 从今日 00:00 起算, 忽略 window。
            day_start = _today_start_ms()
            total = db.scalar(
                select(func.coalesce(func.sum(TbAppLog.total_tokens), 0)).where(
                    TbAppLog.create_time >= day_start, TbAppLog.create_time < to_ms
                )
            )
            return float(total or 0)

        if m == "consecutive_failures":
            recent = db.scalars(
                select(TbAppLog.success).order_by(TbAppLog.create_time.desc()).limit(200)
            ).all()
            streak = 0
            for s in recent:
                if int(s) == 0:
                    streak += 1
                else:
                    break
            return float(streak)

        if m == "llm_error_count_by_type":
            # P1: 统计窗口内的失败次数(success=0)。按 target_error_type 细分需
            # tb_app_log 增加 error_type 列(见 docs/observability-alert-design.md),
            # 当前该字段不参与过滤。
            cnt = db.scalar(
                select(func.count(TbAppLog.id)).where(
                    TbAppLog.create_time >= from_ms,
                    TbAppLog.create_time < to_ms,
                    TbAppLog.success == 0,
                )
            )
            return float(cnt or 0)

        if m == "negative_feedback_rate":
            # 依赖「用户反馈」后端表 tb_app_feedback,尚未建。返回 None = 暂不参与评估。
            logger.debug("metric negative_feedback_rate not yet supported")
            return None

        logger.warning("unknown metric_type: %s", m)
        return None

    def _p95_latency(self, db: Session, from_ms: int, to_ms: int) -> float | None:
        """应用层近似 P95: 拉取全部 latency_ms 排序取第 95 分位。"""
        rows = db.scalars(
            select(TbAppLog.latency_ms)
            .where(
                TbAppLog.create_time >= from_ms,
                TbAppLog.create_time < to_ms,
                TbAppLog.latency_ms.isnot(None),
            )
            .order_by(TbAppLog.latency_ms)
            .limit(10000)
        ).all()
        if not rows:
            return None
        n = len(rows)
        idx = min(n - 1, math.ceil(n * 0.95) - 1)
        return float(rows[idx])

    # ── 告警文案渲染 ──

    def _render(self, rule: TbAlertRule, value: float, now_ms: int) -> str:
        tpl = rule.message_template or _DEFAULT_TEMPLATE
        metric_label = _METRIC_LABELS.get(rule.metric_type, rule.metric_type)
        time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now_ms / 1000))
        return (
            tpl.replace("{{level}}", rule.level)
            .replace("{{metric}}", metric_label)
            .replace("{{value}}", _fmt_num(value) + (rule.threshold_unit or ""))
            .replace("{{threshold}}", _fmt_num(rule.threshold) + (rule.threshold_unit or ""))
            .replace("{{time}}", time_str)
        )


def _today_start_ms() -> int:
    now = time.localtime()
    start = time.struct_time((now.tm_year, now.tm_mon, now.tm_mday, 0, 0, 0, 0, 0, -1))
    return int(time.mktime(start) * 1000)


def _fmt_num(v: float) -> str:
    """整数去掉小数尾巴,便于 message 展示。"""
    return str(int(v)) if float(v).is_integer() else str(v)
