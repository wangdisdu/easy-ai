<template>
  <a-popover
    v-model:open="open"
    trigger="click"
    placement="bottomRight"
    overlay-class-name="alerts-bell-pop"
  >
    <a-button type="text" class="bell-btn" aria-label="告警通知">
      <a-badge :count="active?.total || 0" :overflow-count="99" size="small">
        <BellOutlined class="bell-icon" />
      </a-badge>
    </a-button>

    <template #content>
      <div class="bell-panel">
        <div class="bell-head">
          <span class="bell-title">告警通知</span>
          <span v-if="active && active.total > 0" class="bell-counts">
            <span class="bc bc--critical">严重 {{ active.critical }}</span>
            <span class="bc bc--warning">警告 {{ active.warning }}</span>
            <span class="bc bc--info">通知 {{ active.info }}</span>
          </span>
        </div>

        <div v-if="!active || active.items.length === 0" class="bell-empty">
          系统运行良好,暂无活跃告警
        </div>
        <div v-else class="bell-list">
          <div
            v-for="item in active.items"
            :key="item.id"
            class="bell-item"
            @click="goAlerts"
          >
            <span :class="['lvl-dot', 'lvl-dot--' + item.level]" />
            <div class="bell-item-body">
              <div class="bell-item-name">{{ item.rule_name }}</div>
              <div class="bell-item-msg">{{ item.message }}</div>
            </div>
            <span class="bell-item-time">{{ formatMs(item.triggered_at) }}</span>
          </div>
        </div>

        <div class="bell-foot" @click="goAlerts">查看全部告警</div>
      </div>
    </template>
  </a-popover>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { BellOutlined } from "@ant-design/icons-vue";
import { getActiveAlerts } from "@/api/alert";
import type { AlertActiveResp } from "@/api/types";
import { formatMs } from "@/utils/time";

const POLL_MS = 60_000;

const router = useRouter();
const open = ref(false);
const active = ref<AlertActiveResp | null>(null);
let timer: number | undefined;

async function load() {
  try {
    const { data } = await getActiveAlerts();
    active.value = data.data;
  } catch {
    // 后台轮询失败静默处理,拦截器已提示
  }
}

function goAlerts() {
  open.value = false;
  router.push("/observability/alert");
}

onMounted(() => {
  load();
  timer = window.setInterval(load, POLL_MS);
});

onBeforeUnmount(() => {
  if (timer) window.clearInterval(timer);
});
</script>

<style scoped>
.bell-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 36px;
  width: 36px;
  border-radius: 10px;
}
.bell-icon { font-size: 17px; color: var(--color-text-secondary); }

.bell-panel { width: 320px; }
.bell-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 4px 10px;
  border-bottom: 1px solid var(--color-border);
}
.bell-title { font-size: 14px; font-weight: 700; color: var(--color-text); }
.bell-counts { display: flex; gap: 8px; }
.bc { font-size: 11px; font-weight: 600; }
.bc--critical { color: var(--color-error); }
.bc--warning { color: var(--color-warning); }
.bc--info { color: var(--color-accent); }

.bell-empty { padding: 28px 8px; text-align: center; font-size: 13px; color: var(--color-text-quaternary); }

.bell-list { max-height: 360px; overflow-y: auto; padding: 4px 0; }
.bell-item {
  display: flex;
  gap: 10px;
  padding: 10px 6px;
  border-radius: 10px;
  cursor: pointer;
  transition: background 0.15s ease;
}
.bell-item:hover { background: var(--surface-muted-hover); }
.lvl-dot { width: 8px; height: 8px; border-radius: 999px; margin-top: 5px; flex-shrink: 0; }
.lvl-dot--critical { background: var(--color-error); }
.lvl-dot--warning { background: var(--color-warning); }
.lvl-dot--info { background: var(--color-accent); }
.bell-item-body { flex: 1; min-width: 0; }
.bell-item-name { font-size: 13px; font-weight: 600; color: var(--color-text); }
.bell-item-msg {
  font-size: 12px;
  color: var(--color-text-tertiary);
  margin-top: 2px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.bell-item-time { font-size: 11px; color: var(--color-text-quaternary); flex-shrink: 0; }

.bell-foot {
  padding: 10px 4px 2px;
  border-top: 1px solid var(--color-border);
  text-align: center;
  font-size: 13px;
  font-weight: 600;
  color: var(--color-accent);
  cursor: pointer;
}
</style>
