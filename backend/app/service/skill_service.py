import io
import json
import re
import zipfile

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.error_code import ErrorCode
from app.core.exceptions import ServiceError
from app.core.request_context import RequestContext
from app.core.snowflake import SnowflakeGenerator
from app.db.schema import TbSkill, TbSkillFile, TbSkillTool, TbSkillVersion
from app.model.skill_model import (
    SKILL_FILE_KINDS,
    SkillCreateReq,
    SkillFileItem,
    SkillFileResp,
    SkillPageReq,
    SkillPublishReq,
    SkillResp,
    SkillToolResp,
    SkillUpdateReq,
    SkillVersionResp,
)
from app.service.app_category_service import TARGET_SKILL, AppCategoryService

VALID_STATUSES = {"enabled", "disabled", "draft"}

# 首段目录 → kind 映射;rel_path 必须以这些目录之一开头
_DIR_TO_KIND: dict[str, str] = {
    "references": "reference",
    "scripts": "script",
    "templates": "template",
    "assets": "asset",
}

# Zip 上传安全上限
ZIP_MAX_COMPRESSED_BYTES = 10 * 1024 * 1024  # 10 MB 压缩
ZIP_MAX_UNCOMPRESSED_BYTES = 30 * 1024 * 1024  # 30 MB 解压总量,防 zip bomb
ZIP_MAX_FILE_BYTES = 5 * 1024 * 1024  # 5 MB 单文件
ZIP_MAX_FILES = 100  # 文件数

# 与 DeepAgents 内置 subagent 同名会顶替框架默认的 general-purpose 通用代理
# （见 deepagents/graph.py 的 insert 判定）。大小写不敏感地拦截。
RESERVED_SKILL_NAMES = frozenset({"general-purpose"})


def _validate_skill_name(name: str | None) -> None:
    if name is None:
        return
    if name.strip().lower() in RESERVED_SKILL_NAMES:
        raise ServiceError(
            ErrorCode.BAD_REQUEST,
            f"skill name '{name}' is reserved",
        )


def _to_int_ids(ids: list[str]) -> list[int]:
    return [int(x) for x in ids if str(x).strip()]


def _normalize_rel_path(rel_path: str) -> str:
    """规范化路径:strip,统一斜杠,去除前导/末尾斜杠。"""
    return rel_path.strip().replace("\\", "/").strip("/")


def _kind_of(rel_path: str) -> str:
    """从 rel_path 首段推导 kind。"""
    top = _normalize_rel_path(rel_path).split("/", 1)[0]
    if top not in _DIR_TO_KIND:
        raise ServiceError(
            ErrorCode.BAD_REQUEST,
            f"invalid skill file path '{rel_path}': "
            f"top-level dir must be one of {sorted(_DIR_TO_KIND)}",
        )
    return _DIR_TO_KIND[top]


_FRONTMATTER_RE = re.compile(r"^﻿?---\r?\n([\s\S]*?)\r?\n---\r?\n?", re.MULTILINE)


def _parse_frontmatter(text: str) -> dict[str, str]:
    """极简 YAML frontmatter 解析(仅 key: value 行,字符串值)。"""
    m = _FRONTMATTER_RE.match(text or "")
    if not m:
        return {}
    fm = m.group(1)
    meta: dict[str, str] = {}
    for line in fm.split("\n"):
        line = line.rstrip("\r")
        if not line.strip() or line.lstrip().startswith("#") or line.startswith((" ", "\t")):
            continue
        idx = line.find(":")
        if idx < 0:
            continue
        key = line[:idx].strip()
        val = line[idx + 1 :].strip()
        if (val.startswith('"') and val.endswith('"')) or (
            val.startswith("'") and val.endswith("'")
        ):
            val = val[1:-1]
        meta[key] = val
    return meta


def _validate_skill_file_path(rel_path: str) -> str:
    """校验文件路径合法性,返回规范化后的路径。

    禁止路径穿越(.. 段)、绝对路径、空路径。要求首段目录是 4 类之一。
    """
    if not rel_path or not rel_path.strip():
        raise ServiceError(ErrorCode.BAD_REQUEST, "skill file path cannot be empty")
    norm = _normalize_rel_path(rel_path)
    if not norm:
        raise ServiceError(ErrorCode.BAD_REQUEST, f"invalid skill file path '{rel_path}'")
    segments = norm.split("/")
    if any(seg in ("", ".", "..") for seg in segments):
        raise ServiceError(
            ErrorCode.BAD_REQUEST, f"skill file path '{rel_path}' contains illegal segment"
        )
    # 触发 kind 校验(同时验证首段目录)
    _kind_of(norm)
    if len(segments) < 2:
        raise ServiceError(
            ErrorCode.BAD_REQUEST,
            f"skill file path '{rel_path}' must include a filename under its category dir",
        )
    return norm


class SkillService:
    def __init__(self, id_generator: SnowflakeGenerator) -> None:
        self._id_generator = id_generator
        self._category_service = AppCategoryService(id_generator)

    # ── Helpers ──

    def _load_skill_tools(
        self, db: Session, skill_ids: list[int]
    ) -> dict[int, list[SkillToolResp]]:
        if not skill_ids:
            return {}
        rows = db.scalars(select(TbSkillTool).where(TbSkillTool.skill_id.in_(skill_ids))).all()
        result: dict[int, list[SkillToolResp]] = {}
        for row in rows:
            result.setdefault(row.skill_id, []).append(
                SkillToolResp(
                    tool_id=str(row.tool_id),
                    tool_source=row.tool_source,
                    tool_name=row.tool_name,
                )
            )
        return result

    def _sync_skill_tools(
        self, db: Session, skill_id: int, tools: list, now: int, user_id: int | None
    ) -> None:
        db.query(TbSkillTool).filter(TbSkillTool.skill_id == skill_id).delete()
        for t in tools:
            db.add(
                TbSkillTool(
                    id=self._id_generator.next_id(),
                    skill_id=skill_id,
                    tool_id=int(t.tool_id) if t.tool_id and t.tool_id != "0" else 0,
                    tool_source=t.tool_source,
                    tool_name=t.tool_name,
                    create_time=now,
                    update_time=now,
                    create_user=user_id,
                    update_user=user_id,
                )
            )

    def _load_skill_files(
        self, db: Session, skill_ids: list[int]
    ) -> dict[int, list[SkillFileResp]]:
        if not skill_ids:
            return {}
        rows = db.scalars(
            select(TbSkillFile)
            .where(TbSkillFile.skill_id.in_(skill_ids))
            .order_by(TbSkillFile.rel_path.asc())
        ).all()
        result: dict[int, list[SkillFileResp]] = {}
        for row in rows:
            result.setdefault(row.skill_id, []).append(SkillFileResp.from_entity(row))
        return result

    def _sync_skill_files(
        self,
        db: Session,
        skill_id: int,
        files: list[SkillFileItem],
        now: int,
        user_id: int | None,
    ) -> None:
        # 全量替换:先全删,再按规范化路径写入。重复路径 / 非法路径在此 raise。
        seen_paths: set[str] = set()
        prepared: list[tuple[str, str, str, bool]] = []  # (rel_path, kind, content, executable)
        for f in files:
            norm_path = _validate_skill_file_path(f.rel_path)
            if norm_path in seen_paths:
                raise ServiceError(
                    ErrorCode.BAD_REQUEST, f"duplicate skill file path '{f.rel_path}'"
                )
            seen_paths.add(norm_path)
            derived_kind = _kind_of(norm_path)
            kind = f.kind or derived_kind
            if kind not in SKILL_FILE_KINDS:
                raise ServiceError(ErrorCode.BAD_REQUEST, f"invalid skill file kind '{kind}'")
            # script 类默认 executable=True
            executable = f.executable or (derived_kind == "script")
            prepared.append((norm_path, kind, f.content, executable))

        db.query(TbSkillFile).filter(TbSkillFile.skill_id == skill_id).delete()
        for norm_path, kind, content, executable in prepared:
            db.add(
                TbSkillFile(
                    id=self._id_generator.next_id(),
                    skill_id=skill_id,
                    rel_path=norm_path,
                    kind=kind,
                    content=content,
                    executable=1 if executable else 0,
                    create_time=now,
                    update_time=now,
                    create_user=user_id,
                    update_user=user_id,
                )
            )

    # ── CRUD ──

    def create_skill(self, db: Session, req: SkillCreateReq, req_ctx: RequestContext) -> SkillResp:
        _validate_skill_name(req.name)
        now = req_ctx.request_time_ms
        entity = TbSkill(
            id=self._id_generator.next_id(),
            name=req.name,
            description=req.description,
            emoji=req.emoji,
            instruction=req.instruction,
            skill_status="draft",
            current_version=None,
            create_time=now,
            update_time=now,
            create_user=req_ctx.user_id,
            update_user=req_ctx.user_id,
        )
        db.add(entity)
        db.flush()
        if req.tools:
            self._sync_skill_tools(db, entity.id, req.tools, now, req_ctx.user_id)
        if req.files:
            self._sync_skill_files(db, entity.id, req.files, now, req_ctx.user_id)
        if req.category_ids is not None:
            self._category_service.sync_relations(
                db, TARGET_SKILL, entity.id, _to_int_ids(req.category_ids), req_ctx
            )
        db.commit()
        db.refresh(entity)
        tools_map = self._load_skill_tools(db, [entity.id])
        files_map = self._load_skill_files(db, [entity.id])
        refs_map = self._category_service.load_refs_map(db, TARGET_SKILL, [entity.id])
        return SkillResp.from_entity(
            entity,
            tools_map.get(entity.id, []),
            refs_map.get(entity.id, []),
            files_map.get(entity.id, []),
        )

    def page_skill(self, db: Session, req: SkillPageReq) -> tuple[list[SkillResp], int]:
        stmt = select(TbSkill)
        count_stmt = select(func.count(TbSkill.id))

        conditions = []
        if req.keyword:
            kw = f"%{req.keyword}%"
            conditions.append(or_(TbSkill.name.like(kw), TbSkill.description.like(kw)))
        if req.category_id:
            target_ids = self._category_service.target_ids_by_category(
                db, TARGET_SKILL, int(req.category_id)
            )
            if not target_ids:
                return [], 0
            conditions.append(TbSkill.id.in_(target_ids))
        if req.skill_status:
            conditions.append(TbSkill.skill_status == req.skill_status)

        for cond in conditions:
            stmt = stmt.where(cond)
            count_stmt = count_stmt.where(cond)

        total = db.scalar(count_stmt) or 0
        offset = (req.page_no - 1) * req.page_size
        rows = db.scalars(
            stmt.order_by(TbSkill.create_time.desc()).offset(offset).limit(req.page_size)
        ).all()

        skill_ids = [r.id for r in rows]
        tools_map = self._load_skill_tools(db, skill_ids)
        refs_map = self._category_service.load_refs_map(db, TARGET_SKILL, skill_ids)
        return [
            SkillResp.from_entity(r, tools_map.get(r.id, []), refs_map.get(r.id, [])) for r in rows
        ], total

    def get_skill_by_id(self, db: Session, skill_id: int) -> SkillResp:
        entity = db.get(TbSkill, skill_id)
        if not entity:
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, "skill not found")
        tools_map = self._load_skill_tools(db, [entity.id])
        files_map = self._load_skill_files(db, [entity.id])
        refs_map = self._category_service.load_refs_map(db, TARGET_SKILL, [entity.id])
        return SkillResp.from_entity(
            entity,
            tools_map.get(entity.id, []),
            refs_map.get(entity.id, []),
            files_map.get(entity.id, []),
        )

    def update_skill(
        self, db: Session, skill_id: int, req: SkillUpdateReq, req_ctx: RequestContext
    ) -> SkillResp:
        entity = db.get(TbSkill, skill_id)
        if not entity:
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, "skill not found")

        if req.name is not None:
            _validate_skill_name(req.name)
            entity.name = req.name
        if req.description is not None:
            entity.description = req.description
        if req.emoji is not None:
            # 空串表示清除 emoji
            entity.emoji = req.emoji or None
        if req.instruction is not None:
            entity.instruction = req.instruction

        now = req_ctx.request_time_ms
        if req.tools is not None:
            self._sync_skill_tools(db, skill_id, req.tools, now, req_ctx.user_id)
        if req.files is not None:
            self._sync_skill_files(db, skill_id, req.files, now, req_ctx.user_id)
        if req.category_ids is not None:
            self._category_service.sync_relations(
                db, TARGET_SKILL, skill_id, _to_int_ids(req.category_ids), req_ctx
            )

        entity.update_time = now
        entity.update_user = req_ctx.user_id
        db.commit()
        db.refresh(entity)
        tools_map = self._load_skill_tools(db, [entity.id])
        files_map = self._load_skill_files(db, [entity.id])
        refs_map = self._category_service.load_refs_map(db, TARGET_SKILL, [entity.id])
        return SkillResp.from_entity(
            entity,
            tools_map.get(entity.id, []),
            refs_map.get(entity.id, []),
            files_map.get(entity.id, []),
        )

    def delete_skill(self, db: Session, skill_id: int) -> None:
        entity = db.get(TbSkill, skill_id)
        if not entity:
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, "skill not found")
        db.query(TbSkillTool).filter(TbSkillTool.skill_id == skill_id).delete()
        db.query(TbSkillFile).filter(TbSkillFile.skill_id == skill_id).delete()
        db.query(TbSkillVersion).filter(TbSkillVersion.skill_id == skill_id).delete()
        self._category_service.delete_relations_for_target(db, TARGET_SKILL, skill_id)
        db.delete(entity)
        db.commit()

    def toggle_skill_status(
        self, db: Session, skill_id: int, status: str, req_ctx: RequestContext
    ) -> SkillResp:
        if status not in VALID_STATUSES:
            raise ServiceError(ErrorCode.BAD_REQUEST, f"invalid status: {status}")
        entity = db.get(TbSkill, skill_id)
        if not entity:
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, "skill not found")
        entity.skill_status = status
        entity.update_time = req_ctx.request_time_ms
        entity.update_user = req_ctx.user_id
        db.commit()
        db.refresh(entity)
        tools_map = self._load_skill_tools(db, [entity.id])
        files_map = self._load_skill_files(db, [entity.id])
        refs_map = self._category_service.load_refs_map(db, TARGET_SKILL, [entity.id])
        return SkillResp.from_entity(
            entity,
            tools_map.get(entity.id, []),
            refs_map.get(entity.id, []),
            files_map.get(entity.id, []),
        )

    # ── Publish ──

    def publish_skill(
        self, db: Session, skill_id: int, req: SkillPublishReq, req_ctx: RequestContext
    ) -> SkillVersionResp:
        entity = db.get(TbSkill, skill_id)
        if not entity:
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, "skill not found")

        tools_map = self._load_skill_tools(db, [entity.id])
        tool_list = tools_map.get(entity.id, [])
        files_map = self._load_skill_files(db, [entity.id])
        file_list = files_map.get(entity.id, [])
        category_ids = self._category_service.load_category_ids_map(
            db, TARGET_SKILL, [entity.id]
        ).get(entity.id, [])

        now = req_ctx.request_time_ms
        snapshot = json.dumps(
            {
                "name": entity.name,
                "description": entity.description,
                "emoji": entity.emoji,
                "category_ids": category_ids,
                "instruction": entity.instruction,
                "tools": [
                    {"tool_source": t.tool_source, "tool_name": t.tool_name, "tool_id": t.tool_id}
                    for t in tool_list
                ],
                "files": [
                    {
                        "rel_path": f.rel_path,
                        "kind": f.kind,
                        "content": f.content,
                        "executable": f.executable,
                    }
                    for f in file_list
                ],
            },
            ensure_ascii=False,
        )

        version = TbSkillVersion(
            id=self._id_generator.next_id(),
            skill_id=skill_id,
            version=req.version,
            version_note=req.version_note,
            skill_snapshot=snapshot,
            published_time=now,
            create_time=now,
            update_time=now,
            create_user=req_ctx.user_id,
            update_user=req_ctx.user_id,
        )
        db.add(version)

        entity.skill_status = "enabled"
        entity.current_version = req.version
        entity.update_time = now
        entity.update_user = req_ctx.user_id
        db.commit()
        db.refresh(version)
        return SkillVersionResp.from_entity(version)

    # ── Zip 上传创建 ──

    def create_skill_from_zip(self, db: Session, blob: bytes, req_ctx: RequestContext) -> SkillResp:
        """从 .zip 解压并创建技能。

        要求:
        - 根目录有 SKILL.md(含 YAML frontmatter: name + description)
        - 其他文件按首段路径归类:references/scripts/templates/assets/
        - 解压总大小不超过 ZIP_MAX_UNCOMPRESSED_BYTES
        - 文件数量不超过 ZIP_MAX_FILES
        - 拒绝路径穿越、绝对路径、单文件超大
        """
        if len(blob) > ZIP_MAX_COMPRESSED_BYTES:
            raise ServiceError(
                ErrorCode.BAD_REQUEST,
                f"zip too large: {len(blob)} bytes > {ZIP_MAX_COMPRESSED_BYTES}",
            )
        try:
            zf = zipfile.ZipFile(io.BytesIO(blob))
        except zipfile.BadZipFile as e:
            raise ServiceError(ErrorCode.BAD_REQUEST, f"invalid zip: {e}") from e

        names = [n for n in zf.namelist() if not n.endswith("/")]
        if len(names) > ZIP_MAX_FILES:
            raise ServiceError(
                ErrorCode.BAD_REQUEST, f"zip has too many files: {len(names)} > {ZIP_MAX_FILES}"
            )

        skill_md_content: str | None = None
        bundle_files: list[SkillFileItem] = []
        total_size = 0
        for name in names:
            info = zf.getinfo(name)
            if info.file_size > ZIP_MAX_FILE_BYTES:
                raise ServiceError(
                    ErrorCode.BAD_REQUEST, f"file '{name}' too large ({info.file_size} bytes)"
                )
            total_size += info.file_size
            if total_size > ZIP_MAX_UNCOMPRESSED_BYTES:
                raise ServiceError(
                    ErrorCode.BAD_REQUEST,
                    f"uncompressed total too large: {total_size} > {ZIP_MAX_UNCOMPRESSED_BYTES}",
                )
            norm = _normalize_rel_path(name)
            if not norm or any(seg in ("", ".", "..") for seg in norm.split("/")):
                raise ServiceError(ErrorCode.BAD_REQUEST, f"illegal path '{name}' in zip")

            data = zf.read(info)
            if norm.lower() == "skill.md":
                try:
                    skill_md_content = data.decode("utf-8")
                except UnicodeDecodeError as e:
                    raise ServiceError(ErrorCode.BAD_REQUEST, f"SKILL.md must be utf-8: {e}") from e
                continue

            # 其他文件必须落在 4 类目录之一
            top = norm.split("/", 1)[0]
            if top not in _DIR_TO_KIND:
                raise ServiceError(
                    ErrorCode.BAD_REQUEST,
                    f"file '{name}' not under one of {sorted(_DIR_TO_KIND)}/",
                )
            try:
                content = data.decode("utf-8")
            except UnicodeDecodeError as e:
                # 二进制 asset 暂不支持(MVP 期);明确报错而不是默写空串
                raise ServiceError(
                    ErrorCode.BAD_REQUEST, f"file '{name}' must be utf-8 text: {e}"
                ) from e
            bundle_files.append(SkillFileItem(rel_path=norm, content=content))

        if skill_md_content is None:
            raise ServiceError(ErrorCode.BAD_REQUEST, "zip must contain SKILL.md at top level")

        meta = _parse_frontmatter(skill_md_content)
        name = (meta.get("name") or "").strip()
        description = (meta.get("description") or "").strip() or None
        if not name:
            raise ServiceError(ErrorCode.BAD_REQUEST, "SKILL.md frontmatter must define 'name'")
        if not re.fullmatch(r"[a-z0-9-]{1,64}", name):
            raise ServiceError(
                ErrorCode.BAD_REQUEST,
                f"invalid skill name '{name}' (lowercase letters/digits/hyphens, 1-64 chars)",
            )

        req = SkillCreateReq(
            name=name,
            description=description,
            instruction=skill_md_content,
            files=bundle_files,
        )
        return self.create_skill(db, req, req_ctx)

    def list_skill_versions(self, db: Session, skill_id: int) -> list[SkillVersionResp]:
        entity = db.get(TbSkill, skill_id)
        if not entity:
            raise ServiceError(ErrorCode.DATA_NOT_FOUND, "skill not found")
        rows = db.scalars(
            select(TbSkillVersion)
            .where(TbSkillVersion.skill_id == skill_id)
            .order_by(TbSkillVersion.published_time.desc())
        ).all()
        return [SkillVersionResp.from_entity(r) for r in rows]
