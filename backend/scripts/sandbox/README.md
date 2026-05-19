# 沙盒回归脚本

本地手动回归沙盒/可视化/computer-use 用。是否纳入版本库由你决定(当前未提交)。

## 前置

1. OpenSandbox server 在跑:
   `cd deploy && docker compose -p easy-ai --profile sandbox up -d opensandbox-server`
2. 桌面镜像已构建(03/04/05 需要):
   `docker build -t easy-ai/sandbox-desktop:latest deploy/opensandbox/desktop`
3. 在 `backend/` 下用 venv 跑(脚本内部已临时打开 sandbox 开关,无需改 .env):
   `uv run python scripts/sandbox/<脚本>`

## 脚本

| 脚本 | 验什么 | 依赖 |
|---|---|---|
| `01_smoke.py` | SDK/网络/沙盒生命周期(create/execute/exit/upload/download/复用/release-kill) | server |
| `02_isolation_proof.py` | 命令真在隔离沙盒里跑(hostname=容器id、文件不落宿主等五证) | server |
| `03_desktop_e2e.py` | 桌面沙盒 + `desktop_endpoint` + noVNC `/vnc.html` 经代理可达 | server + 桌面镜像 |
| `04_desktop_browser_smoke.py` | 建「桌面(可视化)」镜像记录 + WebSocket RFB 握手;打印可直接浏览器打开的 URL | server + 桌面镜像 |
| `05_computeruse_e2e.py` | screenshot/move/type(中英)/key/click + 注入/越界/降级 | server + 桌面镜像 |
| `06_instance_mgmt_e2e.py` | 沙盒实例管理 service:list/view/kill 端到端 | server + 桌面镜像 |

判定看末行 `RESULT: ALL PASS` 与退出码;中途 SDK 打印的 traceback 多为预期负向用例(脚本已 catch)。

清理冒烟沙盒:`docker rm -f $(docker ps -q --filter 'name=sandbox-')`
