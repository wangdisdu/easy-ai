/**
 * SSE (Server-Sent Events) 客户端工具。
 *
 * 使用 fetch + ReadableStream 实现（不用 EventSource，因为 EventSource 仅支持 GET）。
 */

export interface SSEEvent {
  event: string;
  data: Record<string, unknown>;
}

export interface SSEOptions {
  onEvent: (event: SSEEvent) => void;
  onError?: (error: Error) => void;
  onDone?: () => void;
  signal?: AbortSignal;
}

/**
 * 向指定 URL 发起 POST 请求并以 SSE 协议解析流式响应。
 */
export async function fetchSSE(
  url: string,
  body: Record<string, unknown>,
  options: SSEOptions,
): Promise<void> {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    credentials: "include",
    signal: options.signal,
  });

  if (!response.ok) {
    let detail = `SSE request failed: ${response.status}`;
    try {
      const errorBody = await response.json();
      if (errorBody?.msg) detail = errorBody.msg;
    } catch {
      // ignore parse error
    }
    throw new Error(detail);
  }

  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let currentEvent = "";

  // eslint-disable-next-line no-constant-condition
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    // 最后一行可能不完整，保留在 buffer 中
    buffer = lines.pop()!;

    for (const line of lines) {
      if (line.startsWith("event: ")) {
        currentEvent = line.slice(7).trim();
      } else if (line.startsWith("data: ")) {
        const raw = line.slice(6);
        if (raw === "[DONE]") {
          options.onDone?.();
          return;
        }
        try {
          const data = JSON.parse(raw) as Record<string, unknown>;
          options.onEvent({ event: currentEvent, data });
        } catch {
          // 跳过无法解析的 data 行
        }
      }
      // 空行重置 currentEvent（SSE 协议中事件边界）
      if (line === "") {
        currentEvent = "";
      }
    }
  }

  // 流正常结束但未收到 [DONE]
  options.onDone?.();
}
