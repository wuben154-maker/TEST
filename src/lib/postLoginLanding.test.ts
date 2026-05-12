import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  dismissPostLoginLandingUI,
  markPostLoginLandingSession,
  readPostLoginLandingSession,
  POST_LOGIN_LANDING_DISMISS_EVENT,
  POST_LOGIN_LANDING_SHOW_EVENT,
  showPostLoginLandingUI,
} from '@/lib/postLoginLanding';

describe('postLoginLanding', () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  afterEach(() => {
    sessionStorage.clear();
  });

  it('dismissPostLoginLandingUI clears session and dispatches event', () => {
    markPostLoginLandingSession();
    expect(readPostLoginLandingSession()).toBe(true);

    const handler = vi.fn();
    window.addEventListener(POST_LOGIN_LANDING_DISMISS_EVENT, handler);

    dismissPostLoginLandingUI();

    expect(readPostLoginLandingSession()).toBe(false);
    expect(handler).toHaveBeenCalledTimes(1);

    window.removeEventListener(POST_LOGIN_LANDING_DISMISS_EVENT, handler);
  });

  it('showPostLoginLandingUI marks session and dispatches event', () => {
    expect(readPostLoginLandingSession()).toBe(false);

    const handler = vi.fn();
    window.addEventListener(POST_LOGIN_LANDING_SHOW_EVENT, handler);

    showPostLoginLandingUI();

    expect(readPostLoginLandingSession()).toBe(true);
    expect(handler).toHaveBeenCalledTimes(1);

    window.removeEventListener(POST_LOGIN_LANDING_SHOW_EVENT, handler);
  });
});
