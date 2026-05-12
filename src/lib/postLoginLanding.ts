/** Session flag: after Auth, show PostLoginWorkspaceStart at least once (even if user has projects). */
export const POST_LOGIN_LANDING_SESSION_KEY = 'secmanus_after_auth_show_start';

export function markPostLoginLandingSession(): void {
  try {
    sessionStorage.setItem(POST_LOGIN_LANDING_SESSION_KEY, '1');
  } catch {
    /* private mode / quota */
  }
}

export function clearPostLoginLandingSession(): void {
  try {
    sessionStorage.removeItem(POST_LOGIN_LANDING_SESSION_KEY);
  } catch {
    /* ignore */
  }
}

export function readPostLoginLandingSession(): boolean {
  try {
    return sessionStorage.getItem(POST_LOGIN_LANDING_SESSION_KEY) === '1';
  } catch {
    return false;
  }
}

/** Same-tab event so `Index` can sync `showAuthLanding` when the shell handles sidebar actions. */
export const POST_LOGIN_LANDING_DISMISS_EVENT = 'secmanus:dismiss-post-login-landing';

/**
 * Clears the post-auth landing session flag and notifies listeners (e.g. Index) to leave PostLoginWorkspaceStart.
 * Use when ProjectSidebar selects/creates a project — shell cannot set Index state directly.
 */
export function dismissPostLoginLandingUI(): void {
  clearPostLoginLandingSession();
  if (typeof window === 'undefined') return;
  try {
    window.dispatchEvent(new CustomEvent(POST_LOGIN_LANDING_DISMISS_EVENT));
  } catch {
    /* ignore */
  }
}

/** Same-tab event so `Index` can show PostLoginWorkspaceStart when the shell requests it (e.g. sidebar Create Project). */
export const POST_LOGIN_LANDING_SHOW_EVENT = 'secmanus:show-post-login-landing';

/**
 * Fired from `Index` after the transition composer successfully creates a project and starts analysis.
 * `AppWorkspaceShell` listens and collapses the project rail (desktop) and closes the mobile drawer.
 */
export const WORKSPACE_START_COLLAPSE_SIDEBAR_EVENT = 'secmanus:workspace-start-collapse-sidebar';

/**
 * Marks session and notifies Index to render the workspace transition page (composer shell).
 * Does not create a project — user names the project after submitting from that page.
 */
export function showPostLoginLandingUI(): void {
  markPostLoginLandingSession();
  if (typeof window === 'undefined') return;
  try {
    window.dispatchEvent(new CustomEvent(POST_LOGIN_LANDING_SHOW_EVENT));
  } catch {
    /* ignore */
  }
}
