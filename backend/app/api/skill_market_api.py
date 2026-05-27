from fastapi import APIRouter, Depends, Query

from app.core.request_context import RequestContext, build_request_context
from app.core.response import Resp
from app.model.skill_market_model import (
    MarketInstallReq,
    MarketSearchResp,
    MarketSkillResp,
    MarketTranslateReq,
    MarketTranslateResp,
)
from app.model.skill_model import SkillResp
from app.service.skill_market_service import SkillMarketService

router = APIRouter(prefix="/skill-market", tags=["skill-market"])
service = SkillMarketService()


@router.get("/search", response_model=Resp[MarketSearchResp])
def search(q: str | None = Query(default=None, max_length=255)) -> Resp[MarketSearchResp]:
    return Resp(data=service.search(q=q))


@router.get("/{slug}", response_model=Resp[MarketSkillResp])
def inspect(slug: str) -> Resp[MarketSkillResp]:
    return Resp(data=service.inspect(slug=slug))


@router.post("/translate", response_model=Resp[MarketTranslateResp])
def translate(req: MarketTranslateReq) -> Resp[MarketTranslateResp]:
    return Resp(data=service.translate(req=req))


@router.post("/install", response_model=Resp[SkillResp])
def install(
    req: MarketInstallReq,
    req_ctx: RequestContext = Depends(build_request_context),
) -> Resp[SkillResp]:
    return Resp(data=service.install(req=req, req_ctx=req_ctx))
