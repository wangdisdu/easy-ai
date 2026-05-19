"""隔离执行沙盒后端(OpenSandbox 接入)。

详见 docs/sandbox-design.md。当前为骨架:接 OpenSandbox SDK 前,
runtime_backend=opensandbox 会显式报错,默认 state 路径不受影响。
"""

from app.app.sandbox.opensandbox_backend import OpenSandboxBackend
from app.app.sandbox.registry import SandboxRegistry, get_sandbox_registry

__all__ = ["OpenSandboxBackend", "SandboxRegistry", "get_sandbox_registry"]
