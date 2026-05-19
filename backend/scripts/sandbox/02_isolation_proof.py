"""证明 execute 真的在沙盒容器里跑,不是宿主/backend 进程。"""

import subprocess
import time

from app.core.config import settings

settings.sandbox_enabled = True
settings.sandbox_server_url = "http://127.0.0.1:8090"
settings.sandbox_api_key = None

from app.app.sandbox.registry import get_sandbox_registry  # noqa: E402

reg = get_sandbox_registry()
APP = {"runtime_backend": "opensandbox", "sandbox": {"image": "python:3.11-slim"}}
b = reg.get_or_create(session_key="proof-1", app_config=APP)

marker = f"EASYAI-PROOF-{int(time.time())}"
r = b.execute(
    "echo '--- 沙盒内部视角 ---'; "
    "uname -s -m; "
    "echo hostname=$(hostname); "
    "head -1 /etc/os-release; "
    "echo PID1=$(cat /proc/1/cmdline | tr '\\0' ' '); "
    "grep -o 'docker[-/][0-9a-f]\\{12\\}' /proc/self/cgroup | head -1; "
    f"echo {marker} > /tmp/proof.txt; cat /tmp/proof.txt; "
    "python -c 'print(\"python:\", __import__(\"sys\").version.split()[0], 2**20)'"
)
print(r.output)
print("exit_code =", r.exit_code)

# 从宿主侧反向对照:同一时刻 docker 里那个 sandbox 容器
print("\n--- 宿主 docker 视角(同一时刻)---")
ps = subprocess.run(
    ["docker", "ps", "--filter", "network=easy-ai-sandbox",
     "--format", "{{.ID}} {{.Image}} {{.Names}} {{.Status}}"],
    capture_output=True, text=True,
)
print("docker ps:\n" + ps.stdout.strip())
cid = ps.stdout.split()[0] if ps.stdout.strip() else None
if cid:
    host_view = subprocess.run(
        ["docker", "exec", cid, "sh", "-c",
         "hostname; cat /tmp/proof.txt"],
        capture_output=True, text=True,
    )
    print(f"docker exec {cid} -> hostname + /tmp/proof.txt:\n{host_view.stdout.strip()}")

# backend 所在宿主(macOS)上有没有这个文件?
host_file = subprocess.run(["cat", "/tmp/proof.txt"], capture_output=True, text=True)
print("\n--- backend 宿主机 /tmp/proof.txt ---")
print("内容:", repr(host_file.stdout), "| stderr:", host_file.stderr.strip()[:60])

reg.release("proof-1")
print("\n[released] 沙盒已 kill")
