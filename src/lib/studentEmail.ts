/**
 * Heuristic "student / academic email" detection from the mailbox domain.
 * Not a legal identity check — used only for UI labeling.
 */
const ACADEMIC_SECOND_LEVEL = new Set([
  "ac.uk",
  "ac.jp",
  "ac.kr",
  "ac.nz",
  "edu",
  "edu.au",
  "edu.cn",
  "edu.hk",
  "edu.sg",
  "edu.tw",
]);

function domainParts(host: string): string[] {
  return host.split(".").filter(Boolean);
}

export function isStudentOrAcademicEmail(email: string | undefined | null): boolean {
  if (!email || typeof email !== "string") return false;
  const at = email.lastIndexOf("@");
  if (at < 0 || at === email.length - 1) return false;
  const host = email.slice(at + 1).trim().toLowerCase();
  if (!host) return false;

  if (host.endsWith(".edu") || host === "edu") return true;

  const parts = domainParts(host);
  if (parts.length >= 2) {
    const tld = parts[parts.length - 1];
    const sld = `${parts[parts.length - 2]}.${tld}`;
    if (ACADEMIC_SECOND_LEVEL.has(sld)) return true;
    if (tld === "edu") return true;
  }

  if (host.startsWith("student.") || host.includes(".student.")) return true;

  return false;
}
