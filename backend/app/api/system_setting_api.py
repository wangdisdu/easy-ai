"""系统设置 API。

读权限放开(任何登录用户都可以读),写权限留给前端做 `system:setting`
校验——后端这里不挂 permission middleware 以保持与权限设计文档一致
(M1.5 阶段权限走前端,后续 RBAC 强化时再加 require_permission)。
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.request_context import RequestContext, build_request_context
from app.core.response import Resp
from app.db.session import get_db
from app.model.system_setting_model import SystemSettingResp, SystemSettingUpsertReq
from app.service.system_setting_service import SystemSettingService

router = APIRouter(prefix="/system-setting", tags=["system-setting"])

service = SystemSettingService()


@router.get("", response_model=Resp[list[SystemSettingResp]])
def list_settings(db: Session = Depends(get_db)) -> Resp[list[SystemSettingResp]]:
    return Resp(data=service.list_all(db))


@router.get("/{key}", response_model=Resp[SystemSettingResp])
def get_setting(key: str, db: Session = Depends(get_db)) -> Resp[SystemSettingResp]:
    return Resp(data=service.get_resp(db, key))


@router.put("/{key}", response_model=Resp[SystemSettingResp])
def upsert_setting(
    key: str,
    req: SystemSettingUpsertReq,
    db: Session = Depends(get_db),
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[SystemSettingResp]:
    return Resp(data=service.set(db, key, req.value, req_ctx))
