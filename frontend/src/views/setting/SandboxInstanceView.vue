<template>
  <div class="inst-page">
    <div class="inst-toolbar">
      <span class="inst-hint">直接来源:OpenSandbox server。包含本进程映射丢失的"孤儿"沙盒。</span>
      <a-button :loading="loading" @click="loadList">刷新</a-button>
    </div>

    <a-table
      :columns="columns"
      :data-source="list"
      :loading="loading"
      :pagination="false"
      row-key="id"
      size="middle"
      class="inst-table"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'id'">
          <code class="inst-id">{{ record.id }}</code>
        </template>
        <template v-else-if="column.key === 'image'">
          <code class="inst-image">{{ record.image || "—" }}</code>
        </template>
        <template v-else-if="column.key === 'status'">
          <a-tag :color="statusColor(record.status)">{{ record.status || "unknown" }}</a-tag>
        </template>
        <template v-else-if="column.key === 'created_at'">
          {{ formatTs(record.created_at) }}
        </template>
        <template v-else-if="column.key === 'expires_at'">
          {{ formatTs(record.expires_at) }}
        </template>
        <template v-else-if="column.key === 'action'">
          <a-button type="link" size="small" @click="openDesktop(record)">查看桌面</a-button>
          <a-popconfirm
            v-if="canEdit"
            title="确定停止该沙盒?"
            description="该沙盒内的会话将无法继续使用,运行态丢失。"
            ok-text="停止"
            cancel-text="取消"
            ok-type="danger"
            @confirm="onKill(record)"
          >
            <a-button type="link" size="small" danger>停止</a-button>
          </a-popconfirm>
        </template>
      </template>
    </a-table>

    <a-modal
      v-model:open="desktopOpen"
      :title="`沙盒桌面 · ${desktopFor}`"
      :width="1320"
      :footer="null"
      destroy-on-close
      @cancel="closeDesktop"
    >
      <a-spin v-if="desktopLoading" tip="正在拉起沙盒桌面…">
        <div class="inst-desktop-frame" />
      </a-spin>
      <iframe
        v-else-if="desktopUrl"
        :src="desktopUrl"
        class="inst-desktop-frame"
        allow="clipboard-read; clipboard-write"
      />
      <a-empty
        v-else
        description="沙盒桌面不可用(非桌面镜像 / 沙盒未就绪)"
      />
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { message } from "ant-design-vue";
import * as api from "@/api/sandboxInstance";
import type { SandboxInstanceResp } from "@/api/types";
import { useAuthStore } from "@/stores/auth";
import { PERM } from "@/utils/permission";

const auth = useAuthStore();
const canEdit = computed(() => auth.hasPermission(PERM.SYSTEM_SETTING));

const columns = [
  { title: "沙盒 ID", dataIndex: "id", key: "id", width: 280 },
  { title: "镜像", dataIndex: "image", key: "image" },
  { title: "状态", dataIndex: "status", key: "status", width: 110 },
  { title: "创建时间", dataIndex: "created_at", key: "created_at", width: 170 },
  { title: "过期时间", dataIndex: "expires_at", key: "expires_at", width: 170 },
  { title: "操作", key: "action", width: 170 },
];

const list = ref<SandboxInstanceResp[]>([]);
const loading = ref(false);
const desktopOpen = ref(false);
const desktopLoading = ref(false);
const desktopUrl = ref("");
const desktopFor = ref("");

async function loadList() {
  loading.value = true;
  try {
    const { data } = await api.listSandboxInstances();
    list.value = data.data || [];
  } catch (e) {
    message.error("读取失败:" + (e instanceof Error ? e.message : String(e)));
  } finally {
    loading.value = false;
  }
}

async function onKill(record: SandboxInstanceResp) {
  try {
    await api.killSandboxInstance(record.id);
    message.success("已停止");
    await loadList();
  } catch (e) {
    message.error("停止失败:" + (e instanceof Error ? e.message : String(e)));
  }
}

function closeDesktop() {
  desktopOpen.value = false;
  desktopUrl.value = "";
}

async function openDesktop(record: SandboxInstanceResp) {
  desktopFor.value = record.id.slice(0, 8);
  desktopOpen.value = true;
  desktopLoading.value = true;
  desktopUrl.value = "";
  try {
    const { data } = await api.getSandboxInstanceView(record.id);
    if (!data.data.ready || !data.data.url) {
      desktopLoading.value = false;
      return;
    }
    const u = new URL(data.data.url);
    const prefix = u.pathname.replace(/^\/+|\/+$/g, "");
    const wsPath = encodeURIComponent(`${prefix}/websockify`);
    desktopUrl.value =
      `${u.origin}/${prefix}/vnc.html?autoconnect=true&resize=scale&path=${wsPath}`;
  } catch (e) {
    message.warning("加载失败:" + (e instanceof Error ? e.message : String(e)));
  } finally {
    desktopLoading.value = false;
  }
}

function statusColor(s: string): string {
  const v = (s || "").toLowerCase();
  if (v.includes("run") || v.includes("ready")) return "green";
  if (v.includes("pause")) return "orange";
  if (v.includes("kill") || v.includes("stop") || v.includes("dead")) return "red";
  return "default";
}

function formatTs(s: string | null | undefined): string {
  if (!s) return "—";
  const d = new Date(s);
  if (Number.isNaN(d.getTime())) return s;
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

onMounted(loadList);
</script>

<style scoped>
.inst-page {
  min-height: 100%;
}

.inst-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}

.inst-hint {
  font-size: 12px;
  color: var(--color-text-tertiary);
}

.inst-table {
  background: var(--surface-base);
}

.inst-id,
.inst-image {
  font-size: 12px;
  color: var(--color-text-secondary);
}

.inst-desktop-frame {
  width: 100%;
  height: 760px;
  border: 0;
  background: #1e1e1e;
  display: block;
}
</style>
