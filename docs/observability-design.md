# 可观测性功能设计文档

## 一、概述

可观测性模块面向平台管理员与运营人员，提供跨应用的全局运营视角，聚合展示请求量、成功率、延迟、Token 消耗、应用健康度、错误分布与请求明细等关键指标。底层数据源以 `tb_app_log`（平台自有）与 Langfuse（链路追踪）为主，前端负责聚合视图与交互。

本文档仅聚焦「可观测性总览」子模块（页面 `ObservabilityPage.vue` 的 overview Tab）。告警中心、告警规则配置将在独立文档中描述。

## 二、页面信息结构

总览页自顶向下分为五个区块：

```
┌──────────────────────────────────────────────────────┐
│ [1] 核心指标卡 × 4                                    │ 顶部统计
├──────────────────────────────────────────────────────┤
│ [2] 全局调用量趋势 (24h)     │ [3] Token 消耗 (按模型) │ 趋势与分布
├──────────────────────────────┼───────────────────────┤
│ [4] 应用健康度排行            │ [5] 错误率排行         │ 应用维度
├──────────────────────────────┴───────────────────────┤
│ [6] 最近请求列表                                       │ 请求明细
└──────────────────────────────────────────────────────┘
```

### 2.1 核心指标卡（Top Stats）

四张并列卡片，每张包含：

| 字段 | 含义 | 示例 |
| --- | --- | --- |
| label | 指标名称 | 今日总请求 |
| value | 当前值（格式化） | 258,432 |
| sub | 辅助信息（对比/费用） | 较昨日 +12.3% |
| color | 主题色，用于数字与 SparkLine | `#3B82F6` |
| spark | 最近 N 个时间点的走势数组 | `[180,195,...,258]` |

四个指标：
1. **今日总请求** — 来自 `tb_app_log` 当日计数，对比昨日同时间段
2. **全局成功率** — `success=1` / 全量，同时显示失败次数
3. **P95 延迟** — `latency_ms` 的 P95，对比上周趋势
4. **Token 总消耗** — `total_tokens` 汇总，叠加费用估算

### 2.2 全局调用量趋势（24h）

面积图 + 应用分项。

- **主图**：24 小时按 2 小时为粒度聚合，X 轴 `00,02,...,22`，Y 轴为请求数。绘制全局总量。
- **图例**：列出参与聚合的 Top N（当前 5 个）应用，每个应用独立颜色。
- **底部小结**：每个应用的 24 小时总量（单位 K）。

数据约定：
```ts
interface AppTrendSeries {
  name: string       // 应用名
  color: string      // 展示色
  data: number[]     // 12 个时间点的请求量
}
```

### 2.3 Token 消耗（按模型）

环形图 + 模型列表。

- **环形图** 按模型分段，分段值来自 Token 消耗占比
- **列表** 每行：模型名、Token 数、估算费用
- 需与 [2.1] 的 Token 总消耗保持一致

### 2.4 应用健康度排行

表格，支持切换排序维度：`调用量 / 成功率升序 / 好评率`。

| 列 | 说明 |
| --- | --- |
| 应用 | 应用名 |
| 类型 | RAG / NL2SQL / LLM / Agent 等，带类型色徽章 |
| 调用量 | 今日/近 24h 调用次数 |
| 成功率 | ≥99% 绿色、否则琥珀色 |
| P95 | P95 延迟（ms/s） |
| Token | 总 Token 消耗 |
| 好评率 | 基于用户反馈（`feedback` 字段） |
| 趋势 | SparkLine 展示好评率近 7 天趋势 |

颜色阈值规则（设计系统中的约定）：
- 成功率：`>=99% → emerald`、否则 `amber`
- 好评率：`>=85% → emerald`、`>=80% → amber`、否则 `rose`

### 2.5 错误率排行

卡片内列表，按错误率降序。每条包含：

- 应用名 + 类型徽章
- 错误率数值（颜色按阈值 1% / 0.5%）
- 水平进度条（相对该页最大错误率归一化）
- 主要错误类型（`topError`，如「SQL 执行超时」「Rate Limit」）
- 绝对错误次数

### 2.6 最近请求列表

表格，展示最近 N 条请求，点击任意行跳转至 Trace 详情页：

```
router.push(`/observability/trace/${r.id}?type=${r.type}`)
```

列：时间、应用、类型、用户、查询内容（截断）、延迟、Tokens、状态（成功/失败）、反馈（👍/👎/-）。

## 三、后端数据模型与 API

可观测性总览的所有指标都可以从现有 `tb_app_log` 表聚合得出，无需额外表结构。部分跨时间/跨服务的复杂指标可回源至 Langfuse（通过 `langfuse_trace_id` 关联）。

### 3.1 数据来源字段

来自 `tb_app_log`：

| 字段 | 用途 |
| --- | --- |
| `app_id` / `app_type` | 应用聚合、类型分类 |
| `model` / `model_id` | 模型分组（Token 消耗 by 模型） |
| `success` / `response_status` | 成功率、错误率 |
| `latency_ms` | P95 延迟、平均延迟 |
| `total_tokens` / `input_tokens` / `output_tokens` | Token 消耗 |
| `create_time` | 时间窗口聚合 |
| `langfuse_trace_id` | 跳转 Langfuse 查看完整链路 |
| `request_payload` / `response_payload` | 最近请求的查询内容、状态 |

尚未覆盖、需要补充的数据：
- **用户反馈** —— 需新增 `tb_app_feedback`（至少包含 `log_id` / `trace_id`、`user_id`、`feedback` ∈ {positive, negative}、`create_time`），或在 `tb_app_log` 上追加 `feedback` 字段。
- **错误分类** —— 错误率排行中的 `topError` 需要错误归因，建议在 `error_message` 基础上做正则/规则归类，或新增 `error_category` 字段。
- **费用估算** —— 需按模型维护单价表（`tb_model_price`），或在 `tb_model` 表上追加 `price_per_1k_input` / `price_per_1k_output`。

### 3.2 API 清单（建议）

所有接口统一前缀 `/api/v1/observability`，返回 `Resp[T]`。时间参数统一使用 Unix 毫秒。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/overview/stats` | 四个核心指标（今日总请求、成功率、P95、Token 总消耗），支持 `from` / `to` 查询参数，默认当日与昨日对比 |
| GET | `/overview/trend` | 全局调用量趋势，参数 `granularity`（`hour`/`2hour`/`day`）、`from`/`to`、`top_apps`，返回 `{labels, total, apps: AppTrendSeries[]}` |
| GET | `/overview/tokens-by-model` | Token 消耗按模型分组，返回 `[{model, tokens, cost}]` |
| GET | `/overview/app-health` | 应用健康度排行，参数 `sort`（`calls`/`success_rate`/`feedback`）、`limit`，返回 `AppHealthRow[]` |
| GET | `/overview/errors-by-app` | 错误率排行，返回 `[{app_id, app_name, app_type, errors, rate, top_error}]` |
| GET | `/overview/recent-requests` | 最近请求列表，参数 `limit`，返回与 `AppLogResp` 一致但裁剪过的摘要 |

### 3.3 聚合 SQL 约定

为避免前端长查询超时，所有聚合查询应：
1. 固定时间窗（默认当日 00:00 起算），大窗查询单独接口
2. 对 `create_time` 建立索引（已存在则复用）
3. P95 可用 `PERCENTILE_CONT(0.95)`（Postgres）或应用层估算（SQLite 暂用近似：按 `latency_ms` 排序取第 95% 位）
4. 避免 `SELECT *`，按接口返回字段精简投影

### 3.4 与 Langfuse 的协同

- **总览层指标** 用 `tb_app_log` 计算，保证和业务侧账本一致，且受控于我方数据库
- **链路级下钻** 点击「最近请求」任一行时，前端优先跳转到我方 Trace 详情页（展示 `response_payload` 里的 messages 结构），同时提供外链跳转到 Langfuse UI（基于 `langfuse_trace_id`）

## 四、前端实现约定

### 4.1 组件复用

- **图表** 统一用 `components/charts/` 下的 `AreaChart`、`DonutChart`、`SparkLine`，保持 SVG 纯渲染，避免引入重图表库
- **指标卡** 沿用现有 `glass-card` 与动画类 `anim-in anim-d{n}`
- **类型徽章** 使用 `typeColors` 映射（`RAG` / `NL2SQL` / `LLM` / `Agent`），新增类型时同步扩展

### 4.2 页面状态

- 响应失败时：卡片显示骨架占位，不用空白；表格区显示 `a-empty`
- 指标未采集（`total_tokens` 为 `null`）时显示 `-`，禁止显示 `0`，与「零用量」语义区分
- 排序切换仅在前端完成（前提是接口返回行数 ≤ 100）；超过则切换到后端排序

### 4.3 交互

- 点击「最近请求」行跳转 Trace 详情（沿用原型路由 `/observability/trace/:id`）
- 应用健康度表格支持按列排序（目前仅三种）；列宽和颜色阈值定义在页面内
- 所有图表支持响应式宽度，最小断点 `1080px` 以下堆叠为单列

## 五、路由与权限

### 5.1 前端路由

```
/observability                 // 总览 + Tab 切换（overview / alerts / alert-rules）
/observability/trace/:id       // 单次请求的 Trace 详情
```

### 5.2 权限

- **查看总览** —— 需要 `observability:view` 权限，所有平台管理员默认拥有
- **跳转 Trace 详情** —— 需额外 `observability:trace:view`
- **导出** —— 预留 `observability:export`，用于导出报表 CSV

## 六、实现优先级建议

建议分阶段落地：

1. **P0** — 核心指标卡 + 全局调用量趋势 + 最近请求列表（直接复用 `tb_app_log`，无需新增表结构）
2. **P1** — 应用健康度排行 + Token 按模型分布（需要模型单价与 Top N 聚合查询）
3. **P2** — 错误率排行（需要错误分类字段或归因规则）
4. **P3** — 用户反馈相关指标（好评率），依赖反馈表结构落地

## 七、未决事项

- 费用估算币种与汇率是否统一为 CNY？离线汇率表的刷新周期
- P95 在 SQLite 环境下的近似算法是否足够，是否切换至 ClickHouse 或其他 OLAP
- 错误分类是规则引擎驱动还是基于模型推断（例如通过小模型给 `error_message` 打标签）
- Trace 详情页是我方自建还是直接 iframe 嵌入 Langfuse
