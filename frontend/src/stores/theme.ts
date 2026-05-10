import { defineStore } from "pinia";
import { ref } from "vue";

export type ThemeMode = "light" | "dark";

const STORAGE_KEY = "easy-ai:theme";

function readStored(): ThemeMode | null {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    return v === "light" || v === "dark" ? v : null;
  } catch {
    return null;
  }
}

function applyToDom(mode: ThemeMode) {
  document.documentElement.setAttribute("data-theme", mode);
}

export const useThemeStore = defineStore("theme", () => {
  const mode = ref<ThemeMode>(readStored() ?? "light");

  /** 应用主题到 DOM；应在 createApp 之前调用一次以避免首屏闪烁。 */
  function init() {
    applyToDom(mode.value);
  }

  function setMode(next: ThemeMode) {
    if (mode.value === next) return;
    mode.value = next;
    applyToDom(next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      /* ignore: 隐私模式或配额异常时静默降级 */
    }
  }

  function toggle() {
    setMode(mode.value === "light" ? "dark" : "light");
  }

  return { mode, init, setMode, toggle };
});
