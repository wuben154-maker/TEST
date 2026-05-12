/** Routes and slugs for the public marketing site (Solutions / Resources). */

export const MARKETING_SOLUTION_SLUGS = [
  "security-team",
  "security-leader",
  "mssp-mdr",
  "phishing-email",
  "malware-analysis",
  "threat-investigation",
] as const;

export type MarketingSolutionSlug = (typeof MARKETING_SOLUTION_SLUGS)[number];

/** Maps URL segment to i18n key under `marketing.solutionPages`. */
export const SOLUTION_SLUG_TO_I18N_KEY: Record<
  MarketingSolutionSlug,
  | "securityTeam"
  | "msspMdr"
  | "securityLeader"
  | "phishingEmail"
  | "malwareAnalysis"
  | "threatInvestigation"
> = {
  "security-team": "securityTeam",
  "mssp-mdr": "msspMdr",
  "security-leader": "securityLeader",
  "phishing-email": "phishingEmail",
  "malware-analysis": "malwareAnalysis",
  "threat-investigation": "threatInvestigation",
};

export function isMarketingSolutionSlug(value: string): value is MarketingSolutionSlug {
  return (MARKETING_SOLUTION_SLUGS as readonly string[]).includes(value);
}
