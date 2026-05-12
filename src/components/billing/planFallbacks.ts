// Static fallback benefits / quota labels keyed by plan slug.
// Used only when DB-driven `features_json` / `quota_hints` are missing.

import type { TranslationKeys } from "@/i18n";
import type { ResolvedBenefit } from "@/lib/billingDisplay";

export function fallbackBenefitsBySlug(
  slug: string,
  t: TranslationKeys,
): ResolvedBenefit[] {
  const base: ResolvedBenefit[] = [
    { id: "workspace_basic", text: t.billing.fallbackBenefitWorkspace },
    { id: "models_basic", text: t.billing.fallbackBenefitModels },
    { id: "exports_basic", text: t.billing.fallbackBenefitExports },
  ];
  // Enterprise gets a generic copy via its tagline; static fallback stays minimal.
  if (slug === "enterprise") {
    return [];
  }
  return base;
}

export function quotaLabelFallback(t: TranslationKeys): Record<string, string> {
  return {
    concurrent_analyses: t.billing.quotaLabelConcurrent,
    queue_priority: t.billing.quotaLabelQueue,
    supported_file_types: t.billing.quotaLabelFileTypes,
    supported_security_log_types: t.billing.quotaLabelLogTypes,
    knowledge_base_capacity: t.billing.quotaLabelKb,
    e2b_sandbox: t.billing.quotaLabelSandbox,
  };
}
