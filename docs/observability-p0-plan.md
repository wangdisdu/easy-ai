# 可观测性总览 P0 落地计划

> 范围：仅实现「可观测性总览」Tab，基于现有 `tb_app_log` 表，不引入新表结构。
> 费用、用户反馈、错误分类等依赖未建表数据的能力 **暂不实现**，UI 中显式展示为 `-`。

## 一、交付清单

### 1.1 后端（Python / FastAPI）

| # | 文件 | 说明 |
| --- | --- | --- |
| 1 | `backend/app/model/observability_model.py` | 新增 Pydantic 响应模型：`OverviewStats`、`TrendPoint`、`AppTrendSeries`、`TrendResp`、`ModelTokenRow`、`AppHealthRow`、`ErrorAppRow`、`RecentRequestRow` |
| 2 | `backend/app/service/observability_service.py` | 新增聚合服务，封装所有 SQL 聚合逻辑 |
| 3 | `backend/app/api/observability_api.py` | 新增 6 个 API 路由 |
| 4 | `backend/app/api/router.py` | 注册新路由 |

#### API 列表（统一前缀 `/api/v1/observability`）

| 方法 | 路径 | 功能 | 主要查询参数 |
| --- | --- | --- | --- |
| GET | `/stats` | 4 个核心指标 + 同比变化 | `from`、`to`（可选，默认当日）|
| GET | `/trend` | 调用量趋势（总量 + Top N 应用） | `from`、`to`、`bucket`（默认 `2h`）、`top` |
| GET | `/tokens-by-model` | Token 按模型分组 | `from`、`to` |
| GET | `/app-health` | 应用健康度排行 | `from`、`to`、`sort`、`limit` |
| GET | `/errors-by-app` | 错误率排行 | `from`、`to`、`limit` |
| GET | `/recent-requests` | 最近请求列表 | `limit`（默认 20）|

统一返回 `Resp[T]`。时间参数为 Unix 毫秒，省略时默认「今日 00:00 至当前」。

#### 聚合 SQL 要点

- **时间分桶**：SQLite 使用 `(create_time / bucket_ms) * bucket_ms` 表达式；后续切 Postgres 可平移到 `date_trunc`
- **P95 延迟**：SQLite 没有 `PERCENTILE_CONT`，用应用层近似——按 `latency_ms` 排序后取第 `ceil(n * 0.95)` 行。单次查询返回 `latency_ms` 数组（限制 ≤ 10000 行），Python 端 `statistics.quantiles` 计算
- **成功/失败**：`success = 1` 代表成功
- **Top N 应用**：先 `GROUP BY app_id` 查总调用量，取前 N；再按 N 个 `app_id` + 时间桶做二次聚合
- **索引**：假定已对 `create_time` 有索引；若无，本期不强制新增（SQLite 实测 < 10w 行无感）

#### 未建表字段的显式处理

后端响应中对以下字段返回 `None`，前端渲染 `-`：
- `AppHealthRow.feedback_rate`
- `ErrorAppRow.top_error`
- `RecentRequestRow.feedback`
- `OverviewStats.token_cost`（Token 消耗副文案）
- `ModelTokenRow.cost`

### 1.2 前端（Vue 3 + Ant Design Vue）

| # | 文件 | 说明 |
| --- | --- | --- |
| 1 | `frontend/src/views/observability/ObservabilityView.vue` | 新建总览页（仅 overview Tab，后续告警 Tab 扩展预留） |
| 2 | `frontend/src/api/observability.ts` | 6 个接口的前端封装 |
| 3 | `frontend/src/api/types.ts` | 新增对应 TS interface |
| 4 | `frontend/src/router/index.ts` | `/observability` 路由组件改为 `ObservabilityView.vue` |

#### 图表方案

直接引入原型中使用的纯 SVG 组件（从 `eoitek-llm/vue-app/src/components/charts/` 移植）：
- `AreaChart.vue`、`DonutChart.vue`、`SparkLine.vue`

放在 `frontend/src/components/charts/`。约 300 行代码，零依赖。

#### 页面区块与数据源映射

| 区块 | API | 备注 |
| --- | --- | --- |
| 4 张核心指标卡 | `/stats` | 费用副标题显示 `-` |
| 调用量趋势 (24h) | `/trend` | Top 5 应用 |
| Token 按模型 | `/tokens-by-model` | cost 列显示 `-` |
| 应用健康度排行 | `/app-health` | 好评率列显示 `-`；排序切换本地完成 |
| 错误率排行 | `/errors-by-app` | 主要错误行显示 `-` |
| 最近请求 | `/recent-requests` | 反馈列显示 `-`，点击行跳转 `/app/:app_id`（暂不做独立 trace 详情页）|

> 注：原型中「最近请求」点击跳 `/observability/trace/:id`，P0 阶段简化为跳 Langfuse 外链（若存在 `langfuse_trace_id`）或应用详情页。

#### 查询内容提取

`recentRequests` 的「查询内容」列从 `request_payload.messages` 末尾的 user 消息提取（复用 `AppDetailView.vue` 中已有的 `logPreview` 逻辑，抽到 `frontend/src/utils/log.ts`）。

### 1.3 不做的事情

- ❌ 不新增 `tb_model_price`、`tb_app_feedback`、错误分类字段
- ❌ 不实现告警中心、告警规则两个 Tab
- ❌ 不实现 Trace 详情页，最近请求点击行暂跳应用详情或 Langfuse 外链
- ❌ 不做权限细分（`observability:view` 等），当前登录用户均可访问
- ❌ 不做 CSV 导出
- ❌ 不做响应式断点适配（1080px 以下降级），沿用 Ant Design 默认行为

## 二、关键技术决策（请确认）

以下 6 个决策点可能影响实现复杂度，**请明确选型后再启动编码**：

| # | 决策点 | 选项 A（推荐） | 选项 B |
| --- | --- | --- | --- |
| 1 | **默认时间窗口** | 今日 00:00 至当前 | 最近 24 小时滚动窗口 |
| 2 | **P95 实现** | 应用层近似（`latency_ms` 数组 + Python 排序） | 下次迁移 Postgres 再做 |
| 3 | **趋势图时间粒度** | 固定 2 小时桶共 12 点 | 前端可切换 `1h/2h/6h` |
| 4 | **Top N 应用** | 固定 Top 5 | 参数可调 |
| 5 | **图表组件** | 移植原型 SVG 组件（零依赖） | 引入 echarts / vue-chartjs |
| 6 | **最近请求点击行为** | 无 `langfuse_trace_id` 时禁用点击；有则跳 Langfuse 外链 | 跳应用详情页历史消息 Tab |

## 三、工时估算

| 阶段 | 内容 | 预估 |
| --- | --- | --- |
| 后端聚合 Service | 6 个聚合方法 + 单元测试 | 4h |
| 后端 API 层 | Model、路由、注册 | 1h |
| 前端图表组件移植 | AreaChart / DonutChart / SparkLine | 1h |
| 前端页面 | ObservabilityView + API 封装 + 路由替换 | 4h |
| 联调与数据构造 | 手工跑测试应用产生日志数据、微调 UI | 2h |
| **合计** | | **约 12 小时** |

## 四、验收标准

1. 访问 `/observability`，不再是 Mock 页面，展示完整总览
2. 6 个区块均能正确渲染，聚合数据与 `tb_app_log` 手工 SQL 结果一致
3. 指标为空（无数据）时显示 `-`，不展示 `0`
4. 费用、好评率、主要错误等未建表字段统一展示为 `-`，不报错
5. 切换应用健康度排序（调用量/成功率/好评率），前端排序实时生效
6. 最近请求点击后跳转正确（Langfuse 外链或禁用）
7. 后端 `ruff check`、前端 `vue-tsc --noEmit` 全部通过

## 五、风险与回滚

- **数据量风险**：`tb_app_log` 增长后 P95 近似算法会慢，需要在日志量 > 5w 时切换到 bucket 采样或 Postgres
- **空库体验**：刚上线时无数据，所有指标卡展示 `-`，需要确认是否先填充部分测试数据
- **回滚**：改动不涉及数据库结构、不修改 `tb_app_log`，仅新增后端路由与前端页面，回滚直接 revert 对应提交即可

## 六、启动前待确认事项

请就以下几点给出决策：

1. **六个技术决策点**（表格中选 A 还是 B）
2. **是否需要同时新增侧边栏图标**（当前是 `eye`，可保留）
3. **「最近请求」显示 Langfuse 外链** 的 URL 前缀从哪里读？建议复用 `backend/app/core/config.py` 中已有的 `langfuse_host`，前端通过 `/setting` 或新增 `/api/v1/system/config` 接口取
4. **是否需要 CSV 导出的预留菜单项**（即使功能未实现）
