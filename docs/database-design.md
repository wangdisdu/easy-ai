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
