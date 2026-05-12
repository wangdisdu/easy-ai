from fastapi import APIRouter
from pydantic import BaseModel

from app.core.permission import PERMISSION_DEFS
from app.core.response import Resp

router = APIRouter(prefix="/permission", tags=["permission"])


class PermissionOption(BaseModel):
    code: str
    label: str
    group: str
    description: str


@router.get("/options", response_model=Resp[list[PermissionOption]])
def list_permission_options() -> Resp[list[PermissionOption]]:
    return Resp(
        data=[
            PermissionOption(
                code=p.code, label=p.label, group=p.group, description=p.description
            )
            for p in PERMISSION_DEFS
        ]
    )
