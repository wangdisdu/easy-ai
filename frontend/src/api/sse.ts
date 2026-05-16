/**
 * Agent 流式通信协议 v1 客户端。
 *
 * 传输：fetch + ReadableStream（POST body，非 EventSource）。
 * 帧：`data: <json>\n\n`，事件类型在 JSON 载荷的 `type` 字段（不使用 SSE
 * `event:` 行，信封传输无关）。流以 `data: [DONE]` 收尾。
 */

export interface SSEEvent {
  /** 事件类型，取自载荷 `type` 字段（如 run.started / block.delta）。 */
  event: string;
  /** 完整事件载荷（含 type/v/seq/run_id 信封字段）。 */
  data: Record<string, unknown>;
}

export interface SSEOptions {
  onEvent: (event: SSEEvent) => void;
  onError?: (error: Error) => void;
  onDone?: () => void;
  signal?: AbortSignal;
}

/**
 * 向指定 URL 发起 POST 请求并按协议解析流式响应。
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

  // eslint-disable-next-line no-constant-condition
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    // 最后一行可能不完整，保留在 buffer 中
    buffer = lines.pop()!;

    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      const raw = line.slice(6);
      if (raw === "[DONE]") {
        options.onDone?.();
        return;
      }
      try {
        const data = JSON.parse(raw) as Record<string, unknown>;
        options.onEvent({ event: String(data.type ?? ""), data });
      } catch {
        // 跳过无法解析的 data 行
      }
    }
  }

  // 流正常结束但未收到 [DONE]
  options.onDone?.();
}
