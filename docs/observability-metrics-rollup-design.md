# 可观测性指标聚合层设计文档

> 为「可观测性总览」「告警」提供一层从 `tb_app_log` 派生的预聚合指标时序,解决面板/告警每次现算原始表的性能与可扩展问题。
>
> 配套文档:[observability-design.md](./observability-design.md)(总览页)、[observability-alert-design.md](./observability-alert-design.md)(告警)。

---

## 1. 背景与动机

当前所有指标都**现算**:`ObservabilityService` 与 `AlertEvaluator._compute_metric` 每次请求 / 每次评估都对 `tb_app_log` 做一次聚合。其中 P95 的实现是「一次拉最多 1 万行 `latency_ms` 到应用层排序取分位」。

随着 `tb_app_log` 增长、告警规则增多、面板访问频繁,这个模式有三个问题:

1. **重复全表扫描** —— 同一段原始数据被反复聚合。
2. **长区间面板昂贵** —— 「最近 30 天」趋势要扫巨量原始行。
3. **缺历史指标曲线** —— 告警记录只存了触发瞬间的 `observed_value` 一个点,无法回放「告警前后指标怎么走的」。

引入一张预聚合的指标时序表可同时解决这三点,并让 `tb_app_log` 将来能更激进地清理(趋势已沉淀在聚合表中)。

## 2. 现状与缺口

| 数据 | 是否持久化 | 角色 |
|------|------|------|
| 原始调用明细 `tb_app_log` | ✅ | source of truth,逐条 |
| 告警触发瞬间指标值 `tb_alert_record.observed_value` | ✅ | 单点快照 |
| **聚合指标时序** | ❌ | 本文档要补的层 |

注意:原始数据未丢失,指标永远可从 `tb_app_log` 重算。本聚合层是**派生缓存 + 产品能力使能**,不是正确性修复。

## 3. 设计目标与非目标

**目标**

- 为总览面板的趋势 / 排行提供 O(读少量桶) 的查询。
- 为告警提供「溯源曲线」:回放某规则指标在任意时间段的走势。
- 聚合表可随时从 `tb_app_log` 重建,并能对账。
- 体积小、可长期保留。

**非目标(P1 不做)**

- 不替换 `tb_app_log`,原始表仍是 source of truth。
- 不在 P1 改造告警评估的读路径(见 §9)。
- 不引入按 `model` / `request_type` 维度的聚合(见 §8、§12)。
- 不做秒级实时,接受分钟级粒度与 ~1 分钟滞后。

## 4. 命名

表名 **`tb_app_metric_minute`**。

`log` 与 `metric` 二词已区分「逐条原始」与「聚合指标」;粒度后缀 `_minute` 对齐本仓既有先例 **`tb_integration_quota_day`**(同样是机器写入的预聚合计数表,用粒度作后缀)。不使用数据仓库术语 `_rollup`——本仓无此惯例。

更粗粒度若需要,后续另加 `tb_app_metric_hour` / `tb_app_metric_day`,不在单表里塞 `granularity` 列。

## 5. 数据模型 `tb_app_metric_minute`

逐「分钟桶 × 应用」一行。列风格对齐 `tb_integration_quota_day`:自然复合主键、精简列、仅 `update_time`、无 Snowflake `id`、无 `create_user/update_user`(机器写入,无业务审计意义)。

| 字段 | 类型 | 说明 |
|------|------|------|
| `bucket_start` | BIGINT | 分钟桶起点,Unix ms,对齐到整分钟(`create_time // 60000 * 60000`) |
| `app_id` | BIGINT | 应用 ID;`0` = 无归属应用(如直连模型网关的调用) |
| `request_count` | INT | 桶内调用总数 |
| `success_count` | INT | `success=1` 的数量(`error_count` = `request_count - success_count`,不另存) |
| `total_tokens` | BIGINT | Token 合计 |
| `input_tokens` | BIGINT | 输入 Token 合计 |
| `output_tokens` | BIGINT | 输出 Token 合计 |
| `latency_count` | INT | `latency_ms` 非空的样本数(avg 分母、直方图样本总数) |
| `latency_sum` | BIGINT | `latency_ms` 之和(算平均延迟) |
| `latency_histogram` | TEXT | JSON int 数组,各延迟区间的计数,见 §6 |
| `update_time` | BIGINT | 最后一次聚合写入时间 |

- **主键**:`PRIMARY KEY (bucket_start, app_id)`。前导列 `bucket_start` 天然支持按时间范围扫描,无需额外索引。
- **全局指标**由按 `app_id` 求和得到;故无需单独存「全局行」。
- 用 `app_id=0` 哨兵代替 `NULL`(`tb_app_log.app_id` 可空),规避复合主键里 NULL 的唯一性歧义,与本仓用 `0` 作哨兵的习惯一致。

## 6. 延迟直方图与分位估算

**P95 不能跨桶平均**——把每分钟的 P95 取平均在数学上是错的。采用 Prometheus 式定长直方图:每桶存各延迟区间的计数,查询时把窗口内所有桶的直方图**逐元素相加**,再在合并直方图上求分位。

**默认区间上界(ms)**,共 17 个有界桶 + 1 个溢出桶:

```
[50, 100, 200, 300, 500, 800, 1200, 2000, 3000, 5000, 6000, 8000, 15000,
 30000, 60000, 120000, 300000, +Inf]
```

`latency_histogram` 即长度 18 的计数数组。区间边界应**贴近常用告警阈值**(如内置规则「P95 延迟过高」阈值 6000ms,故设 6000 边界),并向上覆盖到 5 分钟以容纳较慢的 agent 调用,使分位落点更准。

**分位估算**:设合并直方图累计样本数 `N`,目标排名 `rank = ceil(N * p)`。定位 `rank` 落入的桶 `[lo, hi)`,在桶内按累计占比线性插值:

```
estimate = lo + (hi - lo) * (rank - cum_before) / bucket_count
```

落入溢出桶时返回最后一个有限边界(30000ms)作为下界估计。

**精度**:估计误差不超过所在桶宽。当前现算实现本身已是「应用层近似 P95」,此方案精度同量级且可控,需在文档与 API 注释中标注其为近似值。

## 7. 聚合任务 `AppMetricRollupWorker`

进程内定时任务,复刻 `AlertRuleWorker` / `HitlTimeoutWorker` 模式,在 `lifespan` 启停。

| 配置项 | 默认 | 说明 |
|------|------|------|
| `metric_rollup_enabled` | `true` | 是否启用聚合任务 |
| `metric_rollup_interval_seconds` | `60` | 聚合间隔 |
| `metric_rollup_backfill_minutes` | `5` | 每轮回滚重算的尾部分钟数 |

执行逻辑:

1. 抢全局 advisory lock(单 key),多 worker 部署下只有一个进程聚合。
2. 计算重算区间 `[now - backfill_minutes, 上一个完整分钟]`。回算尾部若干分钟以吸收**迟到数据**(`create_time` 落在已聚合分钟里的行);超过 `backfill` 窗口的迟到行不进聚合表(仍在原始表)。
3. 对该区间按 `(create_time // 60000, app_id)` 分组聚合 `tb_app_log`,直方图用 Postgres `count(*) FILTER (WHERE latency_ms < ...)` 在一条 SQL 内算出。
4. **UPSERT**(`INSERT ... ON CONFLICT (bucket_start, app_id) DO UPDATE`)写回——天然幂等,重跑安全。
5. 聚合含同步 DB IO,经 `asyncio.to_thread` 执行。

**当前分钟**未结束,不聚合;聚合表最多滞后约 1 分钟。

## 8. 指标覆盖范围

聚合表能服务大部分但非全部指标:

| 指标 / 面板 | rollup 可服务 | 说明 |
|------|------|------|
| 成功率 / 错误率 | ✅ | `success_count / request_count` |
| P95 / 请求延迟 | ✅ | 合并直方图求分位(§6) |
| 平均延迟 | ✅ | `latency_sum / latency_count` |
| Token 消耗 / 当日累计 | ✅ | 按桶求和 |
| 调用量趋势(24h) | ✅ | 按桶求和 |
| 应用健康度排行 / 错误率排行 | ✅ | 按 `app_id` 分组 |
| Token 按模型分布 | ❌ | rollup 无 `model` 维度,留原始表或后续加 `tb_app_metric_model_day` |
| 连续失败 `consecutive_failures` | ❌ | 需逐请求顺序,只能读原始表 |
| LLM 错误按类型 `llm_error_count_by_type` | ⚠️ | 总错误数 ✅;按 `target_error_type` 细分需 `tb_app_log` 先加 `error_type` 列(见告警设计文档 §12) |

## 9. 读取路径:面板与告警

分阶段迁移,降低风险:

- **P1 —— 总览面板改读 rollup**。`ObservabilityService` 的趋势 / 排行 / Token 查询切到 `tb_app_metric_minute`;面板可接受 ~1 分钟滞后。
- **P1 —— 告警溯源(新能力)**。告警详情页按规则的 `metric_type` + `triggered_at ± window` 查 `tb_app_metric_minute`,画出告警前后的指标曲线。
- **P1 —— 告警评估保持读原始表**。告警窗口通常 ≤ 数小时、对新鲜度敏感,现算成本可接受;先不动,避免一次改太多。
- **P2 —— 告警评估迁移到 rollup**。把可桶化指标切到「已结算分钟读 rollup + 当前不完整分钟读原始表」的混合查询;`consecutive_failures` 始终走原始表。

## 10. 数据保留与重建

- **聚合表体积可控**:100 个应用约 14.4 万行/天,可保留较长(建议 90 天),到期可降采样进 `tb_app_metric_hour/day`。
- **重建**:提供一次性函数 / CLI,删除指定区间后从 `tb_app_log` 重算——因为原始表才是 source of truth。
- **对账**:可抽样比对某区间「rollup 求和」与「原始表现算」,监控漂移。
- **`tb_app_log` 清理(关联建议)**:目前 `tb_app_log` **无清理、无限增长**。聚合层落地后,趋势已沉淀,可为 `tb_app_log` 增加保留期(如 30 天)的清理任务,复用 `CheckpointPurger` 模式。这本身是独立的小项。

## 11. 与 Langfuse 的边界

Langfuse 存逐条 trace、自带面板。本聚合层是**平台自建**:服务平台自己的总览面板与告警,不向 Langfuse 往返、Langfuse 未配置时也可用。Langfuse 仍负责单条链路的深度排查(告警详情的「在 Langfuse 查看会话」深链)。两者职责正交,聚合层保持自包含。

## 12. 实现优先级与未决事项

**P1 范围**:`tb_app_metric_minute` 表 + 迁移、`AppMetricRollupWorker`、总览面板改读 rollup、告警溯源曲线接口、重建函数。

**待后续迭代**

1. **告警评估迁移到 rollup**(§9 P2)。
2. **`model` 维度** —— 支撑「Token 按模型分布」,建议独立表而非给分钟表加维度(避免行数膨胀)。
3. **`error_type` 维度** —— 与告警设计文档 §12 的前置项共享:`tb_app_log` 加结构化错误类型列后,LLM 错误可按类型聚合。
4. **更粗粒度表** —— `tb_app_metric_hour` / `_day`,服务超长区间面板与降采样保留。
5. **`tb_app_log` 保留期清理** —— 见 §10。
