<template>
  <aside :class="['todo-panel', collapsed ? 'todo-panel--collapsed' : '']">
    <header class="todo-panel-header" @click="collapsed && toggle()">
      <span class="todo-panel-title">
        <span class="todo-panel-icon">📋</span>
        <template v-if="!collapsed">任务清单</template>
      </span>
      <span class="todo-panel-progress">{{ doneCount }}/{{ todos.length }}</span>
      <button
        v-if="!collapsed"
        class="todo-panel-toggle"
        :title="'折叠'"
        @click.stop="toggle"
      >
        ▶
      </button>
    </header>
    <ul v-if="!collapsed" class="todo-panel-list">
      <li
        v-for="(t, i) in todos"
        :key="i"
        :class="['todo-item', `todo-item--${t.status}`]"
      >
        <span class="todo-item-icon">{{ statusIcon(t.status) }}</span>
        <span class="todo-item-content">{{ t.content }}</span>
      </li>
    </ul>
  </aside>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";

export interface Todo {
  content: string;
  status: "pending" | "in_progress" | "completed";
}

const props = defineProps<{ todos: Todo[] }>();

const STORAGE_KEY = "todoPanelCollapsed";

const collapsed = ref<boolean>(loadCollapsed());

function loadCollapsed(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

function saveCollapsed(v: boolean) {
  try {
    localStorage.setItem(STORAGE_KEY, v ? "1" : "0");
  } catch {
    /* ignore */
  }
}

function toggle() {
  collapsed.value = !collapsed.value;
}

watch(collapsed, (v) => saveCollapsed(v));

const doneCount = computed(
  () => props.todos.filter((t) => t.status === "completed").length,
);

function statusIcon(status: Todo["status"]): string {
  if (status === "completed") return "✓";
  if (status === "in_progress") return "⠋";
  return "○";
}
</script>

<style scoped>
.todo-panel {
  display: flex;
  flex-direction: column;
  width: 320px;
  border-left: 1px solid var(--color-border);
  background: var(--surface-subtle);
  transition: width 0.2s ease;
  overflow: hidden;
}

.todo-panel--collapsed {
  width: 44px;
  cursor: pointer;
}

.todo-panel-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 14px;
  border-bottom: 1px solid var(--color-border);
  background: var(--color-bg-elevated);
  user-select: none;
  flex-shrink: 0;
}

.todo-panel--collapsed .todo-panel-header {
  flex-direction: column;
  padding: 12px 8px;
  border-bottom: none;
  cursor: pointer;
}

.todo-panel-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text);
  flex: 1;
}

.todo-panel-icon {
  font-size: 14px;
}

.todo-panel-progress {
  font-size: 12px;
  color: var(--color-text-tertiary);
  font-variant-numeric: tabular-nums;
  background: var(--color-split);
  padding: 2px 8px;
  border-radius: 10px;
}

.todo-panel-toggle {
  border: none;
  background: transparent;
  color: var(--color-text-quaternary);
  cursor: pointer;
  padding: 2px 4px;
  font-size: 12px;
}

.todo-panel-toggle:hover {
  color: var(--color-text);
}

.todo-panel-list {
  list-style: none;
  margin: 0;
  padding: 8px 8px 16px;
  overflow-y: auto;
  flex: 1;
}

.todo-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 6px;
  font-size: 13px;
  line-height: 1.5;
  transition: background 0.15s;
}

.todo-item:hover {
  background: var(--color-split);
}

.todo-item-icon {
  flex-shrink: 0;
  width: 16px;
  text-align: center;
  font-weight: 700;
}

.todo-item-content {
  flex: 1;
  word-break: break-word;
}

.todo-item--pending .todo-item-icon {
  color: var(--color-text-quaternary);
}

.todo-item--pending .todo-item-content {
  color: var(--color-text-secondary);
}

.todo-item--in_progress .todo-item-icon {
  color: var(--color-info-strong);
  animation: spin 1.4s linear infinite;
  display: inline-block;
}

.todo-item--in_progress .todo-item-content {
  color: var(--color-info-strong);
  font-weight: 500;
}

.todo-item--completed .todo-item-icon {
  color: var(--color-success-strong);
}

.todo-item--completed .todo-item-content {
  color: var(--color-text-tertiary);
  text-decoration: line-through;
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

@media (max-width: 768px) {
  .todo-panel {
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    width: 100%;
    max-height: 50vh;
    border-left: none;
    border-top: 1px solid var(--color-border);
    z-index: 50;
  }

  .todo-panel--collapsed {
    width: 100%;
    height: 44px;
  }
}
</style>
