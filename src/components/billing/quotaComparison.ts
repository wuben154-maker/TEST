import type { ResolvedQuotaHint } from "@/lib/billingDisplay";

/**
 * Stable quota row ids for plan cards so every tier renders the same number of rows,
 * aligning visually across sibling columns when shown in a grid.
 */
export const QUOTA_HINT_ROW_ORDER: readonly string[] = [
  "concurrent_analyses",
  "queue_priority",
  "supported_file_types",
  "supported_security_log_types",
  "e2b_sandbox",
] as const;

/**
 * Expand / reorder hints to QUOTA_HINT_ROW_ORDER; pad missing ids with em dash values
 * but keep backend-provided labels (via labelByIdFallback) when the plan omits a row.
 */
export function normalizeQuotaHintsForComparison(
  hints: ResolvedQuotaHint[],
  labelByIdFallback: Partial<Record<string, string>>,
): ResolvedQuotaHint[] {
  if (!hints.length) return [];
  const byId = new Map(hints.map((h) => [h.id, h]));
  const orderSet = new Set(QUOTA_HINT_ROW_ORDER);
  const ordered = QUOTA_HINT_ROW_ORDER.map((id) => {
    const found = byId.get(id);
    if (found) return found;
    const label = labelByIdFallback[id]?.trim();
    return {
      id,
      label: label && label.length ? label : id,
      value: "—",
    };
  });
  const extras = hints.filter((h) => !orderSet.has(h.id));
  return extras.length ? [...ordered, ...extras] : ordered;
}
