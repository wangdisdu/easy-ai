# backend-design 后端设计

## 技术栈

- **语言**: Python 3.12
- **Web 框架**: FastAPI + Pydantic + SQLAlchemy
- **认证**: JWT
- **AI Agent**: LangGraph + LangChain + DeepAgents + LiteLLM
- **数据库**: SQLite / PostgreSQL / MySQL

## 代码质量
- black
- ruff：忽略中文标点符号规则（RUF001、RUF002、RUF003）


## 模块设计

- `app/api`: API 接口层（FastAPI 的 `APIRouter`），如 `user_api.py`。只负责声明接口，不负责业务逻辑；业务逻辑由 service 层实现。
- `app/core`: 核心层，包含系统配置、统一日志、全局异常处理、加密解密、ID 生成器。
- `app/db`: 数据库层，包含 session 连接池与 ORM 表定义（`schema.py`，SQLAlchemy）。
- `app/service`: 业务逻辑层，如 `user_service.py`。

## 日志
使用统一的日志处理

## API Response

api返回统一的结构：Resp和PagedResp

```python
from pydantic import BaseModel, Field


class Resp[T](BaseModel):
    code: int = 0
    msg: str = "ok"
    data: T | None = None

class PagedResp[T](Resp[list[T]]):
    """分页列表：`data` 为当前页行列表，`total` 为符合条件的总条数。"""

    total: int
```

## ERROR CODE

统一业务错误码
INTERNAL_ERROR = 1000
BAD_REQUEST = 1001
UNAUTHORIZED = 1002
FORBIDDEN = 1003
DATA_NOT_FOUND = 1004
VALIDATION_FAILED = 1005
DATA_DUPLICATE = 1006

## id生成
- 使用Snowflake生成
- 起始时间戳1770000000000
- 所有api接口和前端使用id时，都应该用string格式，防止数字精度丢失
