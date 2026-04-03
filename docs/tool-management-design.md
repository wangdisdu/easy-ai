# 工具管理功能详细设计

## 1. 功能概述

工具管理模块为智能体（Agent）提供可调用的外部能力。智能体在对话过程中可根据用户意图自主选择并调用已注册的工具，完成文件操作、内容搜索、外部系统交互等任务。

### 工具三要素

无论哪种来源，每个工具都必须具备以下三个要素，缺一不可：

| 要素 | 说明 | 对应大模型 tool_use 协议 |
|------|------|------------------------|
| **名字（name）** | 工具的唯一标识，英文下划线命名，大模型通过此名字引用和调用工具 | `name` 字段 |
| **描述（description）** | 工具的功能说明，大模型根据描述判断何时调用、如何理解返回结果 | `description` 字段 |
| **参数（parameters）** | 工具接受的输入参数定义，每个参数自身也有三要素（见下文） | `input_schema` 字段（JSON Schema） |

### 参数三要素

每个工具参数也必须具备三个要素：

| 要素 | 说明 | 对应 JSON Schema |
|------|------|-----------------|
| **名字（name）** | 参数的标识名，英文下划线命名。大模型根据名字理解语义并填入对应值 | `properties` 中的 key |
| **类型（type）** | 参数的数据类型，决定大模型传入什么格式的值 | `type` 字段 |
| **描述（description）** | 参数的用途说明，帮助大模型理解该传什么值、值的含义和约束 | `description` 字段 |

**支持的参数类型：**

| 类型 | JSON Schema `type` | 说明 | 示例值 |
|------|-------------------|------|--------|
| 字符串 | `string` | 文本值，最常用的类型 | `"hello"`、`"/data/report.csv"` |
| 整数 | `integer` | 整数值 | `42`、`0`、`-1` |
| 数值 | `number` | 浮点数 | `3.14`、`0.5` |
| 布尔 | `boolean` | true / false | `true`、`false` |
| 枚举 | `string` + `enum` | 限定可选值的字符串 | `"GET"`、`"POST"` |
| 对象 | `object` | 嵌套的 JSON 对象，需定义内部属性 | `{"key": "value"}` |
| 数组 | `array` | 列表，需通过 `items` 指定元素类型 | `["a", "b"]` |

**参数附加属性：**

除三要素外，参数还支持以下附加属性增强定义：

| 属性 | 说明 |
|------|------|
| 是否必填（required） | 标记该参数是否必须提供。必填参数列入 JSON Schema 的 `required` 数组 |
| 默认值（default） | 参数的默认值。有默认值的参数通常为非必填 |
| 枚举值（enum） | 限定参数的可选值范围，如 `["GET", "POST", "PUT"]` |

### 参数设计最佳实践

工具参数的设计质量直接影响大模型的调用准确率。以下是设计原则：

**命名（name）原则：**
- 使用有语义的英文命名，让大模型通过名字即可推测用途，如 `file_path` 而非 `fp`，`search_query` 而非 `q`
- 统一使用 `snake_case` 风格
- 同类参数在不同工具间保持命名一致，如文件路径统一用 `path`

**类型（type）原则：**
- 选择最精确的类型，如用 `integer` 而非 `string` 表示行号
- 有固定可选值时使用 `enum` 约束，如 HTTP 方法限定为 `["GET", "POST", "PUT", "DELETE"]`
- 布尔型参数用于开关语义，如 `recursive`、`replace_all`

**描述（description）原则：**
- 说明参数的**用途**，而非仅重复名字。好：`"搜索的正则表达式模式"`，差：`"pattern 参数"`
- 包含**格式要求**和**示例值**，如 `"glob 匹配模式，如 **/*.py、src/**/*.vue"`
- 注明**边界条件**，如 `"起始行号，从 0 开始"` 、`"最大读取行数，默认 2000"`
- 对于非必填参数，说明**省略时的行为**，如 `"搜索起始目录，省略时从工作区根目录开始"`

**整体结构原则：**
- 参数数量控制在 2–6 个，过多时考虑用 `object` 类型合并相关参数
- 必填参数排在前面，非必填参数排在后面
- 为非必填参数设置合理的默认值，降低调用门槛
- 避免参数间的隐式依赖关系，如需互斥逻辑应在描述中明确说明

**完整的参数定义示例（JSON Schema）：**

```json
{
  "type": "object",
  "properties": {
    "pattern": {
      "type": "string",
      "description": "正则表达式搜索模式"
    },
    "path": {
      "type": "string",
      "description": "搜索路径（文件或目录），省略时从工作区根目录开始"
    },
    "include": {
      "type": "string",
      "description": "文件过滤 glob 模式，如 *.py、*.{ts,tsx}"
    },
    "context_lines": {
      "type": "integer",
      "description": "匹配行前后显示的上下文行数",
      "default": 0
    }
  },
  "required": ["pattern"]
}
```

三种来源的工具获取三要素的方式不同：

| 来源 | 三要素来源 |
|------|-----------|
| 系统内置 | 平台硬编码，不可修改 |
| MCP 工具 | 从 MCP Server 探测自动获取（`tools/list` 返回） |
| 接口工具 | 用户在注册页面手动填写 |

### 工具分类

工具分为三类：

| 类型 | 来源标识 | 说明 | 是否可编辑 |
|------|----------|------|------------|
| 系统内置工具 | `builtin` | 平台预置的沙箱文件操作工具，随系统版本更新 | 不可编辑、不可删除、不可停用 |
| MCP 工具 | `mcp` | 通过 MCP（Model Context Protocol）协议对接的外部服务 | 可编辑、可停用 |
| 接口工具（API 集成） | `api` | 通过 HTTP API 对接的企业内部或第三方服务 | 可编辑、可停用 |

---

## 2. 工具列表页

### 2.1 页面布局

页面顶部为标题区（"工具管理"）和"添加工具"按钮，下方依次为搜索栏 + 分类筛选栏、工具卡片列表。

### 2.2 搜索与筛选

| 功能 | 说明 |
|------|------|
| 关键词搜索 | 按工具名称或描述进行模糊匹配 |
| 来源筛选 | Tab 按钮切换：全部 / 系统内置 / MCP 工具 / API 集成 |

两者可组合使用，同时生效。

### 2.3 工具卡片

每个工具以可展开的卡片形式展示。**折叠态**显示以下信息：

| 元素 | 说明 |
|------|------|
| 图标 | 按来源类型着色（内置绿 / MCP 紫 / API 青） |
| 名称 | 工具显示名称，如 `目录列表 (ls)` |
| 来源标签 | `系统内置` / `MCP 工具` / `API 集成`，带对应颜色 |
| 描述 | 工具功能的一句话描述 |
| 展开箭头 | 点击展开/收起详情 |

点击卡片进入**展开态**，根据工具来源类型展示不同的详情面板（见第 3–5 节）。

### 2.4 添加工具

点击右上角"添加工具"按钮，跳转到注册工具页面（见第 8 节）。仅可添加 MCP 工具和接口工具，内置工具不可手动添加。

---

## 3. 系统内置工具

### 3.1 概述

系统内置工具由平台预置，提供智能体在沙箱环境中操作文件系统的基础能力。用户**不可编辑、不可删除、不可停用**，仅可查看详情。

所有内置工具均在沙箱中运行，确保智能体的文件操作被限制在安全边界内。

### 3.2 工具清单（三要素总览）

| 名字（name） | 描述（description） | 参数（parameters） |
|-------------|--------------------|--------------------|
| `ls` | 列出指定目录下的文件和子目录 | `path`、`recursive`、`pattern` |
| `glob` | 按 glob 模式匹配文件路径 | `pattern`、`path` |
| `grep` | 在文件内容中搜索匹配指定正则表达式的行 | `pattern`、`path`、`include`、`context_lines` |
| `read_file` | 读取指定文件的内容 | `path`、`offset`、`limit` |
| `edit_file` | 对已有文件进行局部文本替换 | `path`、`old_text`、`new_text`、`replace_all` |
| `write_file` | 创建新文件或完整覆盖写入已有文件 | `path`、`content` |

### 3.3 工具详细说明

以下按三要素（名字、描述、参数）详细定义每个内置工具。每个参数均标注其三要素（名字、类型、描述）及附加属性。

#### 3.3.1 ls — 目录列表

- **名字**：`ls`
- **描述**：列出指定目录下的文件和子目录，用于智能体了解工作区的文件结构

**参数定义：**

| 名字（name） | 类型（type） | 描述（description） | 必填 | 默认值 |
|-------------|-------------|--------------------|----- |--------|
| `path` | `string` | 要列出的目录路径 | 是 | — |
| `recursive` | `boolean` | 是否递归列出子目录 | 否 | `false` |
| `pattern` | `string` | 文件名过滤模式，如 `*.log`、`*.py` | 否 | — |

**JSON Schema：**

```json
{
  "type": "object",
  "properties": {
    "path":      { "type": "string",  "description": "要列出的目录路径" },
    "recursive": { "type": "boolean", "description": "是否递归列出子目录", "default": false },
    "pattern":   { "type": "string",  "description": "文件名过滤模式，如 *.log、*.py" }
  },
  "required": ["path"]
}
```

**返回结构：**

```json
{
  "entries": [
    { "name": "src", "type": "directory", "size": null, "modified": "2026-04-01T10:00:00Z" },
    { "name": "main.py", "type": "file", "size": 2048, "modified": "2026-04-02T14:30:00Z" }
  ],
  "total": 2
}
```

#### 3.3.2 glob — 文件匹配

- **名字**：`glob`
- **描述**：按 glob 模式匹配文件路径，适合在不知道精确路径时快速定位文件

**参数定义：**

| 名字（name） | 类型（type） | 描述（description） | 必填 | 默认值 |
|-------------|-------------|--------------------|----- |--------|
| `pattern` | `string` | glob 匹配模式，如 `**/*.py`、`src/**/*.vue` | 是 | — |
| `path` | `string` | 搜索起始目录，省略时从工作区根目录开始 | 否 | 工作区根目录 |

**JSON Schema：**

```json
{
  "type": "object",
  "properties": {
    "pattern": { "type": "string", "description": "glob 匹配模式，如 **/*.py、src/**/*.vue" },
    "path":    { "type": "string", "description": "搜索起始目录，省略时从工作区根目录开始" }
  },
  "required": ["pattern"]
}
```

**返回结构：**

```json
{
  "matches": [
    "src/main.py",
    "src/utils/helper.py",
    "tests/test_main.py"
  ],
  "total": 3
}
```

#### 3.3.3 grep — 内容搜索

- **名字**：`grep`
- **描述**：在文件内容中搜索匹配指定正则表达式的行，支持上下文显示和文件类型过滤

**参数定义：**

| 名字（name） | 类型（type） | 描述（description） | 必填 | 默认值 |
|-------------|-------------|--------------------|----- |--------|
| `pattern` | `string` | 正则表达式搜索模式 | 是 | — |
| `path` | `string` | 搜索路径（文件或目录），省略时从工作区根目录开始 | 否 | 工作区根目录 |
| `include` | `string` | 文件过滤 glob 模式，如 `*.py`、`*.{ts,tsx}` | 否 | — |
| `context_lines` | `integer` | 匹配行前后显示的上下文行数 | 否 | `0` |

**JSON Schema：**

```json
{
  "type": "object",
  "properties": {
    "pattern":       { "type": "string",  "description": "正则表达式搜索模式" },
    "path":          { "type": "string",  "description": "搜索路径（文件或目录），省略时从工作区根目录开始" },
    "include":       { "type": "string",  "description": "文件过滤 glob 模式，如 *.py、*.{ts,tsx}" },
    "context_lines": { "type": "integer", "description": "匹配行前后显示的上下文行数", "default": 0 }
  },
  "required": ["pattern"]
}
```

**返回结构：**

```json
{
  "results": [
    {
      "file": "src/main.py",
      "line": 42,
      "content": "def process_data(input_data):",
      "context_before": ["", "# 数据处理函数"],
      "context_after": ["    if not input_data:"]
    }
  ],
  "total_matches": 1
}
```

#### 3.3.4 read_file — 文件读取

- **名字**：`read_file`
- **描述**：读取指定文件的全部或部分内容，返回带行号的文本，支持通过 offset 和 limit 分段读取大文件

**参数定义：**

| 名字（name） | 类型（type） | 描述（description） | 必填 | 默认值 |
|-------------|-------------|--------------------|----- |--------|
| `path` | `string` | 要读取的文件路径 | 是 | — |
| `offset` | `integer` | 起始行号，从 0 开始 | 否 | `0` |
| `limit` | `integer` | 最大读取行数 | 否 | `2000` |

**JSON Schema：**

```json
{
  "type": "object",
  "properties": {
    "path":   { "type": "string",  "description": "要读取的文件路径" },
    "offset": { "type": "integer", "description": "起始行号，从 0 开始", "default": 0 },
    "limit":  { "type": "integer", "description": "最大读取行数", "default": 2000 }
  },
  "required": ["path"]
}
```

**返回结构：**

```json
{
  "content": "1\tdef main():\n2\t    print('hello')\n3\t    return 0\n",
  "total_lines": 3,
  "truncated": false
}
```

#### 3.3.5 edit_file — 文件编辑

- **名字**：`edit_file`
- **描述**：对已有文件进行局部文本替换，无需重写整个文件。`old_text` 必须精确匹配文件中的内容

**参数定义：**

| 名字（name） | 类型（type） | 描述（description） | 必填 | 默认值 |
|-------------|-------------|--------------------|----- |--------|
| `path` | `string` | 要编辑的文件路径 | 是 | — |
| `old_text` | `string` | 要被替换的原始文本，必须与文件中的内容精确匹配 | 是 | — |
| `new_text` | `string` | 替换后的新文本 | 是 | — |
| `replace_all` | `boolean` | 是否替换所有匹配项。为 false 时要求 old_text 在文件中唯一 | 否 | `false` |

**JSON Schema：**

```json
{
  "type": "object",
  "properties": {
    "path":        { "type": "string",  "description": "要编辑的文件路径" },
    "old_text":    { "type": "string",  "description": "要被替换的原始文本，必须与文件中的内容精确匹配" },
    "new_text":    { "type": "string",  "description": "替换后的新文本" },
    "replace_all": { "type": "boolean", "description": "是否替换所有匹配项。为 false 时要求 old_text 在文件中唯一", "default": false }
  },
  "required": ["path", "old_text", "new_text"]
}
```

**返回结构：**

```json
{
  "success": true,
  "replacements": 1,
  "message": "已替换 1 处匹配"
}
```

#### 3.3.6 write_file — 文件写入

- **名字**：`write_file`
- **描述**：创建新文件或完整覆盖写入已有文件。目录不存在时自动创建

**参数定义：**

| 名字（name） | 类型（type） | 描述（description） | 必填 | 默认值 |
|-------------|-------------|--------------------|----- |--------|
| `path` | `string` | 文件路径，目录不存在时自动创建 | 是 | — |
| `content` | `string` | 要写入的完整文件内容 | 是 | — |

**JSON Schema：**

```json
{
  "type": "object",
  "properties": {
    "path":    { "type": "string", "description": "文件路径，目录不存在时自动创建" },
    "content": { "type": "string", "description": "要写入的完整文件内容" }
  },
  "required": ["path", "content"]
}
```

**返回结构：**

```json
{
  "success": true,
  "bytes_written": 1024,
  "message": "文件已写入"
}
```

### 3.4 展开详情面板

内置工具展开后以三要素为核心展示：

| 字段 | 对应要素 | 说明 |
|------|----------|------|
| 工具名字 | **名字** | 英文标识名，如 `read_file` |
| 功能描述 | **描述** | 工具功能的完整说明 |
| 参数列表 | **参数** | 各参数的名称、类型、是否必填、默认值、说明 |
| 版本 | — | 当前版本号 |
| 更新时间 | — | 最近更新日期 |

底部显示提示文字："系统内置工具，不可编辑"。

---

## 4. MCP 工具

### 4.1 概述

MCP 工具通过 [Model Context Protocol](https://modelcontextprotocol.io/) 协议连接外部 MCP Server，平台通过探测自动发现 Server 提供的工具列表并批量导入。适用于对接企业内部系统（Jira、GitLab、Confluence 等）和第三方 MCP 服务。

### 4.2 传输方式

平台支持两种 MCP 传输协议：

| 传输方式 | 协议 | 说明 |
|----------|------|------|
| **Server-Sent Events（SSE）** | HTTP + SSE | 客户端通过 HTTP POST 发送请求，服务端通过 SSE 流式推送响应。兼容性好，适合已有 SSE 实现的 MCP Server |
| **Streamable HTTP** | HTTP | MCP 协议最新推荐的传输方式。客户端和服务端均通过 HTTP 请求/响应通信，支持可选的 SSE 流式响应。更简洁、易部署 |

用户在注册时选择目标 MCP Server 支持的传输方式。

### 4.3 连接配置

| 字段 | 是否必填 | 说明 |
|------|----------|------|
| 服务器名称 | 必填 | 在系统中标识此 MCP Server 的唯一名称，如 `jira-server` |
| 传输方式 | 必填 | 选择 `Server-Sent Events` 或 `Streamable HTTP` |
| 端点 URL | 必填 | MCP Server 的 URL 地址 |
| 请求头 | 选填 | JSON 格式，用于传递 OAuth Token 或 API Key 等认证信息 |
| 默认风险等级 | 选填 | 批量导入时统一设置，导入后可逐个调整。默认 Low |

**示例 — DeepWiki 文档查询：**

| 字段 | 值 |
|------|-----|
| 服务器名称 | `deepwiki` |
| 传输方式 | Streamable HTTP |
| 端点 URL | `https://mcp.deepwiki.com/mcp` |
| 请求头 | 留空 |

探测后发现 3 个工具：`ask_question`、`read_wiki_contents`、`read_wiki_structure`

### 4.4 工具三要素与 MCP

MCP Server 通过 `tools/list` 接口返回的每个工具自带三要素，其中参数（`inputSchema`）中的每个参数也自带三要素（名字、类型、描述）：

```json
{
  "name": "jira_create_issue",                        // ← 工具名字
  "description": "在 Jira 中创建新工单。输入：项目 key、工单类型、标题、描述。输出：创建的工单 key 和 URL",  // ← 工具描述
  "inputSchema": {                                    // ← 工具参数
    "type": "object",
    "properties": {
      "project":   { "type": "string", "description": "项目 key，如 DEV" },        // 参数三要素：名字=project, 类型=string, 描述=...
      "issueType": { "type": "string", "description": "工单类型，如 Bug、Task",     // 参数三要素：名字=issueType, 类型=string, 描述=...
                     "enum": ["Bug", "Task", "Story", "Epic"] },                   // 附加属性：枚举约束
      "summary":   { "type": "string", "description": "工单标题" },
      "description": { "type": "string", "description": "工单详细描述，支持 Markdown 格式" }
    },
    "required": ["project", "issueType", "summary"]   // 附加属性：必填标记
  }
}
```

平台在探测阶段获取这些信息，导入后直接作为工具定义使用。用户可在导入后修改工具的描述和风险等级，但名字和参数由 MCP Server 定义，不建议修改。

### 4.5 注册流程

```
填写 Server 连接信息 → 点击"探测工具" → 查看发现的工具列表（含三要素） → 勾选需要的工具 → 点击"导入"
```

1. **填写连接信息**：选择传输方式（SSE / Streamable HTTP），填写端点 URL 和请求头
2. **探测工具**：点击"探测工具"按钮，系统临时连接 MCP Server，调用 `tools/list` 获取所有可用工具及其三要素
3. **选择工具**：探测结果以列表展示每个工具的名字、描述和参数概要，用户勾选需要导入的工具（可全选）
4. **批量导入**：点击"导入"，Server 配置和所选工具一并保存到系统中

### 4.6 展开详情面板

MCP 工具展开后按区域显示：

**连接信息区：**

| 字段 | 说明 |
|------|------|
| 服务器名称 | MCP Server 标识名 |
| 传输方式 | Server-Sent Events 或 Streamable HTTP |
| 风险等级 | Low / Medium / High（带颜色标签） |
| 端点 URL | MCP Server 的 URL 地址 |
| 请求头 | 认证头信息（脱敏显示） |

**已发现工具区（三要素展示）：**

列出从该 Server 探测到的所有工具，每个工具展示三要素：
- **名字**：工具函数名称，如 `jira_create_issue`，以标签形式展示
- **描述**：鼠标悬停或展开可查看完整描述
- **参数**：展开可查看参数的 JSON Schema 定义

**操作栏：**

| 操作 | 说明 |
|------|------|
| 编辑 | 跳转到编辑页面，修改 Server 连接配置 |
| 测试连接 | 验证 Server 连通性 |
| 查看日志 | 查看该工具的调用日志 |
| 启用 / 停用 | 切换工具可用状态。停用后智能体不可调用 |
| 更新时间 | 显示最近更新日期 |

---

## 5. 接口工具（API 集成）

### 5.1 概述

接口工具将企业已有的 HTTP API 注册为智能体可调用的工具。适用于对接不支持 MCP 协议的内部系统（企业微信、CMDB、ITSM、短信网关等）。

配置分为两个区域，体现**关注点分离**的设计：

- **工具定义**（大模型可见）：决定大模型看到什么、何时调用、传什么参数
- **API 对接**（大模型不可见）：决定平台如何将工具调用转换为实际的 HTTP 请求

### 5.2 工具定义（大模型可见） — 填写三要素

接口工具的三要素由用户手动填写，以下信息会作为 tool definition 发送给大模型：

| 字段 | 对应要素 | 是否必填 | 说明 |
|------|----------|----------|------|
| 工具名称 | **名字** | 必填 | 大模型调用时引用的标识，建议英文下划线命名，如 `wechat_notify`、`cmdb_query` |
| 功能描述 | **描述** | 必填 | 大模型判断"何时调用"和"如何理解结果"的核心依据。建议格式：**做什么 + 输入什么 + 返回什么**。例："向指定企业微信群或用户发送文本、Markdown 或卡片消息。输入：接收者 ID 和消息内容。输出：发送状态" |
| 输入参数 | **参数** | 必填 | 工具的输入参数定义。每个参数需包含三要素（名字、类型、描述）。支持两种录入方式：手动逐条添加，或粘贴 API 原始请求体 JSON 后点击"解析"自动生成 |
| 工具分组 | — | 选填 | 仅用于平台内分类管理（如 `notification`、`ops`），大模型不可见 |

### 5.3 API 对接（大模型不可见）

以下配置用于平台在运行时将大模型的工具调用转换为实际的 HTTP 请求，大模型不会看到这些信息。

| 字段 | 是否必填 | 说明 |
|------|----------|------|
| 接口地址 | 必填 | 完整的 HTTP API URL，如 `https://qyapi.weixin.qq.com/cgi-bin/message/send` |
| 请求方法 | 选填 | GET / POST / PUT / DELETE / PATCH，默认 `POST` |
| 认证方式 | 选填 | 四种认证方式之一（见 5.4 节），默认无认证 |
| 响应提取路径 | 选填 | JSONPath 表达式（如 `$.data.items`），从 API 返回的 JSON 中提取指定部分返回给大模型。留空则返回完整响应体 |
| 额外请求头 | 选填 | JSON 格式的自定义请求头（认证头由系统自动注入，此处仅填额外头） |
| 风险等级 | 选填 | Low / Medium / High，默认 Low |

### 5.4 认证方式

| 类型 | 说明 | 额外配置字段 |
|------|------|-------------|
| 无认证 | 不添加认证信息 | 无 |
| API Key | 通过自定义 Header 名称传递密钥 | **Header 名称**（如 `X-API-Key`、`X-Corp-Secret`）+ **Key 引用**（如 `vault://ops/cmdb_key`） |
| Bearer Token | 通过 `Authorization: Bearer <token>` 传递令牌 | **Token 引用**（如 `vault://service/bearer_token`） |
| OAuth 2.0 | OAuth 2.0 认证流程 | （待扩展） |

> 密钥统一通过 `vault://` URI 引用管理，不在配置中明文存储。格式：`vault://<namespace>/<key_name>`

### 5.5 展开详情面板

接口工具展开后分两个区域：

**工具定义区**（标注"大模型可见"）：

| 字段 | 说明 |
|------|------|
| 工具名称 | 英文标识名 |
| 工具分组 | 分类名称 |
| 风险等级 | Low / Medium / High（带颜色标签） |
| 功能描述 | 完整的功能描述文本 |
| 输入参数 | 参数列表，每个参数展示三要素（名字、类型、描述）及必填/默认值等附加属性 |

**API 对接区**（标注"大模型不可见"）：

| 字段 | 说明 |
|------|------|
| 接口地址 | HTTP API URL |
| 请求方法 | GET / POST / PUT / DELETE / PATCH |
| 认证方式 | 显示认证类型名称 |
| Header 名称 | 仅 API Key 模式显示 |
| Key 引用 | 密钥引用地址（脱敏显示） |
| 响应提取路径 | JSONPath 表达式 |
| 额外请求头 | 自定义请求头 |

**操作栏：**

| 操作 | 说明 |
|------|------|
| 编辑 | 跳转到编辑页面，修改工具定义和 API 对接配置 |
| 测试连接 | 输入测试参数，验证接口连通性和响应提取 |
| 查看日志 | 查看该工具的调用日志 |
| 启用 / 停用 | 切换工具可用状态 |
| 更新时间 | 显示最近更新日期 |

### 5.6 示例工具

#### 示例 1：企业微信通知（`wechat_notify`）

**工具三要素：**

- **名字**：`wechat_notify`
- **描述**：向指定企业微信群或用户发送文本、Markdown 或卡片消息。输入：接收者 ID 和消息内容。输出：发送状态
- **参数**：

| 名字（name） | 类型（type） | 描述（description） | 必填 | 默认值 |
|-------------|-------------|--------------------|----- |--------|
| `touser` | `string` | 接收者用户 ID，多个用竖线分隔，`@all` 表示全员 | 是 | — |
| `msgtype` | `string` | 消息类型 | 是 | — |
| `content` | `string` | 消息正文内容，msgtype 为 markdown 时支持 Markdown 语法 | 是 | — |

**API 对接**：`POST https://qyapi.weixin.qq.com/cgi-bin/message/send`，API Key 认证，风险 Low

#### 示例 2：CMDB 资产查询（`cmdb_query`）

**工具三要素：**

- **名字**：`cmdb_query`
- **描述**：根据条件查询 CMDB 中的资产记录，支持按 IP、主机名、标签筛选。输入：查询条件。输出：资产列表
- **参数**：

| 名字（name） | 类型（type） | 描述（description） | 必填 | 默认值 |
|-------------|-------------|--------------------|----- |--------|
| `type` | `string` | 资产类型 | 是 | — |
| `tag` | `string` | 资产标签，如 prod、staging | 否 | — |
| `ip` | `string` | 按 IP 地址精确匹配 | 否 | — |
| `hostname` | `string` | 按主机名模糊搜索 | 否 | — |
| `limit` | `integer` | 最大返回条数 | 否 | `20` |

**API 对接**：`POST https://cmdb-api.company.com/v2/assets/search`，API Key 认证，风险 Low

#### 示例 3：ITSM 工单系统（`itsm_ticket`）

**工具三要素：**

- **名字**：`itsm_ticket`
- **描述**：在 ITSM 系统中创建或查询工单，支持故障报修、变更申请、服务请求。输入：工单类型和内容。输出：工单 ID 和状态
- **参数**：

| 名字（name） | 类型（type） | 描述（description） | 必填 | 默认值 |
|-------------|-------------|--------------------|----- |--------|
| `action` | `string` | 操作类型 | 是 | — |
| `type` | `string` | 工单类型 | 是（action 为 create 时） | — |
| `title` | `string` | 工单标题 | 是（action 为 create 时） | — |
| `description` | `string` | 工单详细描述 | 否 | — |
| `ticket_id` | `string` | 工单 ID，查询时使用 | 是（action 为 query 时） | — |

**API 对接**：`POST https://itsm-api.company.com/v1/tickets`，API Key 认证，风险 Medium

#### 示例 4：短信网关（`sms_send`）

**工具三要素：**

- **名字**：`sms_send`
- **描述**：发送短信到指定手机号。输入：手机号和短信内容。输出：发送状态和消息 ID
- **参数**：

| 名字（name） | 类型（type） | 描述（description） | 必填 | 默认值 |
|-------------|-------------|--------------------|----- |--------|
| `phone` | `string` | 接收手机号，如 138xxxx0000 | 是 | — |
| `template` | `string` | 短信模板标识，如 verify_code、notification | 是 | — |
| `params` | `object` | 模板变量键值对，如 `{"code": "1234"}` | 否 | `{}` |

**API 对接**：`POST https://sms.company.com/v1/send`，API Key 认证，风险 High

---

## 6. 风险等级

所有 MCP 工具和接口工具均需配置风险等级，用于智能体调用时的安全控制：

| 等级 | 颜色 | 说明 | 调用策略 |
|------|------|------|----------|
| Low | 绿色 | 只读查询，无副作用 | 智能体可自主调用，无需用户确认 |
| Medium | 橙色 | 可修改数据，有副作用 | 调用前需用户确认 |
| High | 红色 | 高危操作（删除、支付、外发通知等） | 需审批流程通过后方可执行 |

> 系统内置工具不设风险等级，因其运行在沙箱中，操作范围受沙箱约束。

---

## 7. 工具状态

| 状态 | 显示 | 说明 |
|------|------|------|
| 运行中 | 绿色脉冲圆点 + "运行中" | 工具正常可用，智能体可调用 |
| 已停用 | 灰色圆点 + "已停用" | 工具已停用，智能体不可调用，不会出现在工具列表中 |

> 系统内置工具始终为"运行中"状态，不可停用。

---

## 8. 注册工具页面

### 8.1 页面结构

注册（添加）工具页面通过 Tab 切换两种模式：

| Tab | 说明 |
|-----|------|
| MCP 批量导入 | 连接 MCP Server，探测并批量导入工具 |
| 外部 API | 手动配置 HTTP API 注册为单个工具 |

编辑模式下 Tab 被锁定，不可切换工具类型。

### 8.2 MCP 批量导入

**页面布局：** 左侧为配置表单，右侧为示例参考卡片。

**表单字段：** 见第 4.3 节。

**操作按钮：**

| 按钮 | 说明 |
|------|------|
| 探测工具 | 连接 MCP Server 并列出可用工具 |
| 导入（新建模式） | 保存 Server 配置并导入选中工具 |
| 保存（编辑模式） | 更新 Server 配置 |
| 取消 | 返回工具列表 |

**右侧示例：**
- DeepWiki HTTP 远程服务示例

### 8.3 外部 API

**页面布局：** 左侧为双区表单（工具定义 + API 对接），右侧为连通性测试面板和示例卡片。

**工具定义区（大模型可见）：** 见第 5.2 节。

**API 对接区（大模型不可见）：** 见第 5.3 节。

**右侧面板：**

| 区域 | 说明 |
|------|------|
| 连通性测试 | 填写左侧配置后，输入测试参数点击"测试"按钮验证接口调用 |
| 示例参考 | 文本翻译工具的完整配置示例，展示所有字段的推荐填法 |

**操作按钮：**

| 按钮 | 说明 |
|------|------|
| 创建（新建模式） | 保存工具配置 |
| 保存（编辑模式） | 更新工具配置 |
| 取消 | 返回工具列表 |

### 8.4 编辑模式

从工具列表详情面板点击"编辑"进入编辑模式：

- Tab 切换被锁定，显示当前工具类型但不可切换
- 表单自动回填已有配置数据
- 提交按钮文案由"导入/创建"变为"保存"
