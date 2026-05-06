/**
 * 工具调用展示工具函数
 *
 * task 工具是 DeepAgents 框架用于委派子代理的内置工具，需要与普通工具区分展示。
 * subagent_hitl 状态由后端在子代理触发 HITL 时通过 tool_call_end 事件发送，
 * 替代了原先透传 GraphInterrupt 原始 Python repr 字符串的做法。
 */

export type ToolCallStatus = "running" | "done" | "success" | "error" | "subagent_hitl";

export function isSubagentTask(name?: string, args?: Record<string, unknown>): boolean {
  return name === "task" && typeof args?.subagent_type === "string" && Boolean(args.subagent_type);
}

export function toolDisplayName(name?: string, args?: Record<string, unknown>): string {
  if (isSubagentTask(name, args)) return `${args!.subagent_type as string}`;
  return name || "工具调用";
}

export function toolDisplayIcon(name?: string, args?: Record<string, unknown>): string {
  return isSubagentTask(name, args) ? "🤖" : "🔧";
}

/** 子代理内部触发了 HITL，task 工具调用处于等待用户确认状态。 */
export function isSubagentHitlStatus(status?: string): boolean {
  return status === "subagent_hitl";
}
