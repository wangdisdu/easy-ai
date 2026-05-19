# 可视化沙盒镜像:Xvfb + fluxbox + Chromium + x11vnc + noVNC。
# 容器保持 keep-alive(由 registry 注入的 entrypoint),桌面栈在沙盒创建后
# 由后端经 execd 跑 /usr/local/bin/start-desktop.sh 拉起(幂等)。
# 详见 docs/sandbox-design.md §9。
#
# 本地构建(OpenSandbox server 用宿主 docker,本地镜像即可,无需 push):
#   docker build -t easy-ai/sandbox-desktop:latest deploy/opensandbox/desktop
FROM debian:bookworm-slim

# 换阿里云 Debian 镜像源(deb.debian.org 不稳/被墙;国内构建快且可靠)。
# bookworm-slim 用 deb822 格式 /etc/apt/sources.list.d/debian.sources。
RUN sed -i 's|deb.debian.org|mirrors.aliyun.com|g; s|security.debian.org|mirrors.aliyun.com|g' \
      /etc/apt/sources.list.d/debian.sources \
 && apt-get -o Acquire::Retries=5 update \
 && apt-get -o Acquire::Retries=5 install -y --no-install-recommends \
      xvfb fluxbox x11vnc novnc websockify chromium \
      xdotool scrot \
      procps ca-certificates dbus-x11 \
      fonts-noto-cjk fonts-noto-color-emoji \
 && rm -rf /var/lib/apt/lists/*

# 非 root 用户:Chromium 以它运行,从而无需 --no-sandbox(去掉黄色警告条)。
RUN useradd -m -u 1000 -s /bin/sh app

COPY start-desktop.sh /usr/local/bin/start-desktop.sh
RUN chmod +x /usr/local/bin/start-desktop.sh

ENV DISPLAY=:1
# entrypoint 由 SandboxRegistry 注入(tail -f /dev/null 保活);此 CMD 仅兜底。
CMD ["tail", "-f", "/dev/null"]
