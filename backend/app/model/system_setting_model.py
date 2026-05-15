"""系统设置请求/响应模型。

平台级 KV 配置,key 命名空间见 docs/knowledge-rag-impl-plan.md §4 Step 1。
"""

from pydantic import BaseModel, Field


class SystemSettingResp(BaseModel):
    key: str
    value: str | None = None
    update_time: int | None = None


class SystemSettingUpsertReq(BaseModel):
    value: str | None = Field(default=None, max_length=4096)
