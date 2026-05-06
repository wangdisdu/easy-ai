/**
 * Markdown 渲染 + Mermaid 流程图支持
 *
 * marked.use() 和 mermaid.initialize() 在模块首次加载时执行一次，后续 import 直接复用。
 * renderMarkdown  —— 把 Markdown 文本转为 HTML 字符串（供 v-html 使用）
 * runMermaid      —— 在给定容器内查找未处理的 mermaid 占位元素，用 textContent 赋值
 *                    后调用 mermaid.run()，完全绕开 innerHTML 的 HTML 实体编码问题
 */

import { marked } from "marked";
import mermaid from "mermaid";

// ── 注册 mermaid 代码块渲染器（全局，只需一次）──────────────────────────────
// 通过 data-src 存储原始源码，而非写入 innerHTML——避免 HTML 实体编码
// 被 mermaid 解析时出现 "Syntax error in text" 错误。
marked.use({
  renderer: {
    code({ text, lang }: { text: string; lang?: string }): string | false {
      if (lang === "mermaid") {
        return `<div class="mermaid-diagram" data-src="${encodeURIComponent(text)}"></div>`;
      }
      return false; // 其余语言走 marked 默认渲染
    },
  },
});

// ── 初始化 mermaid（全局，只需一次）────────────────────────────────────────
mermaid.initialize({
  startOnLoad: false,
  theme: "default",
});

// ── 导出工具函数 ─────────────────────────────────────────────────────────────

export function renderMarkdown(text: string): string {
  return marked(text) as string;
}

/**
 * 在 container 内找到所有未渲染的 .mermaid-diagram 元素：
 * 1. 通过 data-src 解码原始源码
 * 2. 用 el.textContent = src 创建 .mermaid 子元素（绕开 HTML 编码）
 * 3. 调用 mermaid.run() 渲染为 SVG
 * 幂等：已渲染的元素带有 data-processed 属性，不会重复处理。
 */
export async function runMermaid(container: HTMLElement | null): Promise<void> {
  if (!container) return;

  const wrappers = Array.from(
    container.querySelectorAll<HTMLElement>(".mermaid-diagram:not([data-processed])"),
  );
  if (!wrappers.length) return;

  const nodes: HTMLElement[] = [];
  for (const wrapper of wrappers) {
    const src = decodeURIComponent(wrapper.dataset.src ?? "");
    if (!src) continue;
    const el = document.createElement("div");
    el.className = "mermaid";
    el.textContent = src; // 直接赋 textContent，无任何 HTML 转义干扰
    wrapper.appendChild(el);
    wrapper.setAttribute("data-processed", "true");
    nodes.push(el);
  }

  if (!nodes.length) return;
  try {
    await mermaid.run({ nodes, suppressErrors: true });
  } catch (e) {
    console.warn("[mermaid] render error:", e);
  }
}
