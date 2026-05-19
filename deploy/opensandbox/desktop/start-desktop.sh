#!/bin/sh
# 幂等拉起桌面栈:Xvfb(虚拟屏)→ fluxbox(窗管)→ x11vnc(5900)→
# websockify/noVNC(6080,提供网页客户端并代理到 5900)→ Chromium。
# 后端经 execd 在沙盒创建后调用;重复调用安全(pgrep 守卫)。
#
# 用 setsid 让各守护脱离本次 exec 会话,execd 退出回收会话时不会被连带杀掉。
# 详见 docs/sandbox-design.md §9。
set -e
export DISPLAY=:1

if pgrep -x Xvfb >/dev/null 2>&1; then
  echo "desktop already running"
  exit 0
fi

# -ac 关闭 X 访问控制,让非 root 的 app 用户也能连上本 :1(单用户隔离沙盒,安全)
setsid Xvfb :1 -screen 0 1280x800x24 -ac >/tmp/xvfb.log 2>&1 &
for _ in $(seq 1 30); do
  [ -e /tmp/.X11-unix/X1 ] && break
  sleep 0.2
done

setsid fluxbox >/tmp/fluxbox.log 2>&1 &
setsid x11vnc -display :1 -forever -shared -nopw -o /tmp/x11vnc.log >/tmp/x11vnc.boot 2>&1 &
setsid websockify --web=/usr/share/novnc 6080 localhost:5900 >/tmp/novnc.log 2>&1 &
# Chromium 以非 root 的 app 用户运行(纵深防御)。本受限容器禁了非特权
# user namespace、且 no_new_privileges 使 SUID sandbox 也不可用 → 必须
# --no-sandbox(否则 "No usable sandbox" 崩);用 --test-type 抑制由此产生
# 的黄色 "unsupported command-line flag" 警告条。详见 docs/sandbox-design.md §9。
setsid runuser -u app -- env HOME=/home/app DISPLAY=:1 \
  chromium --no-sandbox --test-type --no-first-run --start-maximized \
  --disable-dev-shm-usage --user-data-dir=/home/app/.chromium \
  about:blank >/tmp/chromium.log 2>&1 &

echo "desktop started: noVNC on :6080"
