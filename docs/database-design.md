# database-design 数据库设计

## 数据库规范

### 字符串字段类型

- 字符串字段统一使用 `VARCHAR(255)` 或 `TEXT` 类型。
- 时间字段统一使用 `UnixMS`（Unix 时间戳的毫秒表示）。
- 使用字符串类型存储 JSON 数据，由业务层处理 JSON 格式，保障数据库兼容性。

### 标准字段

默认包含 4 个字段，除非某表明确不需要。

| 列名 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `create_time` | BIGINT | 是 | Unix **毫秒**级时间戳 |
| `update_time` | BIGINT | 是 | Unix **毫秒**级时间戳，更新时刷新 |
| `create_user` | BIGINT | 否 | 操作者用户 ID |
| `update_user` | BIGINT | 否 | 操作者用户 ID |

### 主键

主键均为 `BIGINT`，由应用 Snowflake 生成（`snowflake_worker_id` 可配）。

### 外键

禁止使用外键约束。

### 表名

全部用tb_为前缀

### 字段名

避免使用sql关键字，例如：select、from、where、delete、update、delete、join、type等

## 示例：`tb_user`（用户）

| 列名 | 类型 | 必填 | 约束/说明 |
|------|------|------|-----------|
| `id` | BIGINT | 是 | PK |
| `account` | VARCHAR(255) | 是 | **全局唯一**，登录账号 |
| `passwd` | TEXT | 是 | bcrypt 哈希，不存明文 |
| `email` | VARCHAR(255) | 否 | 邮箱 |
| `name` | VARCHAR(255) | 否 | 显示名 |
| `phone` | VARCHAR(255) | 否 | 手机 |
| `department` | VARCHAR(255) | 否 | 部门 |

## 应用工厂

> 设计原则：
> - 五种应用类型（RAG / LLM / NL2SQL / Agent / Agent Flow）共用一张主表 `tb_app`，通过 `app_type` 区分。
> - 各类型的差异化配置统一存入 `config` 字段（TEXT/JSON），由业务层按 `app_type` 解析，避免大量可空列或过多子表。
> - 发布版本独立建表 `tb_app_version`，支持版本回溯与灰度发布。

### `tb_app`（应用）

| 列名 | 类型 | 必填 | 约束/说明 |
|------|------|------|-----------|
| `id` | BIGINT | 是 | PK |
| `name` | VARCHAR(255) | 是 | 应用名称 |
| `description` | TEXT | 否 | 应用描述 |
| `app_type` | VARCHAR(255) | 是 | 应用类型：`RAG` / `LLM` / `NL2SQL` / `Agent` / `AgentFlow` |
| `app_status` | VARCHAR(255) | 是 | 状态：`draft` / `published` / `offline`，默认 `draft` |
| `engine` | VARCHAR(255) | 否 | 底层引擎标识（RAGFlow / LiteLLM / Vanna / AgentRuntime / FlowEngine） |
| `model` | VARCHAR(255) | 否 | 模型标识（如 `gpt-4o`、`qwen-72b`） |
| `temperature` | DOUBLE | 否 | Temperature 参数，默认 0.7 |
| `max_tokens` | INT | 否 | 最大生成 Token 数，默认 2048 |
| `system_prompt` | TEXT | 否 | System Prompt |
| `config` | TEXT | 否 | 类型专属配置，JSON 字符串，结构见下方说明 |
| `access_scope` | VARCHAR(255) | 否 | 访问范围：`internal` / `api` / `embed`，默认 `internal` |
| `rate_limit` | INT | 否 | 每分钟请求限制，默认 60 |
| `enable_log` | TINYINT | 否 | 是否启用调用日志，默认 1 |
| `current_version` | VARCHAR(255) | 否 | 当前发布版本号，草稿时为空 |
| `total_calls` | BIGINT | 否 | 累计调用次数，默认 0 |

#### `config` 字段结构说明

按 `app_type` 存储不同的 JSON 结构：

**LLM 类型：**

```json
{
  "user_prompt": "请分析以下内容：\n\n{{report_text}}",
  "input_vars": [
    { "name": "report_text", "label": "研报内容", "var_type": "textarea", "required": true }
  ],
  "output_format": "json",
  "output_vars": [
    { "name": "summary", "var_type": "string", "description": "摘要" }
  ]
}
```

**RAG 类型：**

```json
{
  "kb_ids": ["1001", "1002"],
  "similarity_threshold": 0.2,
  "vector_weight": 0.3,
  "top_n": 6,
  "enable_rerank": true,
  "rerank_model": "bge-reranker-v2-m3",
  "rerank_top_n": 3,
  "enable_summary": true,
  "summary_model": "qwen-72b",
  "summary_temperature": 0.3,
  "summary_prompt": "你是一个专业的知识总结助手..."
}
```

**NL2SQL 类型：**

```json
{
  "db_connection": "prometheus_metrics",
  "db_schema": "CREATE TABLE metrics ..."
}
```

**Agent 类型：**

```json
{
  "tool_ids": ["1919810114514001", "1919810114514002"],
  "skill_ids": ["sk-rca", "sk-alert-triage"],
  "sub_agents": [
    { "name": "监控分析子智能体", "model": "qwen-72b", "agent_role": "指标分析和异常检测" }
  ],
  "max_turns": 20,
  "agent_timeout": 60,
  "allow_auto_exec": false
}
```

**AgentFlow 类型：**

```json
{
  "flow_instance": "flow-prod",
  "flow_id": "flowise-xxx",
  "flow_name": "故障响应编排",
  "flow_sync_trace": true
}
```

### `tb_app_version`（应用版本）

记录每次发布的版本快照，支持版本回溯。

| 列名 | 类型 | 必填 | 约束/说明 |
|------|------|------|-----------|
| `id` | BIGINT | 是 | PK |
| `app_id` | BIGINT | 是 | 所属应用 ID |
| `version` | VARCHAR(255) | 是 | 版本号（如 `v1.0.0`） |
| `version_note` | TEXT | 否 | 版本说明 |
| `app_snapshot` | TEXT | 否 | 发布时的完整应用配置快照，JSON 字符串 |
| `published_time` | BIGINT | 是 | 发布时间（Unix ms） |

## 工具管理

> 设计原则：
> - 系统内置工具由平台硬编码，不存数据库。
> - MCP Server 连接配置独立建表 `tb_mcp_server`，一个 Server 可探测出多个工具。
> - 所有用户注册的工具（MCP 探测导入的、手动注册的 API 工具）统一存入 `tb_tool`，通过 `source` 字段区分来源。
> - 工具三要素（名字、描述、参数）直接存为 `tb_tool` 的字段，其中参数以 JSON Schema 格式存储为 TEXT。
> - API 工具的对接配置（接口地址、认证方式等）存入 `tb_tool` 的 `api_config` 字段（TEXT/JSON），大模型不可见。

### `tb_mcp_server`（MCP 服务器）

管理 MCP Server 的连接配置，一个 Server 可提供多个工具。

| 列名 | 类型 | 必填 | 约束/说明 |
|------|------|------|-----------|
| `id` | BIGINT | 是 | PK |
| `server_name` | VARCHAR(255) | 是 | **全局唯一**，MCP Server 标识名，如 `jira-server`、`deepwiki` |
| `transport` | VARCHAR(255) | 是 | 传输方式：`sse` / `streamable_http` |
| `endpoint_url` | TEXT | 是 | MCP Server 的 URL 地址 |
| `headers` | TEXT | 否 | 请求头，JSON 字符串，如 `{"Authorization": "Bearer xxx"}` |
| `server_status` | VARCHAR(255) | 是 | 状态：`enabled` / `disabled`，默认 `enabled` |

### `tb_tool`（工具）

存储所有用户注册的工具（MCP 工具和 API 工具），系统内置工具不入库。

| 列名 | 类型 | 必填 | 约束/说明 |
|------|------|------|-----------|
| `id` | BIGINT | 是 | PK |
| `source` | VARCHAR(255) | 是 | 工具来源：`mcp` / `api` |
| `tool_name` | VARCHAR(255) | 是 | 工具名字（三要素之一），英文下划线命名，如 `jira_create_issue`、`wechat_notify`。同一来源下唯一 |
| `description` | TEXT | 是 | 工具描述（三要素之一），大模型根据此描述判断何时调用 |
| `parameters` | TEXT | 是 | 工具参数（三要素之一），JSON Schema 格式的参数定义，含每个参数的名字、类型、描述 |
| `tool_group` | VARCHAR(255) | 否 | 工具分组，用于平台分类管理，如 `notification`、`ops` |
| `risk_level` | VARCHAR(255) | 否 | 风险等级：`low` / `medium` / `high`，默认 `low` |
| `tool_status` | VARCHAR(255) | 是 | 状态：`enabled` / `disabled`，默认 `enabled` |
| `mcp_server_id` | BIGINT | 否 | 所属 MCP Server ID，仅 `source=mcp` 时有值 |
| `api_config` | TEXT | 否 | API 对接配置，仅 `source=api` 时有值，JSON 字符串，结构见下方说明 |

#### `api_config` 字段结构说明

仅 `source=api` 的工具使用此字段，存储 API 对接信息（大模型不可见）：

```json
{
  "url": "https://qyapi.weixin.qq.com/cgi-bin/message/send?corpid={{corp_id}}",
  "method": "POST",
  "headers": [
    { "key": "Authorization", "value": "Bearer {{api_token}}" },
    { "key": "Content-Type", "value": "application/json" }
  ],
  "body": "{\"touser\": \"{{touser}}\", \"msgtype\": \"{{msgtype}}\", \"text\": {\"content\": \"{{content}}\"}}"
}
```

| JSON 字段 | 说明 |
|-----------|------|
| `url` | HTTP URL，支持 `{{参数名}}` 引用工具参数进行模板替换 |
| `method` | 请求方法：`GET` / `POST` / `PUT` / `DELETE`，默认 `POST` |
| `headers` | 请求头键值对数组，每项含 `key` 和 `value`，value 支持 `{{参数名}}` 引用 |
| `body` | 请求体字符串，支持 `{{参数名}}` 引用工具参数。实际请求时通过工具调用参数进行 format 替换 |

> **参数引用语法**：URL、Headers、Body 中均可使用 `{{参数名}}` 引用工具的输入参数。平台在实际发起 HTTP 请求时，将 `{{参数名}}` 替换为大模型传入的对应参数值。

#### `parameters` 字段结构说明

所有工具统一使用 JSON Schema 格式存储参数定义，每个参数包含三要素（名字、类型、描述）：

```json
{
  "type": "object",
  "properties": {
    "touser":  { "type": "string", "description": "接收者用户 ID，多个用竖线分隔，@all 表示全员" },
    "msgtype": { "type": "string", "description": "消息类型", "enum": ["text", "markdown", "card"] },
    "content": { "type": "string", "description": "消息正文内容，msgtype 为 markdown 时支持 Markdown 语法" }
  },
  "required": ["touser", "msgtype", "content"]
}
```

## 技能管理

> 设计原则：
> - 技能（Skill）是工具的编排层，将指令说明和工具集合封装为一个可复用的能力单元。
> - 技能主表 `tb_skill` 存储技能本身的信息，技能说明（instruction）以 Markdown 文本存储。
> - 技能与工具的绑定关系通过 `tb_skill_tool` 中间表实现（多对多）。
> - 技能分类不建表，使用枚举字符串直接存储在 `tb_skill.category` 字段中。
> - 技能版本独立建表 `tb_skill_version`，记录每次发布的快照。

### 技能分类枚举

技能分类以字符串枚举形式存储在 `tb_skill.category` 字段中，不独立建表：

| 枚举值          | 显示名称 |
|--------------|---------|
| `text`       | 文本处理 |
| `retrieval`  | 信息检索 |
| `code`       | 代码与推理 |
| `data`       | 数据处理 |
| `multimodal` | 多模态 |
| `flow`       | 编排调度 |

> 枚举值由后端常量维护，前端通过接口获取可选列表。如需扩展分类，修改后端枚举常量即可。

### `tb_skill`（技能）

| 列名 | 类型 | 必填 | 约束/说明 |
|------|------|------|-----------|
| `id` | BIGINT | 是 | PK |
| `name` | VARCHAR(255) | 是 | 技能显示名称 |
| `description` | TEXT | 否 | 一句话描述 |
| `category` | VARCHAR(255) | 是 | 技能分类枚举值：`text` / `retrieval` / `code` / `data` / `multimodal` / `flow` |
| `instruction` | TEXT | 是 | 技能说明，Markdown 格式，定义执行步骤、输入输出、注意事项 |
| `skill_status` | VARCHAR(255) | 是 | 状态：`enabled` / `disabled` / `draft`，默认 `draft` |
| `current_version` | VARCHAR(255) | 否 | 当前版本号，如 `v1.3` |
| `create_time` | BIGINT | 是 | |
| `update_time` | BIGINT | 是 | |
| `create_user` | BIGINT | 否 | |
| `update_user` | BIGINT | 否 | |

### `tb_skill_tool`（技能-工具绑定）

技能与工具的多对多关系。一个技能可绑定多个工具，一个工具可被多个技能引用。

| 列名 | 类型 | 必填 | 约束/说明 |
|------|------|------|-----------|
| `id` | BIGINT | 是 | PK |
| `skill_id` | BIGINT | 是 | 技能 ID |
| `tool_id` | BIGINT | 是 | 工具 ID，关联 `tb_tool.id` |
| `tool_source` | VARCHAR(255) | 是 | 工具来源：`builtin` / `mcp` / `api`。内置工具无 `tb_tool` 记录，此时 `tool_id` 为 0，通过 `tool_name` 标识 |
| `tool_name` | VARCHAR(255) | 是 | 工具名字，冗余存储便于展示和内置工具引用 |
| `create_time` | BIGINT | 是 | |
| `update_time` | BIGINT | 是 | |
| `create_user` | BIGINT | 否 | |
| `update_user` | BIGINT | 否 | |

**唯一约束**：`(skill_id, tool_source, tool_name)` — 同一技能下不可重复绑定同名工具。

> 说明：内置工具由平台硬编码、不入 `tb_tool` 表，因此绑定内置工具时 `tool_id` 置为 0，通过 `tool_source='builtin'` + `tool_name` 标识。MCP / API 工具的 `tool_id` 指向 `tb_tool.id`。

### `tb_skill_version`（技能版本）

记录技能每次发布的版本快照，支持版本回溯。

| 列名 | 类型 | 必填 | 约束/说明 |
|------|------|------|-----------|
| `id` | BIGINT | 是 | PK |
| `skill_id` | BIGINT | 是 | 所属技能 ID |
| `version` | VARCHAR(255) | 是 | 版本号，如 `v1.0`、`v1.3` |
| `version_note` | TEXT | 否 | 版本说明 |
| `skill_snapshot` | TEXT | 否 | 发布时的技能完整快照，JSON 字符串 |
| `published_time` | BIGINT | 是 | 发布时间（Unix ms） |
| `create_time` | BIGINT | 是 | |
| `update_time` | BIGINT | 是 | |
| `create_user` | BIGINT | 否 | |
| `update_user` | BIGINT | 否 | |

#### `skill_snapshot` 字段结构说明

```json
{
  "name": "网页搜索",
  "description": "调用搜索引擎获取实时互联网信息",
  "category": "retrieval",
  "instruction": "## 执行步骤\n1. 接收用户查询关键词\n...",
  "tools": [
    { "tool_source": "builtin", "tool_name": "read_file" },
    { "tool_source": "mcp", "tool_name": "jira_create_issue", "tool_id": "1919810114514001" }
  ]
}
```