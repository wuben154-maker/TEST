import { useState } from "react";
import { Link } from "react-router-dom";
import { ChevronDown } from "lucide-react";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { useLanguage } from "@/contexts/LanguageContext";
import { DEFAULT_CREDITS_PER_USD, formatBillingTokens } from "@/lib/billingDisplay";

type Variant = "app" | "marketing";

export function MeteringDisclosure({
  tokensEstimate,
  variant = "app",
  defaultOpen = false,
  showUsageLink = true,
  creditsPerUsd = DEFAULT_CREDITS_PER_USD,
}: {
  tokensEstimate?: number;
  variant?: Variant;
  defaultOpen?: boolean;
  showUsageLink?: boolean;
  creditsPerUsd?: number;
}) {
  const { t, language } = useLanguage();
  const [open, setOpen] = useState<boolean>(defaultOpen);

  const wrapperClass =
    variant === "marketing"
      ? "rounded-lg border border-[#2e2c28]/60 bg-[#e8e5de]/[0.02] p-3"
      : "rounded-lg border border-border/60 bg-muted/40 p-3";

  const triggerClass =
    variant === "marketing"
      ? "flex w-full items-center justify-between gap-2 text-left text-[13px] font-medium text-[#e8e5de]/85 hover:text-[#e8e5de]"
      : "flex w-full items-center justify-between gap-2 text-left text-sm font-medium text-foreground hover:text-foreground/80";

  const bodyTextClass =
    variant === "marketing"
      ? "text-[12px] leading-relaxed text-[#9a9a98]"
      : "text-xs leading-relaxed text-muted-foreground";

  const linkClass =
    variant === "marketing"
      ? "text-[12px] text-[#a5b4fc] underline-offset-4 hover:text-[#c7d2fe] hover:underline"
      : "text-xs text-primary underline-offset-4 hover:underline";

  return (
    <Collapsible open={open} onOpenChange={setOpen} className={wrapperClass}>
      <CollapsibleTrigger className={triggerClass} aria-expanded={open}>
        <span>{t.billing.meteringTitle}</span>
        <ChevronDown
          aria-hidden
          className={`h-4 w-4 transition-transform ${open ? "rotate-180" : ""}`}
        />
      </CollapsibleTrigger>
      <CollapsibleContent className="mt-2 space-y-2">
        <p className={bodyTextClass}>
          {t.billing.meteringCreditsEquivalence.replace(
            "{{per}}",
            String(
              Number.isFinite(creditsPerUsd) && creditsPerUsd > 0 ? creditsPerUsd : DEFAULT_CREDITS_PER_USD,
            ),
          )}
        </p>
        <p className={bodyTextClass}>{t.billing.meteringDisclosureLong}</p>
        {typeof tokensEstimate === "number" && tokensEstimate > 0 ? (
          <p className={bodyTextClass}>
            <span className="font-medium">{t.billing.meteringTokensEstimate}: </span>
            {formatBillingTokens(tokensEstimate, language)}
          </p>
        ) : null}
        {showUsageLink ? (
          <p>
            <Link to="/usage" className={linkClass}>
              {t.billing.meteringSeeUsage}
            </Link>
          </p>
        ) : null}
      </CollapsibleContent>
    </Collapsible>
  );
}
