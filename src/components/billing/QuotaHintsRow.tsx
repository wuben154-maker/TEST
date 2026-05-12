import type { ResolvedQuotaHint } from "@/lib/billingDisplay";

type Variant = "app" | "marketing";

/**
 * Labels use normal case so CJK does not collide with faux-uppercase layout.
 * Fixed label column keeps wrapping consistent across sibling plan cards.
 */
const labelClass = (variant: Variant) =>
  variant === "marketing"
    ? "text-[11px] font-medium leading-snug tracking-normal text-[#9a9a98] [word-break:keep-all]"
    : "text-xs leading-snug tracking-normal text-muted-foreground [word-break:keep-all]";

const valueClass = (variant: Variant) =>
  variant === "marketing"
    ? "text-[13px] font-medium tabular-nums leading-snug text-[#e8e5de]"
    : "text-sm font-medium tabular-nums leading-snug text-foreground";

const rowGridClass =
  "grid grid-cols-[minmax(5.75rem,0.42fr)_minmax(0,1fr)] items-start gap-x-3 border-b border-border/25 py-2 last:border-b-0";

const rowGridMarketingClass =
  "grid grid-cols-[minmax(5.75rem,0.42fr)_minmax(0,1fr)] items-start gap-x-3 border-b border-[#2e2c28]/50 py-2 last:border-b-0";

export function QuotaHintsRow({
  hints,
  variant = "app",
  title,
}: {
  hints: ResolvedQuotaHint[];
  variant?: Variant;
  title?: string;
}) {
  if (!hints.length) return null;
  return (
    <div className="flex flex-col gap-2">
      {title ? (
        <h4
          className={
            variant === "marketing"
              ? "text-[12px] font-semibold tracking-wide text-[#e8e5de]/85"
              : "text-xs font-semibold tracking-wide text-muted-foreground"
          }
        >
          {title}
        </h4>
      ) : null}
      <dl className={variant === "marketing" ? "grid grid-cols-1 gap-0" : "grid grid-cols-1 gap-0"}>
        {hints.map((h) => (
          <div
            key={h.id}
            className={variant === "marketing" ? rowGridMarketingClass : rowGridClass}
            data-quota-id={h.id}
          >
            <dt className={`${labelClass(variant)} min-w-0`}>{h.label}</dt>
            <dd className={`${valueClass(variant)} min-w-0 text-right break-words`}>{h.value}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
