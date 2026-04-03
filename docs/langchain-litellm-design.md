# LangChain + LiteLLM 接入设计

## 1. 目标

本方案采用：

- `LiteLLM` 作为统一模型接入网关
- `LangChain / LangGraph / DeepAgents` 作为上层编排框架
- 平台后端负责供应商配置、模型配置、应用配置、运行时调用编排

设计目标：

- 用统一方式接入 OpenAI、Anthropic、Gemini、Azure OpenAI、Ollama 等模型供应商
- 上层应用、Agent、RAG、Flow 不直接感知不同厂商 SDK
- LangChain 统一对接 LiteLLM 网关接口，而不是分别对接各模型厂商
- 平台侧统一做模型配置、鉴权、路由、日志、限流、故障切换和成本治理

---

## 2. 总体架构

### 2.1 调用链

```text
应用工厂 / Agent Runtime / RAG Runtime
    -> LangChain / LangGraph / DeepAgents
    -> LiteLLM Gateway（OpenAI-compatible）
    -> OpenAI / Anthropic / Gemini / Azure OpenAI / Ollama
```

### 2.2 分层职责

| 层 | 组件 | 职责 |
|------|------|------|
| 平台配置层 | `tb_llm_provider` / `tb_llm_model` | 维护供应商、模型、鉴权信息、启停状态 |
| 模型网关层 | LiteLLM | 多厂商适配、统一接口、路由、fallback、代理 |
| 编排运行层 | LangChain / LangGraph / DeepAgents | Prompt 编排、Agent、工具调用、Graph 状态流转 |
| 业务应用层 | App / RAG / Agent / Flow | 承载业务场景配置与运行逻辑 |

### 2.3 设计原则

- LangChain 不直接保存厂商 API Key
- 平台运行时只配置 LiteLLM 网关地址和网关密钥
- 厂商密钥只保留在平台后端管理面或 LiteLLM 配置层
- 模型供应商差异在 LiteLLM 层收敛
- 应用侧只引用平台模型 ID，不直接引用供应商 SDK 参数

---

## 3. 数据模型设计

当前项目已经存在 `tb_llm_provider` 与 `tb_llm_model`，本方案在此基础上补充字段语义与建议扩展。

### 3.1 `tb_llm_provider`

作用：维护 LiteLLM 可识别的供应商连接配置。

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | bigint | 是 | 主键 |
| `name` | varchar(255) | 是 | 平台内显示名，如 `OpenAI-Prod` |
| `provider_type` | varchar(255) | 是 | 供应商类型，如 `openai` / `anthropic` / `gemini` / `azure` / `ollama` |
| `base_url` | text | 是 | 供应商原始地址或代理地址 |
| `api_key` | text | 否 | 供应商密钥，建议后续改为加密存储 |
| `status` | varchar(255) | 是 | `active` / `inactive` |
| `last_check` | bigint | 否 | 最近探活时间 |
| `create_time` | bigint | 是 | 创建时间 |
| `update_time` | bigint | 是 | 更新时间 |
| `create_user` | bigint | 否 | 创建人 |
| `update_user` | bigint | 否 | 更新人 |

建议约束：

- 唯一约束：`uk_tb_llm_provider_name(name)`
- 索引：`idx_tb_llm_provider_type(provider_type)`
- 索引：`idx_tb_llm_provider_status(status)`

建议 `provider_type` 枚举：

- `openai`
- `anthropic`
- `gemini`
- `azure`
- `ollama`
- `openai_compatible`

说明：

- `provider_type` 用于映射 LiteLLM 的 provider 语义
- `base_url` 允许配置供应商原始地址，也允许配置内部代理地址
- 后续若要支持更复杂鉴权，可新增 `provider_config` 字段，存 JSON 格式扩展配置

### 3.2 `tb_llm_model`

作用：维护平台可选模型清单，一个模型归属于一个供应商。

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | bigint | 是 | 主键 |
| `provider_id` | bigint | 是 | 所属供应商 ID |
| `model` | varchar(255) | 是 | LiteLLM 调用时使用的模型标识 |
| `model_type` | varchar(255) | 是 | 模型分类，如 `chat` / `embedding` / `rerank` / `image` |
| `status` | varchar(255) | 是 | `active` / `inactive` |
| `create_time` | bigint | 是 | 创建时间 |
| `update_time` | bigint | 是 | 更新时间 |
| `create_user` | bigint | 否 | 创建人 |
| `update_user` | bigint | 否 | 更新人 |

建议约束：

- 唯一约束：`uk_tb_llm_model_provider_model(provider_id, model)`
- 索引：`idx_tb_llm_model_provider_id(provider_id)`
- 索引：`idx_tb_llm_model_model_type(model_type)`
- 索引：`idx_tb_llm_model_status(status)`

说明：

- `model` 建议直接保存 LiteLLM 路由使用的模型名
- 如果后续需要平台别名，可新增 `alias` 字段，但当前版本建议先不加

### 3.3 建议新增：`tb_llm_gateway`

如果系统未来需要同时接多个 LiteLLM 网关实例，建议新增网关表；如果只有一个固定网关，可先不建表，直接放配置文件。

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | bigint | 是 | 主键 |
| `name` | varchar(255) | 是 | 网关名称，如 `litellm-prod` |
| `gateway_url` | text | 是 | LiteLLM 网关地址 |
| `gateway_key` | text | 否 | 网关访问密钥 |
| `status` | varchar(255) | 是 | `active` / `inactive` |
| `remark` | text | 否 | 备注 |
| `create_time` | bigint | 是 | 创建时间 |
| `update_time` | bigint | 是 | 更新时间 |
| `create_user` | bigint | 否 | 创建人 |
| `update_user` | bigint | 否 | 更新人 |

适用场景：

- 开发 / 测试 / 生产多套 LiteLLM 网关
- 不同业务域使用不同 LiteLLM 实例
- 需要网关级别容灾和切换

### 3.4 应用工厂与模型的关系

应用主表 `tb_app` 已经保留以下字段：

- `provider_id`
- `model_id`
- `model`
- `model_setting`

在本方案中它们的含义如下：

| 字段 | 说明 |
|------|------|
| `provider_id` | 选中的模型供应商 |
| `model_id` | 选中的模型配置 |
| `model` | 冗余存储的模型名快照 |
| `model_setting` | 推理参数 JSON，如 `temperature`、`max_tokens`、`top_p` |

建议 `model_setting` JSON 结构：

```json
{
  "temperature": 0.7,
  "max_tokens": 2048,
  "top_p": 1,
  "stream": true
}
```

---

## 4. LiteLLM 网关设计

### 4.1 网关职责

LiteLLM 统一负责：

- 各模型厂商 SDK / API 差异适配
- OpenAI-compatible 接口暴露
- 模型路由与模型名统一
- 重试、超时、fallback
- 统一日志和成本统计

### 4.2 平台与 LiteLLM 的关系

平台数据库保存“供应商”和“模型”配置，LiteLLM 保存“运行时路由规则”。

建议平台后端在以下两种模式中二选一：

1. 静态 LiteLLM 配置模式
   平台只管理元数据，LiteLLM 配置文件单独维护。

2. 平台下发 LiteLLM 配置模式
   平台管理供应商和模型，并生成 LiteLLM 需要的路由配置。

当前建议先采用第 1 种：

- 实现简单
- 上线快
- 风险可控

后续需要平台化治理时，再演进到第 2 种。

### 4.3 LiteLLM 配置映射建议

`tb_llm_provider` 与 `tb_llm_model` 可以映射成 LiteLLM 的 model entry：

```yaml
model_list:
  - model_name: gpt-4o
    litellm_params:
      model: openai/gpt-4o
      api_key: ${OPENAI_API_KEY}
      api_base: https://api.openai.com/v1

  - model_name: claude-3-7-sonnet
    litellm_params:
      model: anthropic/claude-3-7-sonnet-latest
      api_key: ${ANTHROPIC_API_KEY}
```

平台侧建议统一使用：

- 展示名：来自 `tb_llm_provider.name`
- 供应商类型：来自 `tb_llm_provider.provider_type`
- 调用模型名：来自 `tb_llm_model.model`

---

## 5. LangChain / LangGraph / DeepAgents 对接方式

### 5.1 统一接入原则

LangChain 不直接连 OpenAI、Anthropic、Gemini 等厂商。

LangChain 统一连接 LiteLLM 网关，例如：

- `base_url = http://litellm-gateway:4000/v1`
- `api_key = <gateway-api-key>`
- `model = <tb_llm_model.model>`

### 5.2 编排层职责

| 套件 | 用途 |
|------|------|
| `langchain` | Prompt、Chain、Retriever、Tool 封装 |
| `langgraph` | 状态流、Agent Graph、多节点编排 |
| `deepagents` | 高阶 Agent 执行框架，承载复杂智能体能力 |

### 5.3 运行时调用流程

```text
读取应用配置 tb_app
    -> 解析 provider_id / model_id / model_setting / app_config
    -> 组装 LangChain ChatModel 参数
    -> 将请求发送到 LiteLLM 网关
    -> LiteLLM 调用具体模型厂商
    -> 返回结果给 LangChain / Agent Runtime
```

### 5.4 推荐运行时参数结构

运行时统一传给模型适配层：

```json
{
  "model": "gpt-4o",
  "base_url": "http://litellm:4000/v1",
  "api_key": "gateway-key",
  "temperature": 0.7,
  "max_tokens": 2048
}
```

说明：

- `model` 来自 `tb_app.model` 或 `tb_llm_model.model`
- `temperature`、`max_tokens` 等来自 `tb_app.model_setting`
- LangChain 侧不需要知道底层真实厂商是谁

---

## 6. 后端模块划分

### 6.1 模块边界

建议后端按以下方式拆分：

| 模块 | 说明 |
|------|------|
| `app/service/llm_service.py` | 管理供应商和模型配置 |
| `app/service/model_gateway_service.py` | 统一封装 LiteLLM 网关调用 |
| `app/service/llm_runtime_service.py` | 基于应用配置组装模型调用参数 |
| `app/service/langchain_service.py` | 封装 LangChain ChatModel / EmbeddingModel 创建逻辑 |
| `app/service/agent_runtime_service.py` | 基于 LangGraph / DeepAgents 承载 Agent 执行 |
| `app/service/rag_runtime_service.py` | 承载 RAG 应用运行逻辑 |
| `app/service/app_service.py` | 负责应用配置 CRUD，不直接处理模型调用 |

### 6.2 详细职责

#### `llm_service.py`

负责：

- 供应商 CRUD
- 模型 CRUD
- 模型启停
- 模型列表查询

不负责：

- 真正的模型推理调用

#### `model_gateway_service.py`

负责：

- 对 LiteLLM 网关发起 HTTP 请求
- 统一封装请求头、超时、重试、错误处理
- 统一处理 chat、embedding、rerank 等调用入口

建议接口：

- `chat_completion(...)`
- `embedding(...)`
- `rerank(...)`

#### `llm_runtime_service.py`

负责：

- 从 `tb_app` 读取模型相关配置
- 合并 `tb_llm_provider`、`tb_llm_model`、`tb_app.model_setting`
- 产出 LangChain 可直接消费的模型参数

建议接口：

- `build_chat_runtime(app_id)`
- `build_embedding_runtime(app_id)`

#### `langchain_service.py`

负责：

- 创建 LangChain ChatModel
- 创建 Embedding 模型
- 统一封装 LangChain 对 LiteLLM 网关的接入参数

建议接口：

- `build_chat_model(runtime_config)`
- `build_embedding_model(runtime_config)`

#### `agent_runtime_service.py`

负责：

- 基于 LangGraph / DeepAgents 运行 Agent
- 管理工具、技能、对话上下文、图状态
- 为 Agent 应用与 Agent Flow 提供统一运行入口

#### `rag_runtime_service.py`

负责：

- 执行检索、重排、总结
- 调用 LangChain 组织最终生成链路

---

## 7. API 设计建议

### 7.1 模型管理接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/v1/llm/provider/page` | 分页查询供应商 |
| `POST` | `/api/v1/llm/provider` | 创建供应商 |
| `PUT` | `/api/v1/llm/provider/{id}` | 更新供应商 |
| `GET` | `/api/v1/llm/model/page` | 分页查询模型 |
| `POST` | `/api/v1/llm/model` | 创建模型 |
| `PUT` | `/api/v1/llm/model/{id}` | 更新模型 |

### 7.2 运行时接口

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/v1/runtime/chat/{app_id}` | 通用 LLM 应用调用 |
| `POST` | `/api/v1/runtime/rag/{app_id}` | RAG 应用调用 |
| `POST` | `/api/v1/runtime/agent/{app_id}` | Agent 应用调用 |
| `POST` | `/api/v1/runtime/flow/{app_id}` | Agent Flow 调用 |

说明：

- 上述接口内部统一走 LangChain + LiteLLM
- 具体调用路径由应用类型决定

---

## 8. 落地顺序建议

建议按以下顺序实施：

1. 完善 `tb_llm_provider` 与 `tb_llm_model` 的字段语义和管理接口
2. 部署 LiteLLM 网关，并验证 OpenAI-compatible 入口可用
3. 新增 `model_gateway_service.py`，统一封装 LiteLLM HTTP 调用
4. 新增 `langchain_service.py`，让 LangChain 统一走 LiteLLM 网关
5. 在 `app_service` 对应的运行时链路中接入 `llm_runtime_service`
6. 为 `agent` 应用引入 LangGraph / DeepAgents 运行时
7. 后续再补充 fallback、成本统计、调用日志、配额策略

---

## 9. 当前阶段建议结论

当前项目建议采用：

- 数据库：保留 `tb_llm_provider` 与 `tb_llm_model`
- 网关：单实例 LiteLLM
- 编排：LangChain + LangGraph + DeepAgents
- 应用侧：统一通过平台模型配置选择模型

当前阶段不建议立即做：

- 多 LiteLLM 网关动态切换
- 平台自动下发 LiteLLM 全量配置
- 模型别名与复杂路由编排

先把“统一模型接入 + 编排层统一走 LiteLLM”落地，再逐步扩展治理能力。
