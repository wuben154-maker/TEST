import { Check } from "lucide-react";
import type { ResolvedBenefit } from "@/lib/billingDisplay";

type Variant = "app" | "marketing";

const containerClass = (variant: Variant) =>
  variant === "marketing" ? "text-[13px] text-[#e8e5de]/85" : "text-sm text-foreground";

const iconWrapClass = (variant: Variant) =>
  variant === "marketing"
    ? "text-[#9be7c4]"
    : "text-primary";

export function PlanBenefitsList({
  benefits,
  variant = "app",
  ariaLabel,
  emptyText,
}: {
  benefits: ResolvedBenefit[];
  variant?: Variant;
  ariaLabel?: string;
  emptyText?: string;
}) {
  if (!benefits.length) {
    if (!emptyText) return null;
    return (
      <p
        className={
          variant === "marketing"
            ? "text-[13px] leading-relaxed text-[#9a9a98]"
            : "text-sm text-muted-foreground"
        }
      >
        {emptyText}
      </p>
    );
  }
  return (
    <ul aria-label={ariaLabel} className={`flex flex-col gap-2 ${containerClass(variant)}`}>
      {benefits.map((b) => (
        <li
          key={b.id || b.text}
          className="flex items-start gap-2 leading-snug"
          data-benefit-id={b.id || undefined}
        >
          <Check
            aria-hidden
            className={`mt-0.5 h-4 w-4 flex-shrink-0 ${iconWrapClass(variant)}`}
          />
          <span>{b.text}</span>
        </li>
      ))}
    </ul>
  );
}
