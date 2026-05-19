# 沙盒方案设计(deepagents × OpenSandbox)

> 关联文档:[tool-approval-and-acl-design.md](./tool-approval-and-acl-design.md)、[long-session-design.md](./long-session-design.md)、[checkpoint-monitoring.md](./checkpoint-monitoring.md)、[system-architecture.md](./system-architecture.md)

## 1. 背景与目标

Agent 应用需要"在隔离环境里跑任意 shell / python / 装包 / 处理文件"的能力(代码解释器、数据分析、文件转换等)。本系统当前 Agent 运行时(`backend/app/app/`,基于 deepagents 0.5.3 + LangGraph)使用 `StateBackend` —— 文件只存在 LangGraph state 内存里,**没有真实执行环境**。

目标:接入 [alibaba/OpenSandbox](https://github.com/alibaba/OpenSandbox) 作为可选的隔离执行后端,且:

- 复用 deepagents 现成的 backend 抽象与 `execute` 工具自动暴露机制,**不改 prompt / 不新增工具注册**;
- 复用本系统已有的 `PolicyMiddleware`(ACL / HITL / 审计),**不在沙盒层另起一套权限**;
- 沙盒生命周期与现有 checkpoint / HITL / purge 机制对齐;
- per-app 可选开关,轻应用零成本(仍走 `StateBackend`)。

## 2. 两个能力面

### 2.1 deepagents 的 backend 抽象(接入点已预埋)

`deepagents/backends/protocol.py` 是分层的:

| 层 | 能力 | 本系统现状 |
|---|---|---|
| `BackendProtocol` | ls/read/write/edit/grep/glob/upload/download | `StateBackend`(内存,无 shell) |
| `SandboxBackendProtocol` | 上面 + `execute()/aexecute()` + `id` | 面向隔离环境 |
| `BaseSandbox`(ABC) | 全部文件操作由 `execute()`+`upload_files()` 派生 | **子类只需实现 4 个成员**,参考实现 `LangSmithSandbox` |

`BaseSandbox` 的具体子类只需实现:`id`(property)、`execute()`、`upload_files()`、`download_files()`。其余 ls/grep/glob/edit/read/write 由基类用 shell 命令自动派生。

**关键机制**:deepagents 的 `FilesystemMiddleware` 检测到 backend 是 `SandboxBackendProtocol` 时,会**自动向 agent 暴露一个 `execute` shell 工具**(`deepagents/middleware/filesystem.py`)。所以接上沙盒 backend,agent 即获得隔离执行能力,无需改任何 prompt 或工具注册。

本仓库 `backend/app/app/backend_factory.py` 的注释已写明"方便未来接入 OpenSandbox",`runtime_backend` 是预留开关,`agent_app.py` 取到 backend 后直接喂给 `create_deep_agent`。**接入点现成,缺的是沙盒 backend 实现 + 生命周期治理。**

### 2.2 OpenSandbox 形态

FastAPI lifecycle server + `execd` 执行守护 + ingress/egress 网关;Docker / K8s 运行时,可选 gVisor / Kata / Firecracker 强隔离;Python 异步 SDK(`commands.run()`、`sandbox.files`、context manager、超时、env、持久卷 PVC/OSSFS)。

两者咬合干净:`BaseSandbox.execute()` ↔ `commands.run()`,`upload_files()/download_files()` ↔ `sandbox.files`。

## 3. 总体架构

```
Agent(deepagents create_deep_agent)
  └─ FilesystemMiddleware ──自动暴露──> execute / write_file / read_file ...
       └─ PolicyMiddleware(本系统已有)── 对 execute 做 ACL / HITL / 审计 / tb_tool_audit
            └─ Backend(BackendFactory 按 app_config.runtime_backend 选择)
                 ├─ state        : StateBackend          (默认,无沙盒,轻应用)
                 ├─ opensandbox  : OpenSandboxBackend     (隔离执行)
                 └─ composite    : CompositeBackend       (混合,见 §6)
                       └─ SandboxRegistry(进程内单例)
                            ·按 thread_id 复用沙盒(跨 HITL 中断/恢复)
                            ·warm pool 预热
                            ·随 checkpoint purge 联动回收
```

设计原则:沙盒是 **per-app 可选的运行时后端**,不是全局开关;治理沿用 §5。

## 4. 核心实现

### 4.1 `OpenSandboxBackend(BaseSandbox)`

`backend/app/app/sandbox/opensandbox_backend.py`,只实现 4 个抽象成员,文件操作继承基类:

- `id` → registry 注入的 sandbox id
- `execute(command, *, timeout=None)` → `SandboxSync.commands.run(command, opts=RunCommandOpts(timeout=...))`,把 `execution.logs.stdout/stderr`(`list[OutputMessage].text`)拼成 `ExecuteResponse`,`exit_code` 直取;保留 `timeout` kwarg(deepagents 反射签名,见 `execute_accepts_timeout`)
- `upload_files` → `files.write_files([WriteEntry(path, data)])`(逐条写以满足协议部分成功);`download_files` → `files.read_bytes(path)` 返回 `bytes`;**逐文件 try/except,部分成功**

用 OpenSandbox **同步 SDK**(`opensandbox.sync.SandboxSync`):`BaseSandbox` 抽象方法本就是同步的,deepagents 异步路径默认 `asyncio.to_thread` 包装,无需 async 桥。SDK 符号惰性导入,仅沙盒路径加载,不拖累默认 `state` 部署。

### 4.2 `SandboxRegistry`:沙盒绑定到 thread

这是方案关键,必须与 checkpoint / HITL 对齐:

- **粒度**:一个 sandbox = 一个会话线程(`thread_id`)。
- **复用**:HITL 中断后 `resume_stream()` 会重建 agent(`agent_app.py` 每次 `_prepare` 新建 backend),沙盒**不能随 backend 对象销毁**。Registry 按 `thread_id` 查找复用,使中断/恢复落在同一沙盒。无 `thread_id`(一次性直 API)时每次新建、用完即弃。
- **回收**:与已有 checkpoint purge(`config.py` 的 `purge_ttl_days`)对齐 —— `thread_id` 的 checkpoint 被清理时联动 kill 沙盒;再加 OpenSandbox 侧 idle timeout 兜底。
- **暖池**:OpenSandbox 创建有冷启动开销,per-app 维护 warm pool 预热,降低首个 `execute` 延迟。

落在 `backend/app/app/sandbox/registry.py`,提供 `get_or_create / release / purge_hook / prewarm` 接口。`_create_handle` 实调 `SandboxSync.create`,`_kill_handle` 调 `kill()`。复用范围是**进程内**(`_by_thread`);多 worker / 重启后同 thread 落到别的进程会新建沙盒(旧的靠 idle timeout 回收),跨进程复用见 §8 步骤 7。

### 4.3 工厂改造

`BackendFactory.create(app_config, *, session_key=None)`:

- `state`(默认)→ `StateBackend()`,行为不变;
- `opensandbox` → 经 `SandboxRegistry` 取/建沙盒,包成 `OpenSandboxBackend`;
- `composite` → `CompositeBackend`(§6)。

`agent_app.py` 调用处把 `req.thread_id` 作为 `session_key` 传入。

## 5. 安全治理(复用 + 强化)

| 关注点 | 方案 |
|---|---|
| `execute` 工具风险 | `execute` 是 deepagents `FilesystemMiddleware` 注入的**框架内置工具**,不是 api/mcp 工具,`PolicyMiddleware` 默认对它透传不治理。本系统的做法:在 `tb_tool` 落一条 `source='builtin'` 的治理记录(迁移 `0016` 种入,`execute`=high、`write_file`/`edit_file`=medium),`agent_app._governed_builtin_metadata` 把它们的 name→id/risk/hitl 并入 `PolicyMiddleware` 的 `name_to_id`,从而**复用同一套 ACL+HITL+`tb_tool_audit` 审计**,中间件本身零改动。仅沙盒后端(`opensandbox`/`composite`)启用,`state` 后端维持原透传不引入新 HITL 打扰。详见 tool-approval-and-acl-design.md |
| 进程/FS 隔离 | OpenSandbox 容器隔离;敏感 app 启用 gVisor / Kata / Firecracker |
| 出网 | 默认 **egress deny**,按 app 白名单放行(防数据外泄 / SSRF);ingress 不暴露 |
| 数据面 | per-app/per-user 持久卷(PVC/OSSFS),app 间不共享卷,租户隔离 |
| 资源 | 每沙盒 CPU/内存/超时上限;`execute` timeout 复用 `mcp_tool_timeout_seconds` 同源量级 |
| 凭证 | 沙盒内**不注入**平台 JWT/DB 凭证;需数据访问仍走 MCP 工具回平台,保持现有 ACL 边界 |

## 6. 混合后端(进阶,可选)

`CompositeBackend` 按路径前缀路由:`/workspace/**` → OpenSandbox(可执行),`/memory/**` → StateBackend/StoreBackend(快、随 checkpoint 持久)。让"长期记忆/草稿"留在状态层,"跑代码"才进沙盒,兼顾性能与成本。

## 7. 配置与部署

App 级配置(`app_config`)新增:

| 键 | 说明 |
|---|---|
| `runtime_backend` | `state`(默认) / `opensandbox` / `composite` |
| `sandbox.image_id` | 从镜像目录(`tb_sandbox_image`)选的镜像 id;不填用 `is_default` 那条 |
| `sandbox.egress_allow` | 出网白名单(域名/CIDR 列表) |
| `sandbox.idle_timeout` | 空闲回收秒数 |
| `sandbox.resources` | `{cpu, memory}`,由所选镜像的 `cpu`/`memory` 解析注入,透传 OpenSandbox `create(resource=...)` |

> 运行时统一 docker(server 端 `[runtime] type=docker`),不做 per-image 运行时选择。

### 7.1 镜像目录 `tb_sandbox_image`

平台级镜像白名单,管理员维护,Agent 应用只能从中选一个,避免任意镜像注入。

| 字段 | 说明 |
|---|---|
| `name` | 显示名,全局唯一 |
| `image` | 容器镜像引用(如 `python:3.12-slim` 或私有仓库路径) |
| `cpu` / `memory` | 默认资源画像(如 `cpu="1"`、`memory="2Gi"`);空=不限,透传 OpenSandbox |
| `is_default` | 全局至多一条;app 未选时兜底 |
| `enabled` | 软上下架;`list` 接口只返回启用的供选择 |

- 标准 REST:`GET /api/v1/sandbox-image/page`、`/list`、`POST`、`GET/PUT/DELETE /{id}`。
- 解析时机:`agent_app._prepare` 仅当 `runtime_backend ∈ {opensandbox, composite}` 时调
  `SandboxImageService.resolve_image(db, app_config)`,把 `image_id` → 实际镜像注入本次
  运行态的 `app_config["sandbox"]["image"]`(不持久化),`SandboxRegistry._create_handle`
  据此建沙盒。配置了不存在/停用的 `image_id` 显式报错,不静默回退。
- `state` 后端不触发上述 DB 查询,零开销。

全局配置(`config.py` `Settings`)新增 `sandbox_*` 系列(server URL / api key / 默认超时 / 暖池大小),已落骨架字段。

部署:OpenSandbox lifecycle server 作为一个服务进 `deploy/` 的 docker-compose,与 RAGFlow/Flowise/Langfuse 同构(本系统本就是 federated 多服务架构)。`pyproject.toml` 增加 OpenSandbox Python SDK 依赖。

## 8. 落地步骤

1. ✅ `BackendFactory` 增加 `opensandbox` / `composite` 分支 + `session_key` 参数。
2. ✅ `OpenSandboxBackend` + `SandboxRegistry` **实际接入 OpenSandbox 同步 SDK**(`opensandbox==0.1.9`,`pyproject.toml` 已加依赖):`SandboxSync.create/kill`、`commands.run`(`RunCommandOpts.timeout`)、`files.write_files`/`read_bytes`。`ConnectionConfigSync` 从 `settings.sandbox_server_url`/`sandbox_api_key` 组装;keep-alive entrypoint `tail -f /dev/null` 让容器常驻供 shell 派生。
3. ✅ `agent_app.py` 会话结束/异常路径回收沙盒;`_delete_checkpoint_thread` 接 purge 钩子。
4. ✅ `source='builtin'` 治理记录(迁移 `0016`)+ `agent_app` 把内置写/执行工具元数据并入 `PolicyMiddleware`(仅沙盒后端),复用现有 ACL+HITL+审计。
5. ✅ docker-compose 服务(`deploy/docker-compose.yml` 的 `opensandbox-server`,profile `sandbox`)+ `deploy/opensandbox/config.toml`。
6. **沙盒出网管控**:当前沙盒可随意联网(数据外泄 / SSRF 风险),目标改为默认拒绝、仅放行白名单 `egress_allow`(域名/CIDR),翻译成 OpenSandbox `NetworkPolicy` 下发。⏳ 待核实 `NetworkPolicy` 字段并在真实部署验证,未做(不影响功能,是安全收紧)。
7. **多副本生产优化**:(a) 暖池——提前预热空闲沙盒,消除首次 `execute` 的冷启动等待(现 `prewarm` 为空实现);(b) 跨进程复用——把 `sandbox_id` 持久化(随 checkpoint),换 backend 进程时用 `SandboxSync.resume` 重连原沙盒,否则多副本下同一会话会重建新沙盒。⏳ 单进程开发够用,扩容阶段再做。
8. 可视化沙盒:✅ Tier 1/2/3 全部落地并端到端验证(noVNC 桌面 + computer-use 操控)。详见 [§9 可视化沙盒](#9-可视化沙盒)。

> 步骤 1–5 已完成并**端到端验证通过**(真实 OpenSandbox server + 真实 `SandboxRegistry`/`OpenSandboxBackend`:create / execute / exit code / upload / download / 同会话复用 / release-kill 全 PASS)。`settings.sandbox_enabled=False`(默认)时不打网络、不影响默认 `state` 路径。

### 8.1 部署拓扑(docker-out-of-docker,端到端验证得出)

OpenSandbox server 在容器里,经挂载的宿主 `docker.sock` 在**宿主 Docker** 上拉 sandbox 容器。两个坑(已在代码/compose 固化):

1. **SDK 必须走 server 代理**:backend 到不了临时 sandbox 的 bridge IP。`registry._connection_config` 固定 `use_server_proxy=True`,SDK→server→sandbox。
2. **server 与 sandbox 必须同网**:否则 server(compose 网)连不到 sandbox(宿主 bridge)。compose 声明固定名网络 `easy-ai-sandbox`,`opensandbox-server` 接入它,`config.toml` 的 `[docker] network_mode = "easy-ai-sandbox"` 让 server 经 docker.sock 拉起的 sandbox 也接入同网。

启用(一条命令):`deploy/.env` 置 `SANDBOX_ENABLED=true` → `./deploy.sh up`。脚本检测开关 → 自动加 `--profile sandbox` → compose 一并启 `opensandbox-server` 与 `sandbox-desktop`(本地构建可视化镜像,`build: ./opensandbox/desktop` + tag `easy-ai/sandbox-desktop:latest`)→ backend 启动时迁移 `0018_seed_sandbox_image` 自动落一条 `is_default` 的"桌面(可视化)"镜像 → 应用配置勾「启用沙盒」直接选它即可。

**api_key 注入**:`SANDBOX_API_KEY` 由容器 entrypoint 用 sed 在 `config.template.toml` 上做条件替换:非空 → 替占位符为真值且服务端强制鉴权;为空 → 删除 `api_key` 行 + `SANDBOX_INSECURE=YES` 走 insecure 模式(仅本机/受信网络)。backend SDK 走 `SANDBOX_API_KEY` 同源,无需额外配置。生产**强烈建议**设 32+ 字符强密钥。

## 9. 可视化沙盒

参照 Manus / Devin / Operator / Anthropic computer-use:让用户在会话页**实时看到**沙盒里命令执行、Ubuntu 桌面、浏览器操作,甚至让 Agent 直接操控 GUI。它不是单一技术,是三层叠加:

| 层 | 作用 | 选型 | 本系统现状 |
|---|---|---|---|
| ① 隔离 | 每会话一个隔离环境 | Docker(弱)/ Firecracker·Kata microVM(强,即所谓"虚拟机") | ✅ 已有(§4) |
| ② 桌面 + 串流 | 把容器内画面推到用户浏览器 | noVNC | ✅ **Tier 2 已实现**(见 §9.4) |
| ③ Agent 操控 | 模型截图→决策→点按打字 | computer-use 工具集(scrot + xdotool) | ✅ **Tier 3 已实现**(见 §9.5) |

### 9.1 串流层选型(②)

容器内:`Xvfb`(虚拟显示器)+ 轻量窗管 + Chromium + `x11vnc`。串流三选一:

- **noVNC + websockify**:VNC→WebSocket,前端 `iframe` 直接看桌面。最简单、最通用(E2B Desktop / browser-use / Anthropic computer-use demo 同款)。**推荐起步**。
- **WebRTC**(Neko / Kasm):低延迟高画质,复杂度高,适合后续体验升级。
- **CDP screencast**:只需"看浏览器"时,headed Chrome `Page.screencast` 推画面,不要整桌面(Browserbase / Steel 同款)。

终端"看命令执行"独立且最轻:execd 已流式返回 stdout/stderr(`commands.run`),前端 `xterm.js` 接上即可,不依赖桌面。

### 9.2 与本系统的接入点

OpenSandbox 已预留端口暴露能力(`SandboxSync.get_endpoint / get_signed_endpoint`、`SandboxEndpoint`、`secure_access`、`[ingress]`),正是可视化的入口:

1. **桌面镜像**:做一个 Xvfb + WM + Chromium + x11vnc + noVNC 的镜像(或复用 E2B / computer-use 现成镜像),在 §7.1「沙盒管理」里就是一条镜像记录。
2. **暴露端口**:`OpenSandboxBackend` / `registry` 用 `get_signed_endpoint(<noVNC端口>)` 取带签名的临时 URL。
3. **前端面板**:会话页加一块——`iframe` 嵌 noVNC URL(看桌面)+ `xterm.js` 接命令流(看终端)。
4. **(可选,大头)操控**:加 computer-use 工具(screenshot/click/type),Agent 才能"操作"而非仅"被看";仍走 §5 的 PolicyMiddleware HITL/审计(高危操作人工确认)。

### 9.3 工作量梯度与边界

- **只看终端**(命令流 → xterm.js):最小,几乎零新基建。
- **看桌面/浏览器**(noVNC iframe + 签名 URL):中等,核心是桌面镜像 + 端口签名暴露 + 前端面板。
- **Agent 操控桌面**(computer-use):最大,基本是另立能力模块,需视觉模型 + 动作工具 + 治理接入。

建议按"终端 → 桌面 → 操控"分期推进。

### 9.4 Tier 2 实现(noVNC 桌面,✅ 已落地并端到端验证)

- **桌面镜像** `deploy/opensandbox/desktop/`:`Dockerfile`(Debian + Xvfb + fluxbox + Chromium + x11vnc + noVNC/websockify + `fonts-noto-cjk`/emoji 字体,否则网页中文显示为方块;非 root `app` 用户跑浏览器)+ 幂等 `start-desktop.sh`(各守护 `setsid` 脱离 exec 会话,pgrep 守卫可重复调用)。apt 源换阿里云镜像(deb.debian.org 不稳)。本地构建即可(OpenSandbox 用宿主 docker,免 push):`docker build -t easy-ai/sandbox-desktop:latest deploy/opensandbox/desktop`。在 §7.1「沙盒管理」建一条 `image=easy-ai/sandbox-desktop:latest` 的镜像记录,应用启用沙盒时选它。
  - **Chromium 沙盒/警告条**:OpenSandbox 受限运行时禁用了非特权 user namespace 且 `no_new_privileges=true`(SUID sandbox 也不可用),Chromium 必须 `--no-sandbox`(否则 `No usable sandbox` 崩),非 root 也救不了;改用 `--test-type` 抑制由此产生的黄色 "unsupported command-line flag" 警告条。浏览器仍以非 root `app` 用户运行作纵深防御。
- **后端** `SandboxRegistry.desktop_endpoint(session_key)`:沙盒不存在→`None`(前端提示未就绪);存在则经 execd 跑 `start-desktop.sh` 拉起桌面栈,再 `get_endpoint(6080)` 取代理 URL(补全 scheme)。API:`GET /api/v1/sandbox-view?thread_id=`(登录态),返回 `{ready,url,headers}`。
- **前端** `AppDetailView.vue` 测试抽屉:应用启用沙盒(`app_config.runtime_backend!='state'`)时显示「沙盒桌面」按钮(需先发起对话拿到 `thread_id`),点开弹 `a-modal` 内嵌 noVNC `iframe`,轮询直到 `ready`;noVNC `path` 参数指向同一代理前缀的 `websockify`,关闭即清空 iframe 断连。
- **关键约束**:`get_signed_endpoint`(带过期 token 的签名 URL)**仅 Kubernetes runtime 支持**;docker runtime 报 `Signed routes ... not supported`,故用 `get_endpoint`(经 lifecycle server 代理),访问控制依赖 server `api_key` / 网络边界。生产上 K8s runtime 可切回签名 URL。
- **安全**:桌面镜像同样走 §7.1 白名单;egress 默认拒绝(§5,⏳);非 K8s 下无 URL 级过期,需靠 server 鉴权 + 网络隔离收口。
- **端到端验证**:真实 registry 建桌面沙盒 → `desktop_endpoint` 拉起 → `/vnc.html` 经 server 代理 200 且含 noVNC,全 PASS。WebSocket 实流建议浏览器侧再冒烟一次。

> 终端档(xterm.js)未单独做:桌面里本就能开终端看命令。

### 9.5 Tier 3 实现(computer-use 操控,✅ 已落地并端到端验证)

让 Agent 看截图并点按/输入,真正操控 §9.4 的桌面。

- **桌面镜像**追加 `xdotool`(键鼠注入)+ `scrot`(截图)。
- **工具** `app/app/computer_tools.py` `build_computer_tools(session_key)`:`screenshot / click / double_click / right_click / move_mouse / scroll / type_text / press_key`,经 `registry.exec_in_session` 在该会话沙盒里跑 `scrot`/`xdotool`(`DISPLAY=:1`)。沙盒不存在→提示串(模型自愈)。与 memory_tools 同样的会话闭包注入。
- **截图回传**:`screenshot` 返回 `[{text},{image_url:data:image/png;base64}]` 多模态内容块,供视觉模型直接看;**需模型支持 tool_result 图片**(如 Claude via LiteLLM)。非视觉模型则盲操,但用户仍可在 §9.4 noVNC 面板看到画面。
- **接线** `agent_app._prepare`:仅当沙盒后端 **且** `app_config.sandbox.computer_use` 为真才挂载;工具随 thread 绑定。
- **治理**:迁移 `0017` 以 `source='builtin'` 把这些工具种入 `tb_tool` —— `screenshot`/`move_mouse`=low(放行),`click/type/key/scroll` 等改动类=high,复用 §5 PolicyMiddleware **走 HITL 人工确认 + `tb_tool_audit`**;`_governed_builtin_metadata` 自动覆盖,无需额外接线。
- **前端** `AppFormView`「启用沙盒」下复选「允许 Agent 操控桌面」→ `app_config.sandbox.computer_use`。
- **健壮性**:文本/按键 token 化注入(`type_text` 转 Unicode keysym 逐字符 `xdotool key`,解决 xdotool 对中文/多字节 `type` 报错;`press_key` 白名单正则防注入;坐标越界拦截)。
- **端到端验证**:真实桌面沙盒里 `screenshot` 返回合法 PNG、`move_mouse` 经 `xdotool getmouselocation` 实测生效、`type_text`(中英)、`press_key`、注入/越界/无沙盒降级全 PASS。

> Tier 1/2/3 全部落地。computer-use 是否启用由 app 显式开关控制,默认关闭。

## 10. 剩余事项

功能本身已闭环,下面是"上生产 / 上规模 / 上合规"才会撞到的事,按优先级列出。每条注明**做什么 / 不做的后果**,先看后果再决定是否排期。

### 10.1 安全收紧

**(a) 沙盒出网管控**(已在 §5/§8 标 ⏳)
- **做什么**:默认不让沙盒里的命令随意访问外网,只允许白名单里的域名/网段(如 `pypi.org`、公司内网 API)。
- **不做**:Agent 跑的可能是模型生成的命令,有人诱导它把数据 `curl` 到外部,或者从沙盒里探内网 → **数据外泄 / SSRF 风险**。当前是放开的。

**(b) Docker 控制接口的权限收口**
- **做什么**:OpenSandbox server 现在挂了宿主的 docker 控制套接字,等于给了它"操作整台宿主 Docker"的能力。生产应换成只允许必要操作的代理(docker-socket-proxy),或迁移到 K8s runtime。
- **不做**:容器逃逸 / 一旦 server 被攻破,**等同于宿主 root**。内部 / 受信环境影响小,合规审计会卡。

**(c) OpenSandbox server 自身资源限制**
- **做什么**:在 compose 给 `opensandbox-server` 加 CPU/内存上限。
- **不做**:server 失控或被压垮时**可能拖垮宿主**。沙盒容器本身的资源画像已经能在镜像里设(§7.1 的 `cpu`/`memory`),这条是给 server 兜底。

### 10.2 性能与多实例

**(d) 暖池**(已在 §8 标 ⏳)
- **做什么**:提前起几个空闲沙盒备着,用户来了直接领。
- **不做**:每次新会话第一次用沙盒要等几秒冷启动(拉容器、装 execd、就绪检查)。**功能没问题,只是首响应慢一拍**。

**(e) 跨进程沙盒复用**(已在 §8 标 ⏳)
- **做什么**:把沙盒 id 随 checkpoint 存库;backend 多副本时,同一会话被路由到不同进程也能"接回"原来那个沙盒。
- **不做**:多副本部署下同一会话的第二条消息可能落到另一个进程 → 重新建一个新沙盒,工作目录/状态不连续(旧沙盒靠 idle 自动回收,不算泄漏,但浪费 + 体验断裂)。**单进程开发完全不受影响**。

**(f) 沙盒实例管理页(运维侧)** ✅ **已实现并端到端验证**
- 系统配置 → 沙盒实例 tab(`SandboxInstanceView.vue`),列出 OpenSandbox server 当前持有的所有沙盒(创建时间/过期时间/镜像/状态),支持「查看桌面」(复用 noVNC iframe)和「停止」(popconfirm),权限 `system:setting`。
- 后端 `SandboxInstanceService` 走 `SandboxManagerSync.list_sandbox_infos` / `kill_sandbox` 和 `SandboxesSync.get_sandbox_endpoint` 直连 server,**不依赖本进程 registry**,因此能看到 backend 重启后映射丢失的"孤儿"。
- API:`GET /api/v1/sandbox-instance`、`DELETE /{id}`、`GET /{id}/view`。
- 实现踩坑(已固化):`SandboxInfo.image` 是 `SandboxImageSpec(image=..., auth=...)` 要取内层;`SandboxInfo.status` 是 `SandboxStatus` 对象取 `.state`;`SandboxSync.resume` 是"暂停→恢复"生命周期 API,**不能**用于"按 id 重连"运行中沙盒(会报 `not in a paused state`),view 路径直接走底层 `get_sandbox_endpoint(id, port, use_server_proxy)`。

### 10.3 测试与平台覆盖

**(g) CI 接入端到端回归**
- **做什么**:把 `backend/scripts/sandbox/` 的几条脚本(`01_smoke` / `02_isolation_proof` / `03_desktop_e2e` / `05_computeruse_e2e`)接入 CI,每次改动跑一次。
- **不做**:沙盒/可视化/computer-use 不在自动化回归内,只能靠每次手动跑。**变更稍多就容易回归**。

**(h) 单元测试覆盖**
- **做什么**:registry、computer_tools、SandboxImageService 加单测。
- **不做**:目前回归全靠端到端脚本,粒度粗,坏掉时不易定位。

**(i) Linux 部署演练**
- **做什么**:在一台 Linux(非 macOS Docker Desktop)宿主上完整跑一次 `./deploy.sh up` + 沙盒/可视化烟测,确认无 mac-only 假设。
- **不做**:目前所有验证都在 macOS Docker Desktop 上做的。Linux 上理论也通(架构问题已规避,见下),**但没真跑过**。

### 10.4 部署形态(澄清,非待办)

**桌面镜像保持"部署时本地构建"**(`./deploy.sh up` 触发),不 push 任何 registry:这样**自动按宿主 CPU 架构(arm64/amd64)编译**,不用做多架构 buildx,也不需要 registry。代价是每台新部署机首次构建大约 10 分钟(已换阿里云源,稳定)。多机批量部署如果想加速,可以加本地构建缓存(`--cache-from`),但**不强需**。

### 10.5 流程

- **未提交**:这条线累积的所有改动按既定习惯由你自行 `git commit`。
- **README/runbook 增补**:仓库顶层 README 没指向 §7 的"`./deploy.sh up` + 启用沙盒"流程;补一行链接即可。
- **changelog/PR 描述**:整理一次,方便后续追溯。

### 优先级建议

- **现在做**:10.3-(i) Linux 演练 + 10.5 commit/changelog ── 收尾性质,半天内。
- **上线前建议做**:10.1-(a)(b) 安全两项 ── (a) egress 白名单需要研究 OpenSandbox `NetworkPolicy` 字段;(b) docker-socket-proxy 几行 compose,变更部署架构。
- **上规模再做**:10.2-(d)(e) + 10.3-(g)(h)。
- **已完成**:10.2-(f) 沙盒实例管理页。
- **澄清不做**:registry push(§10.4)。
