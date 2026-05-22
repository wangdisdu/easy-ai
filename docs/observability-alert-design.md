# 可观测性告警功能详细设计

> 基于原型页面 [ObservabilityView](/Users/wangdi/workspace/king/easy-ai/eoitek-llm/web-demo/assets/ObservabilityView-BSe5_cQ0.js) 的「告警规则」「告警中心」两个 Tab 反推整理。该视图是 demo 构建的混淆产物,本文档已抽取其完整中文文案、字段、交互,并对照后端实现补全数据模型与 API。
>
> 配套文档:[observability-design.md](./observability-design.md) 描述「可观测性总览」Tab,本文档不重复。

---

## 1. 功能概述

可观测性模块自顶向下分四个 Tab:**总览 / 告警中心 / 告警规则 / 用户反馈**。本文档覆盖中间两个——它们共同构成平台的「阈值告警闭环」:

```
告警规则(配什么时候报)
   │  评估器周期扫描 / 立即评估
   ▼
告警记录(报了什么)  ──►  告警中心(查看 / 确认 / 恢复)
   │                          AlertsBell(顶部铃铛实时提醒)
   ▼
指标恢复正常 ──► 评估器自动 resolve
```

设计原则:

- **自建告警,不依赖外部**:指标数据源是平台自有的 `tb_app_log`(与总览同源),不强依赖 Langfuse。Langfuse 仅作为告警记录的链路深链补充。
- **规则与记录解耦**:`tb_alert_rule` 是配置,`tb_alert_record` 是运行时事件;删除规则不影响历史记录(记录持有 `rule_name` 快照)。
- **评估幂等可重入**:同一规则被「立即评估」和后台任务并发评估,靠 `cooldown` + Postgres advisory lock 双重去抖,不会重复落记录。
- **闭环自动化**:命中阈值自动落 `firing` 记录;指标回落到正常区间自动 `resolve`,无需人工介入。
- **管理 API 沿用主仓约定**:HTTP 200 + 业务 `code`,统一 `Resp[T]` / `PagedResp[T]`。

---

## 2. 页面与路由范围

| 页面 / 组件 | 前端路由 | 作用 |
|------|------|------|
| 告警中心 | `/observability/alerts` | 告警记录列表,支持按级别 / 状态 / 时间筛选,确认与恢复 |
| 告警规则 | `/observability/alert-rules` | 规则增删改查、启停、立即评估 |
| 新建 / 编辑规则 | 同上(弹窗) | 规则表单 |
| AlertsBell | `AppLayout` 顶部铃铛 | 轮询活跃告警,分级展示,点击「标记已读」 |

后端 menuCode 统一为 `observability`。

---

## 3. 数据模型

两张表,均加在 Alembic 迁移 `0021_alert_rule` 中。沿用主仓约定:`tb_` 前缀、Snowflake BIGINT 主键(API 以字符串传输)、Unix 毫秒时间戳、标准审计列、无外键约束。

### 3.1 tb_alert_rule(告警规则)

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | BIGINT | 主键 |
| `rule_name` | VARCHAR(255) | 规则名称,服务层校验唯一 |
| `description` | TEXT | 规则描述 |
| `metric_type` | VARCHAR(64) | 监控指标,见 §4.1 |
| `target_error_type` | VARCHAR(64) | 目标 LLM 错误类型;仅 `metric_type=llm_error_count_by_type` 时有意义,空=任意错误 |
| `operator` | VARCHAR(8) | 比较运算符:`lt` / `lte` / `gt` / `gte` / `eq` |
| `threshold` | FLOAT | 阈值 |
| `threshold_unit` | VARCHAR(16) | 阈值单位:`%` / `ms` / `tokens` |
| `scope` | VARCHAR(16) | 监控范围:`global` / `per_app` / `per_request` |
| `level` | VARCHAR(16) | 触发后产生的告警级别:`critical` / `warning` / `info` |
| `window_minutes` | INT | 监控窗口(分钟),1–1440 |
| `cooldown_minutes` | INT | 冷却时间(分钟),0–1440 |
| `notify_channels` | TEXT | 通知渠道 JSON 数组字符串,如 `["inbox"]` |
| `message_template` | TEXT | 告警文案模板,支持占位符,见 §5.5 |
| `enabled` | INT | 启用开关,0 / 1 |
| `trigger_count` | INT | 累计触发次数(运行时统计) |
| `last_triggered_at` | BIGINT | 最后触发时间(Unix ms,运行时统计) |
| `create_time` / `update_time` | BIGINT | 标准审计列 |
| `create_user` / `update_user` | BIGINT | 标准审计列 |

索引:`idx_tb_alert_rule_enabled (enabled)` —— 后台任务每轮按 `enabled=1` 扫描。

> **关于 `level`**:原型 `message_template` 含 `{{level}}` 占位符、告警记录有三级着色,故规则显式携带 `level` 字段(原型表单或为默认隐含),作为触发时赋给告警记录的级别。

### 3.2 tb_alert_record(告警记录)

评估器命中阈值时写入,「告警中心」与 AlertsBell 消费。

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | BIGINT | 主键 |
| `rule_id` | BIGINT | 来源规则 ID |
| `rule_name` | VARCHAR(255) | 触发时的规则名快照,规则删除后历史记录仍可展示 |
| `level` | VARCHAR(16) | 告警级别:`critical` / `warning` / `info` |
| `status` | VARCHAR(16) | 状态:`firing` / `acknowledged` / `resolved`,见 §6 |
| `metric_type` | VARCHAR(64) | 指标类型快照 |
| `scope` | VARCHAR(16) | 范围快照 |
| `app_id` | BIGINT | `scope=per_app` 时填具体应用,`global` 为空 |
| `app_name` | VARCHAR(255) | 应用名快照 |
| `observed_value` | FLOAT | 触发时实测指标值 |
| `threshold` | FLOAT | 触发时阈值快照 |
| `message` | TEXT | 渲染后的告警文案 |
| `triggered_at` | BIGINT | 触发时间(Unix ms) |
| `resolved_at` | BIGINT | 恢复时间,未恢复为空 |
| `acknowledged_at` | BIGINT | 确认时间,未确认为空 |
| `acknowledged_by` | BIGINT | 确认人 user_id |
| `create_time` / `update_time` | BIGINT | 标准审计列 |
| `create_user` / `update_user` | BIGINT | 标准审计列(评估器写入时为空) |

索引:`idx_tb_alert_record_status (status, triggered_at)` —— AlertsBell 高频查 `status=firing`。

---

## 4. 监控指标

### 4.1 指标清单与数据源

8 类指标,全部由 [`AlertEvaluator._compute_metric`](../backend/app/service/alert_evaluator.py) 翻译成对 `tb_app_log` 的聚合查询。窗口为 `[now - window_minutes, now)`。

| `metric_type` | 中文名 | 计算方式 | 典型 operator | 单位 |
|------|------|------|------|------|
| `success_rate` | 成功率 | `sum(success) / count * 100` | `lt` | `%` |
| `error_rate` | 错误率 | `100 - 成功率` | `gt` | `%` |
| `p95_latency` | P95 延迟 | `latency_ms` 的第 95 分位(应用层近似) | `gt` | `ms` |
| `request_latency` | 请求延迟 | 同 P95(P1 复用同算法) | `gt` | `ms` |
| `token_usage_daily` | Token 消耗 | 当日 00:00 起 `sum(total_tokens)`(忽略 window) | `gt` | `tokens` |
| `consecutive_failures` | 连续失败 | 最近请求中尾部连续 `success=0` 的条数 | `gte` | 次 |
| `llm_error_count_by_type` | LLM 错误次数 | 窗口内 `success=0` 计数(见下方限制) | `gt` | 次 |
| `negative_feedback_rate` | 负面反馈率 | 依赖反馈表,P1 未实现(见 §12) | `gt` | `%` |

约定:窗口内无数据时 `_compute_metric` 返回 `None`,该轮**不参与评估**(既不触发也不自动恢复)——无数据无法判定条件是否真的解除,保持现状更安全。

### 4.2 LLM 错误类型

`target_error_type` 的 13 个取值(原型告警规则表单下拉):

`quota_exhausted`(余额耗尽)、`rate_limited`(限流)、`auth_failed`(认证失败)、`model_not_found`(模型不存在)、`context_length_exceeded`(上下文超长)、`content_filter`(内容审查拦截)、`invalid_request`(请求参数错误)、`provider_server_error`(供应商服务错误)、`service_unavailable`(服务不可用)、`timeout`(请求超时)、`network_error`(网络错误)、`response_invalid`(响应格式异常)、`model_not_configured`(模型未配置)。

> **当前限制**:`tb_app_log` 现仅有自由文本 `error_message`,无结构化错误类型列。因此 `llm_error_count_by_type` 暂按窗口内失败次数(`success=0`)统计,`target_error_type` 不参与过滤。按类型细分需后续给 `tb_app_log` 增加 `error_type VARCHAR(64)` 列,并在模型网关写日志时归类(`app/core/integration_errors.py` 已有错误分类逻辑可复用)。

---

## 5. 告警规则评估

### 5.1 评估流程

[`AlertEvaluator.evaluate(db, rule, now_ms)`](../backend/app/service/alert_evaluator.py) 评估单条规则:

```
1. observed = _compute_metric(rule, 窗口)
2. observed 为 None        → 返回「无数据」,不动作
3. breached = operator(observed, threshold)
4. 未命中:
     _resolve_active() 自动恢复该规则名下未关闭的告警(见 §6.2)
     返回「未触发」
5. 命中:
     在冷却期内    → 仅返回「命中」,不重复落记录
     不在冷却期    → 落 firing 记录, trigger_count++, last_triggered_at=now
```

评估器被两处复用:`AlertRuleService.evaluate_rule`(「立即评估」按钮,同步单条)与 `AlertRuleWorker`(后台批量)。

### 5.2 触发条件:运算符与阈值

`operator` 把实测值与 `threshold` 比较:`lt <` / `lte ≤` / `gt >` / `gte ≥` / `eq =`。

服务层 `_validate_config` 做单位粗校验:`%` 仅允许配比率类指标(`success_rate` / `error_rate` / `negative_feedback_rate`),`ms` 仅允许配延迟类指标(`p95_latency` / `request_latency`),否则报 `ALERT_RULE_INVALID_CONFIG`。

### 5.3 监控窗口与冷却

- **`window_minutes`**:聚合区间。除 `token_usage_daily` 固定按当日累计外,其余指标都在 `[now - window, now)` 内聚合。
- **`cooldown_minutes`**:命中后的静默期。距 `last_triggered_at` 不足 `cooldown` 时,即使持续命中也不再落新记录,避免告警风暴。冷却是评估幂等的第一道防线。

### 5.4 监控范围 scope

| `scope` | 含义 | P1 状态 |
|------|------|------|
| `global` | 全平台聚合后判定 | ✅ 已实现 |
| `per_app` | 按应用分组,逐应用判定并分别落记录 | ⏳ 规划(见 §12) |
| `per_request` | 逐条请求判定(适合延迟类) | ⏳ 规划(见 §12) |

P1 阶段 `evaluate` 一律按 `global` 聚合;`per_app` / `per_request` 的规则可以创建,但评估时仍走全局聚合,记录的 `scope` 字段如实保存原值。

### 5.5 告警文案模板

`message_template` 支持占位符,评估器 `_render` 在触发时替换:

| 占位符 | 替换为 |
|------|------|
| `{{level}}` | 告警级别 |
| `{{metric}}` | 指标中文名 |
| `{{value}}` | 实测值 + 单位 |
| `{{threshold}}` | 阈值 + 单位 |
| `{{time}}` | 触发时间 `YYYY-MM-DD HH:MM:SS` |

默认模板:`【{{level}}】{{metric}} 已达 {{value}}，超过阈值 {{threshold}}，触发时间 {{time}}`。

---

## 6. 告警状态机

### 6.1 状态与转移

```
          ┌──────────────── resolve(手动 / 自动) ──────────────┐
          │                                                    ▼
       firing ──acknowledge──► acknowledged ──resolve(手动/自动)──► resolved
       触发中                  已确认                            已恢复
```

| 状态 | 含义 | 进入方式 |
|------|------|------|
| `firing` | 触发中,需关注 | 评估器命中阈值落记录 |
| `acknowledged` | 已确认,有人在跟进 | 告警中心「确认」/ AlertsBell「标记已读」 |
| `resolved` | 已恢复 | 手动「恢复」,或评估器自动恢复 |

约束:`resolved` 是终态;`acknowledge` 拒绝作用于已 `resolved` 的记录(报 `BAD_REQUEST`)。`acknowledge` / `resolve` 均**幂等**,重复调用安全。

AlertsBell 只展示 `status=firing` 的记录——确认后即移出铃铛。

### 6.2 自动恢复

[`AlertEvaluator._resolve_active`](../backend/app/service/alert_evaluator.py):规则指标回落到正常区间(未命中阈值)时,把该规则名下所有**未关闭**的告警记录置为 `resolved`。

- 覆盖 `firing` **与** `acknowledged` 两种状态:底层条件一旦解除,即便此前已被人工确认,也随指标恢复一并关闭,不会有告警永久悬挂。
- 自动恢复发生在 `evaluate` 内,故后台任务与「立即评估」都会触发。
- 自动恢复为系统行为,只写 `resolved_at` / `update_time`,不写 `update_user`。

---

## 7. 后台评估任务

[`AlertRuleWorker`](../backend/app/app/alert_rule_worker.py),进程内定时任务,复刻 `HitlTimeoutWorker` / `CheckpointPurger` 模式,在 `lifespan` 启停。

| 配置项 | 默认 | 说明 |
|------|------|------|
| `alert_eval_enabled` | `true` | 是否启用后台评估 |
| `alert_eval_interval_seconds` | `60` | 评估间隔(秒) |

执行逻辑:

1. 启动后延迟 30s,待 web 就绪、`tb_app_log` 积累数据后再评估。
2. 每轮先抢 Postgres advisory lock(key `90001`);抢不到说明另一进程正在评估,本轮跳过——保证多 worker 部署下同一时刻只有一个进程评估,这是评估幂等的第二道防线。
3. 拉取 `enabled=1` 的规则,逐条调用 `AlertEvaluator.evaluate`。单条规则异常 `rollback` 并续跑,不影响其余规则。
4. 评估含同步 DB IO,通过 `asyncio.to_thread` 丢到线程池,不阻塞事件循环。

---

## 8. API 设计

两组路由均挂在 `/api/v1/observability` 命名空间下,需登录。

### 8.1 告警规则 API

前缀 `/observability/alert-rule`,实现见 [`alert_rule_api.py`](../backend/app/api/alert_rule_api.py)。

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/page` | 分页列表,筛选 `keyword` / `metric_type` / `enabled` |
| POST | `` | 新建规则 |
| GET | `/{id}` | 规则详情 |
| PUT | `/{id}` | 编辑规则(字段级,`null`=不更新) |
| DELETE | `/{id}` | 删除规则(历史告警记录保留) |
| POST | `/{id}/enable` | 启用 |
| POST | `/{id}/disable` | 停用 |
| POST | `/{id}/evaluate` | 立即评估,返回 `AlertRuleEvaluateResp` |

`AlertRuleEvaluateResp`:`{ triggered, observed_value, threshold, message, record_id }`。

### 8.2 告警记录 / 告警中心 API

前缀 `/observability/alert`,实现见 [`alert_record_api.py`](../backend/app/api/alert_record_api.py)。

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/page` | 告警记录分页,筛选 `level` / `status` / `rule_id` / `from` / `to` |
| GET | `/active` | AlertsBell 数据:活跃(firing)告警分级计数 + 最近 20 条 |
| GET | `/{id}` | 告警详情 |
| POST | `/{id}/acknowledge` | 确认告警(firing → acknowledged) |
| POST | `/{id}/resolve` | 恢复告警(firing/acknowledged → resolved) |

> 路由注册时 `/page`、`/active` 在 `/{id}` 之前,避免 `active` 被解析为 `record_id`。

`GET /active` 返回 `AlertActiveResp`:`{ total, critical, warning, info, items[] }`。

`AlertRecordResp` 含计算字段 `duration_ms`:`resolved` 取 `resolved_at - triggered_at`,进行中取 `now - triggered_at`。

### 8.3 统一响应与错误码

所有接口返回 `Resp[T]` / `PagedResp[T]`。新增错误码(`app/core/error_code.py`):

| 常量 | 值 | 含义 |
|------|------|------|
| `ALERT_RULE_NOT_FOUND` | 1400 | 规则不存在 |
| `ALERT_RULE_NAME_DUPLICATE` | 1401 | 规则名重复 |
| `ALERT_RULE_INVALID_CONFIG` | 1402 | 指标 / 单位 / 范围组合非法 |
| `ALERT_RECORD_NOT_FOUND` | 1403 | 告警记录不存在 |

非法状态流转(如确认已恢复的告警)复用通用 `BAD_REQUEST(1001)` + 描述性消息。

---

## 9. 通知渠道

`notify_channels` 是渠道数组,P1 仅支持 `inbox`(站内通知)。

评估器落 `firing` 记录后,应按渠道推送。P1 阶段 `inbox` 渠道的语义即「写入告警记录」本身——AlertsBell 通过 `GET /observability/alert/active` 轮询拉取,无需独立通知表。`AlertEvaluator` 中保留 `TODO` 标记,后续扩展 `email` / `webhook` 时再引入真正的推送层与 `tb_notification` 表。

---

## 10. 与可观测性总览、Langfuse 的关系

- **与总览同源**:告警指标与「可观测性总览」都基于 `tb_app_log`,P95 算法、窗口聚合方式与 `ObservabilityService` 保持一致,口径统一。
- **Langfuse 为补充**:告警记录可携带应用 / 会话信息,前端在告警详情提供「在 Langfuse 查看整段会话」深链;Langfuse 未配置时该入口禁用。告警链路本身不依赖 Langfuse。

---

## 11. 内置告警规则

新环境部署后,种子迁移 `0022_seed_alert_rule` 预置一组开箱可用的全局告警规则,管理员无需手动逐条创建。全部 `scope=global`、`notify_channels=["inbox"]`、`enabled=1`。

| 规则名 | 指标 | 触发条件 | 级别 | 窗口 / 冷却 |
|------|------|------|------|------|
| 全局成功率过低 | `success_rate` | `< 99%` | critical | 5 / 10 分钟 |
| 全局错误率过高 | `error_rate` | `> 5%` | warning | 5 / 10 分钟 |
| P95 延迟过高 | `p95_latency` | `> 6000ms` | warning | 5 / 15 分钟 |
| 连续调用失败 | `consecutive_failures` | `≥ 5 次` | critical | 5 / 10 分钟 |
| 当日 Token 消耗过高 | `token_usage_daily` | `> 1000 万 tokens` | info | —— / 120 分钟 |

阈值取通用默认值,「当日 Token 消耗过高」的阈值与具体部署的用量预算强相关,属占位值,建议按实际调整。迁移按 `rule_name` 逐条幂等:已存在同名规则则跳过,可安全重跑。

新环境无流量时各指标 `_compute_metric` 返回 `None`,不会误报,故内置规则默认即 `enabled`。

---

## 12. 实现优先级与未决事项

**P1 已实现**:`tb_alert_rule` / `tb_alert_record` 两表、规则 CRUD + 启停 + 立即评估、告警记录查询 + 确认 + 恢复、AlertsBell 数据接口、`global` 范围评估、后台周期评估、命中自动落记录、指标恢复自动 resolve(覆盖 firing + acknowledged)。

**待后续迭代**:

1. **`error_type` 列** —— 给 `tb_app_log` 增加结构化错误类型列,让 `llm_error_count_by_type` 的 `target_error_type` 真正生效。
2. **`negative_feedback_rate`** —— 依赖「用户反馈」Tab 的后端表 `tb_app_feedback`,该表尚未建。建表后在 `_compute_metric` 接入,当前返回 `None` 占位。
3. **`per_app` / `per_request` 范围** —— 在 `_compute_metric` 加分组判定,`per_app` 逐应用落记录(填 `app_id` / `app_name`),`per_request` 逐请求判定。
4. **通知推送层** —— `email` / `webhook` 渠道与 `tb_notification` 站内通知表。
5. **规则版本 / 审计** —— 如需追踪规则变更历史,可参照 `tb_skill_version` 模式补版本表。
