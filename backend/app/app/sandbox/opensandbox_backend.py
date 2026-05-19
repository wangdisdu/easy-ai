"""OpenSandbox 隔离执行后端。

deepagents 的 ``BaseSandbox`` 已把 ls/grep/glob/edit/read/write 全部用 shell
命令派生,具体子类只需实现 4 个成员:``id`` / ``execute`` / ``upload_files``
/ ``download_files``。参考实现见
``deepagents/backends/langsmith.py`` 的 ``LangSmithSandbox``。

用 OpenSandbox 的**同步** SDK(``opensandbox.sync.SandboxSync``):``BaseSandbox``
的抽象方法本就是同步的,deepagents 的异步路径默认 ``asyncio.to_thread`` 包装
同步实现,因此不需要 async 桥。句柄由 :class:`SandboxRegistry` 注入并管生命周期。

设计依据 docs/sandbox-design.md §4.1。
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from deepagents.backends.protocol import (
    ExecuteResponse,
    FileDownloadResponse,
    FileUploadResponse,
)
from deepagents.backends.sandbox import BaseSandbox

logger = logging.getLogger(__name__)

# OpenSandbox 单条命令默认超时(秒)。未在 app_config 指定时使用;
# 与 settings.mcp_tool_timeout_seconds 同量级,避免一个慢命令卡住整轮 agent。
_DEFAULT_EXECUTE_TIMEOUT = 300


def _join_output(messages: Any) -> str:
    """OpenSandbox 的 logs.stdout/stderr 是 list[OutputMessage(.text)]。"""
    if not messages:
        return ""
    return "".join(getattr(m, "text", "") or "" for m in messages)


class OpenSandboxBackend(BaseSandbox):
    """包装一个已创建的 OpenSandbox ``SandboxSync`` 句柄。

    实例由 :class:`~app.app.sandbox.registry.SandboxRegistry` 按 thread_id
    复用创建,不要直接 new(否则会绕过生命周期与暖池治理)。
    """

    def __init__(
        self,
        *,
        sandbox: Any,
        sandbox_id: str,
        default_timeout: int = _DEFAULT_EXECUTE_TIMEOUT,
    ) -> None:
        """
        Args:
            sandbox: OpenSandbox ``SandboxSync`` 句柄(由 Registry 注入)。
            sandbox_id: 沙盒唯一 id,用于日志/审计关联。
            default_timeout: execute 未显式传 timeout 时的默认值(秒)。
        """
        self._sandbox = sandbox
        self._sandbox_id = sandbox_id
        self._default_timeout = default_timeout

    # -- SandboxBackendProtocol 必需成员 ----------------------------------

    @property
    def id(self) -> str:
        return self._sandbox_id

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        """在沙盒内执行 shell 命令。

        deepagents 会通过 ``execute_accepts_timeout`` 反射本方法签名,
        ``timeout`` kwarg 必须保留。
        """
        from opensandbox.models.execd import RunCommandOpts

        effective_timeout = timeout if timeout is not None else self._default_timeout
        execution = self._sandbox.commands.run(
            command,
            opts=RunCommandOpts(timeout=timedelta(seconds=effective_timeout)),
        )

        logs = getattr(execution, "logs", None)
        stdout = _join_output(getattr(logs, "stdout", None))
        stderr = _join_output(getattr(logs, "stderr", None))
        output = f"{stdout}\n{stderr}" if stdout and stderr else stdout or stderr

        return ExecuteResponse(
            output=output,
            exit_code=getattr(execution, "exit_code", None),
            truncated=False,
        )

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        """批量上传。协议要求**逐文件 try/except,允许部分成功**,不得整体抛异常。

        SDK 的 ``write_files`` 是一次性批处理(无单条结果),为满足协议的部分
        成功语义,这里逐条写、逐条兜底。
        """
        from opensandbox.models.filesystem import WriteEntry

        responses: list[FileUploadResponse] = []
        for path, content in files:
            if not path.startswith("/"):
                responses.append(FileUploadResponse(path=path, error="invalid_path"))
                continue
            try:
                self._sandbox.files.write_files([WriteEntry(path=path, data=content)])
                responses.append(FileUploadResponse(path=path, error=None))
            except Exception as e:  # noqa: BLE001 - 协议要求逐文件兜底
                logger.warning("[sandbox] upload failed path=%s: %s", path, e)
                responses.append(FileUploadResponse(path=path, error="permission_denied"))
        return responses

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        """批量下载。同样要求逐文件兜底、允许部分成功。"""
        from opensandbox.exceptions import SandboxException

        responses: list[FileDownloadResponse] = []
        for path in paths:
            if not path.startswith("/"):
                responses.append(
                    FileDownloadResponse(path=path, content=None, error="invalid_path")
                )
                continue
            try:
                content = self._sandbox.files.read_bytes(path)
                responses.append(FileDownloadResponse(path=path, content=content, error=None))
            except SandboxException as e:
                msg = str(e).lower()
                error = "is_directory" if "is a directory" in msg else "file_not_found"
                responses.append(FileDownloadResponse(path=path, content=None, error=error))
            except Exception as e:  # noqa: BLE001 - 协议要求逐文件兜底
                logger.warning("[sandbox] download failed path=%s: %s", path, e)
                responses.append(
                    FileDownloadResponse(path=path, content=None, error="file_not_found")
                )
        return responses
