/** 权限码常量。与后端 backend/app/core/permission.py 保持同步。 */
export const PERM = {
  APP_EDIT: "app:edit",
  APP_PUBLISH: "app:publish",
  SKILL_EDIT: "skill:edit",
  SKILL_PUBLISH: "skill:publish",
  TOOL_EDIT: "tool:edit",
  TOOL_CONTROL: "tool:control",
  KB_EDIT: "kb:edit",
  KB_PUBLISH: "kb:publish",
  SYSTEM_LLM: "system:llm",
  SYSTEM_SETTING: "system:setting",
  PERMISSION_USER: "permission:user",
  PERMISSION_ROLE: "permission:role",
} as const;

export type PermissionCode = (typeof PERM)[keyof typeof PERM];
