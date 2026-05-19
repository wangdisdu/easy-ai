"""L0 冒烟:真实 SandboxRegistry + OpenSandboxBackend 打通真实 OpenSandbox server。
跑法:cd backend && SANDBOX_ENABLED=true uv run python /tmp/easyai_sandbox_smoke.py
"""

import sys

from app.core.config import settings

settings.sandbox_enabled = True
settings.sandbox_server_url = "http://127.0.0.1:8090"
settings.sandbox_api_key = None

from app.app.sandbox.registry import get_sandbox_registry  # noqa: E402

APP_CONFIG = {
    "runtime_backend": "opensandbox",
    "sandbox": {"image": "python:3.11-slim", "execute_timeout": 120},
}
SESSION = "smoke-1"
reg = get_sandbox_registry()
fail = []


def ck(name, cond, extra=""):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")
    cond or fail.append(name)


b = reg.get_or_create(session_key=SESSION, app_config=APP_CONFIG)
print("sandbox id =", b.id)
r = b.execute("echo hello-easyai && uname -s")
ck("execute", r.exit_code == 0 and "hello-easyai" in r.output, repr(r.output[:60]))
ck("exit code", b.execute("exit 7").exit_code == 7)
up = b.upload_files([("/tmp/s.txt", b"smoke-ok"), ("rel", b"x")])
ck("upload + invalid_path", up[0].error is None and up[1].error == "invalid_path")
ck("read back via shell", "smoke-ok" in b.execute("cat /tmp/s.txt").output)
dl = b.download_files(["/tmp/s.txt", "/tmp/none"])
ck("download roundtrip", dl[0].content == b"smoke-ok")
ck("missing -> file_not_found", dl[1].error == "file_not_found")
ck("same-session reuse", reg.get_or_create(session_key=SESSION, app_config=APP_CONFIG).id == b.id)
reg.release(SESSION)
try:
    b.execute("echo x")
    ck("killed after release", False, "still alive")
except Exception as e:
    ck("killed after release", True, type(e).__name__)

print("\nRESULT:", "ALL PASS" if not fail else f"FAIL={fail}")
sys.exit(1 if fail else 0)
