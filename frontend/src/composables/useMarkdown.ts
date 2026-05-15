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

// ── 注册 [[doc:REF]] 内联引用扩展(用于 RAG 应用回答的文档引用)──────────────
// 渲染成 data-doc-ref 标记的 anchor,具体跳转逻辑由 AssistantView 等使用方
// 通过事件委托捕获 click 处理(调 GET /kb/document-by-ref/{ref} 解析后跳预览)。
// inline level extension 不会在 fenced code block 内被处理。
marked.use({
  extensions: [
    {
      name: "doc-ref",
      level: "inline",
      start(src: string) {
        const i = src.indexOf("[[doc:");
        return i === -1 ? undefined : i;
      },
      tokenizer(src: string) {
        const m = /^\[\[doc:([a-z0-9]{4,16})\]\]/i.exec(src);
        if (!m) return undefined;
        return {
          type: "doc-ref",
          raw: m[0],
          ref: m[1].toLowerCase(),
        };
      },
      renderer(token) {
        const ref = (token as unknown as { ref: string }).ref;
        return (
          `<a class="doc-ref-link" data-doc-ref="${ref}" href="#" ` +
          `role="button" title="点击查看引用文档">` +
          `<svg class="doc-ref-icon" width="11" height="11" viewBox="0 0 24 24" ` +
          `fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>` +
          `${ref}</a>`
        );
      },
    },
  ],
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
 * 渲染 markdown 后,把 .doc-ref-link 内的纯 ref 文本替换为 "文档名 (ref)"。
 * 适用场景:RAG 回答里的 [[doc:abc123]] 已经被 marked 扩展渲染成 anchor,
 * 但只显示 ref 不友好;调用方传入预先建好的 ``refNames`` (ref → 文档名)
 * 作为参考,匹配到的会被替换,匹配不到的保持只显 ref。
 */
export function renderMarkdownWithDocRefs(
  text: string,
  refNames: Record<string, string>,
): string {
  const html = renderMarkdown(text);
  if (!refNames || Object.keys(refNames).length === 0) return html;
  return html.replace(
    /(<a[^>]*class="doc-ref-link"[^>]*data-doc-ref="([a-z0-9]+)"[^>]*>)(<svg[^>]*>[\s\S]*?<\/svg>)([^<]*)(<\/a>)/gi,
    (_full, openTag: string, ref: string, svg: string, _refText: string, closeTag: string) => {
      const name = refNames[ref];
      if (!name) return `${openTag}${svg}${escapeHtml(ref)}${closeTag}`;
      return `${openTag}${svg}${escapeHtml(`${name} (${ref})`)}${closeTag}`;
    },
  );
}

function escapeHtml(s: string): string {
  return s.replace(/[&<>"']/g, (c) =>
    c === "&" ? "&amp;"
    : c === "<" ? "&lt;"
    : c === ">" ? "&gt;"
    : c === "\"" ? "&quot;"
    : "&#39;",
  );
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
