/**
 * DEV ONLY: apply JWT + user from URL hash into localStorage (same keys as api-client).
 * Used with `npm run auth:bootstrap` for local automation (/qa, design-review) without manual login.
 * Stripped in production builds via import.meta.env.DEV guard.
 */
const HASH_PREFIX = "#__secmanus_bootstrap=";

export function applyDevAuthHashBootstrap(): boolean {
  if (!import.meta.env.DEV) {
    return false;
  }

  const hash = window.location.hash;
  if (!hash.startsWith(HASH_PREFIX)) {
    return false;
  }

  try {
    const b64 = decodeURIComponent(hash.slice(HASH_PREFIX.length));
    const json = JSON.parse(atob(b64)) as { access_token?: string; user?: unknown };
    if (typeof json.access_token !== "string" || json.user === undefined || json.user === null) {
      return false;
    }

    localStorage.setItem("auth_token", json.access_token);
    localStorage.setItem("auth_user", JSON.stringify(json.user));

    const { pathname, search } = window.location;
    window.history.replaceState(null, "", pathname + search);
    window.location.reload();
    return true;
  } catch {
    return false;
  }
}
