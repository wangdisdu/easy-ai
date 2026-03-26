export function formatMs(ms: number): string {
  if (!ms) return "-";
  return new Date(ms).toLocaleString();
}
