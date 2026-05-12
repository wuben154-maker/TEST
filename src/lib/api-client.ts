/**
 * API Client abstraction layer
 * Frontend talks only to the FastAPI backend.
 */

import { config, analysisEndpoints, isLocalMode as isLocalModeConfig } from "@/lib/config";
import { detectBrowserLanguage, getTranslations } from "@/i18n";
import { logger } from "@/lib/logger";

// Storage keys
const TOKEN_KEY = "auth_token";
const USER_KEY = "auth_user";

// Resolve backend base URL (local vs deployed)
const getApiBaseUrl = () => {
  return isLocalModeConfig() ? config.localApiUrl : config.pythonBackendUrl;
};

/** IANA zone for backend dynamic timestamps (X-Client-Timezone). */
export const CLIENT_TIMEZONE_HEADER = "X-Client-Timezone";

export function getClientTimezoneHeaders(): Record<string, string> {
  try {
    const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
    return { [CLIENT_TIMEZONE_HEADER]: tz || "UTC" };
  } catch {
    return { [CLIENT_TIMEZONE_HEADER]: "UTC" };
  }
}

// Common helper: build headers with optional JWT token
const buildAuthHeaders = (extraHeaders: Record<string, string> = {}) => {
  const token = getAuthToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...getClientTimezoneHeaders(),
    ...extraHeaders,
  };

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  return headers;
};

/**
 * Get stored auth token (JWT)
 */
export const getAuthToken = (): string | null => {
  return localStorage.getItem(TOKEN_KEY);
};

/**
 * Store auth token (JWT)
 */
export const setAuthToken = (token: string | null): void => {
  if (token) {
    localStorage.setItem(TOKEN_KEY, token);
  } else {
    localStorage.removeItem(TOKEN_KEY);
  }
};

/**
 * Get stored user
 */
export const getStoredUser = (): any | null => {
  const user = localStorage.getItem(USER_KEY);
  return user ? JSON.parse(user) : null;
};

/**
 * Store user
 */
export const setStoredUser = (user: any | null): void => {
  if (user) {
    localStorage.setItem(USER_KEY, JSON.stringify(user));
  } else {
    localStorage.removeItem(USER_KEY);
  }
};

function generateRequestId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `req-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

/** Options beyond `RequestInit`; stripped before `fetch()`. */
export type ApiFetchOptions = RequestInit & {
  /** When true, HTTP 404 resolves to `null` instead of throwing (no error log). */
  nullIfNotFound?: boolean;
};

/**
 * Make authenticated request to backend API
 */
const apiFetch = async <T = unknown>(path: string, options: ApiFetchOptions = {}) => {
  const { nullIfNotFound, ...fetchInit } = options;
  const requestId = generateRequestId();
  const headers = buildAuthHeaders(fetchInit.headers as Record<string, string> | undefined);
  headers["x-request-id"] = requestId;
  const url = `${getApiBaseUrl()}${path}`;

  let response: Response;
  try {
    response = await fetch(url, { ...fetchInit, headers });
  } catch (e) {
    const msg = e instanceof TypeError && e.message === "Failed to fetch"
      ? "无法连接到后端，请确认服务已启动"
      : (e instanceof Error ? e.message : "Network error");
    logger.error("api_request_network_error", { request_id: requestId, url: path, error: msg });
    throw new Error(msg);
  }

  if (!response.ok) {
    if (nullIfNotFound && response.status === 404) {
      return null as T | null;
    }
    const error = await response.json().catch(() => ({ detail: "Request failed" }));
    const detail = error.detail;
    const msg = typeof detail === "string" ? detail : (detail?.msg || detail?.message || JSON.stringify(detail || error));
    logger.error("api_request_failed", { request_id: requestId, url: path, status: response.status, detail: msg });
    throw new Error(msg || `HTTP ${response.status}`);
  }

  return response.json() as Promise<T>;
};

export type AccountOverview = {
  project_count: number;
  analysis_sessions_count: number;
  total_llm_tokens_lifetime: number;
};

export type LoginHistoryRow = {
  id: string;
  logged_in_at: string;
  ip_address?: string | null;
  user_agent?: string | null;
  /** Country/region label from server geo lookup, e.g. "China (CN)" or "Local". */
  ip_country?: string | null;
};

// ============================================
// Auth API
// ============================================

export const authApi = {
  async register(email: string, password: string, username?: string) {
    const result = await apiFetch("/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password, username }),
    });
    setAuthToken(result.access_token);
    setStoredUser(result.user);
    return { data: result, error: null };
  },

  async login(email: string, password: string) {
    const result = await apiFetch("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    setAuthToken(result.access_token);
    setStoredUser(result.user);
    return { data: result, error: null };
  },

  async logout() {
    try {
      await apiFetch("/auth/logout", { method: "POST" });
    } catch {
      // Ignore backend errors on logout, just clear local state
    }
    setAuthToken(null);
    setStoredUser(null);
    return { error: null };
  },

  async getSession() {
    const token = getAuthToken();
    const user = getStoredUser();
    if (token && user) {
      return { data: { session: { access_token: token }, user }, error: null };
    }
    return { data: { session: null, user: null }, error: null };
  },

  async getUser() {
    const token = getAuthToken();
    if (!token) return { data: null, error: null };
    try {
      const user = await apiFetch("/auth/me");
      setStoredUser(user);
      return { data: user, error: null };
    } catch (e: any) {
      setAuthToken(null);
      setStoredUser(null);
      return { data: null, error: e };
    }
  },

  async patchProfile(username: string) {
    const user = await apiFetch("/auth/profile", {
      method: "PATCH",
      body: JSON.stringify({ username }),
    });
    setStoredUser(user);
    return { data: user, error: null };
  },

  async getLoginHistory(limit = 10) {
    const q = new URLSearchParams({ limit: String(limit) });
    const items = await apiFetch(`/auth/login-history?${q.toString()}`);
    return { data: items as LoginHistoryRow[], error: null };
  },

  onAuthStateChange(callback: (event: string, session: any) => void) {
    // No real-time auth events from backend; simulate initial state only.
    const token = getAuthToken();
    const user = getStoredUser();
    if (token && user) {
      setTimeout(() => callback("SIGNED_IN", { access_token: token, user }), 0);
    } else {
      setTimeout(() => callback("SIGNED_OUT", null), 0);
    }
    // Return unsubscribe function for API compatibility
    return { data: { subscription: { unsubscribe: () => {} } } };
  },
};

export const accountApi = {
  async getOverview(): Promise<AccountOverview> {
    return apiFetch("/account/overview");
  },
};

// ============================================
// Billing / usage (FastAPI)
// ============================================

export type LocalizedText = Partial<Record<string, string>>;

export type PlanFeatureItem = {
  id: string;
  text: LocalizedText;
};

export type PlanQuotaHint = {
  id: string;
  value: string;
  label?: LocalizedText;
};

export type BillingPlanRow = {
  slug: string;
  display_name: string;
  monthly_price_usd: number;
  sort_order: number;
  included_credits_usd: number;
  credits_label: string;
  tagline_json?: LocalizedText;
  features_json?: PlanFeatureItem[];
  quota_hints?: PlanQuotaHint[];
};

export const billingApi = {
  async getPlans(): Promise<{ plans: BillingPlanRow[]; credits_per_usd?: number }> {
    return apiFetch("/billing/plans");
  },

  async getSummary(): Promise<Record<string, unknown>> {
    return apiFetch("/billing/summary");
  },

  async createCheckout(planSlug: "pro" | "ultra"): Promise<{ url: string; session_id: string }> {
    return apiFetch("/billing/checkout", {
      method: "POST",
      body: JSON.stringify({ plan_slug: planSlug }),
    });
  },

  async createPortal(): Promise<{ url: string }> {
    return apiFetch("/billing/portal", { method: "POST", body: JSON.stringify({}) });
  },

  async getUsageEvents(
    limit = 50,
    offset = 0
  ): Promise<{
    items: Record<string, unknown>[];
    limit: number;
    offset: number;
    has_more?: boolean;
    total?: number;
    credits_per_usd?: number;
    usage_persistence?: string;
    reason?: string;
  }> {
    const q = new URLSearchParams({
      limit: String(limit),
      offset: String(offset),
    });
    return apiFetch(`/usage/events?${q.toString()}`);
  },
};

// ============================================
// Registry catalog (Python agent service — subagents + global skills)
// ============================================

export type RegistryCatalogSkill = {
  directory_name: string;
  name: string;
  description: string;
  enabled_for_main_agent?: boolean;
};

export type RegistryCatalogSubagent = {
  id: string;
  purpose: string;
  runtime: string;
  tool_profile: string;
  include_shared_skills: boolean;
  extra_skill_package_ids: string[];
  bundle_skills: Omit<RegistryCatalogSkill, "enabled_for_main_agent">[];
  attached_global_skills: RegistryCatalogSkill[];
};

export const registryApi = {
  async getSubagents(): Promise<{ subagents: RegistryCatalogSubagent[] }> {
    return apiFetch("/registry/subagents");
  },

  async getGlobalSkills(): Promise<{ skills: RegistryCatalogSkill[] }> {
    return apiFetch("/registry/skills");
  },
};

// ============================================
// Projects API
// ============================================

export const projectsApi = {
  async list() {
    const projects = await apiFetch("/projects");
    return { data: projects, error: null };
  },

  async create(title?: string) {
    const defaultTitle =
      title || getTranslations(detectBrowserLanguage()).sidebar.newConversation;
    const project = await apiFetch("/projects", {
      method: "POST",
      body: JSON.stringify({ title: defaultTitle }),
    });
    return { data: project, error: null };
  },

  async get(projectId: string) {
    const project = await apiFetch(`/projects/${projectId}`);
    return { data: project, error: null };
  },

  async update(projectId: string, updates: { title?: string }) {
    const project = await apiFetch(`/projects/${projectId}`, {
      method: "PATCH",
      body: JSON.stringify(updates),
    });
    return { data: project, error: null };
  },

  /**
   * Persist the realtime context-usage reducer snapshot for a project
   * (feature: realtime-context-usage-indicator).
   *
   * Passing ``null`` explicitly clears the stored payload on the server and
   * bumps ``context_usage_updated_at`` — this is what the frontend should
   * send on project delete or when the user resets state.
   *
   * The wire format matches the server's ``ProjectUpdate`` pydantic model:
   * ``{"context_usage": <payload or null>}``. Returns a fire-and-forget
   * promise; callers use this for background flushes so they shouldn't
   * block on it. Errors are swallowed into ``error`` to match the rest of
   * ``projectsApi``.
   */
  async updateContextUsage(
    projectId: string,
    payload: Record<string, unknown> | null,
  ) {
    try {
      const project = await apiFetch(`/projects/${projectId}`, {
        method: "PATCH",
        body: JSON.stringify({ context_usage: payload }),
        /** Row may already be gone (delete race, stale client id) — treat as cleared. */
        nullIfNotFound: true,
      });
      return { data: project, error: null as Error | null };
    } catch (e) {
      // Background flush must never throw up to the UI — surface via the
      // ``error`` field so tests + callers can observe it, but don't blow
      // up the streaming pipeline when the backend is momentarily down.
      return { data: null, error: e as Error };
    }
  },

  async delete(projectId: string) {
    await apiFetch(`/projects/${projectId}`, { method: "DELETE" });
    return { error: null };
  },

  async getAnalysisProgress(projectId: string) {
    const data = await apiFetch(`/projects/${projectId}/analysis-progress`);
    return { data: data as AnalysisProgress | null, error: null };
  },

  async cancelAnalysisProgress(projectId: string) {
    await apiFetch(`/projects/${projectId}/analysis-progress/cancel`, {
      method: "POST",
    });
    return { error: null };
  },
};

export interface AnalysisProgress {
  is_analyzing: boolean;
  /** Correlates with ``messages.request_id`` for the active /analyze leg. */
  request_id?: string;
  /** Same as POST /analyze `ui_language` for this running leg (refresh + HITL resume). */
  ui_language?: string;
  user_input: string;
  thinking_steps: any[];
  task_plan: any;
  understanding: any;
  task_summary: string;
  conclusion: string;
  blocks: any[];
  /** Canonical SSE rows for ReAct replay (same shape as messages.timeline). */
  timeline?: unknown[];
  updated_at: string;
}

// ============================================
// Messages API
// ============================================

export const messagesApi = {
  async create(message: {
    project_id: string;
    type: string;
    content: string;
    request_id?: string;
    reasoning?: string;
    blocks?: any[];
    timeline?: any[];
    stats?: Record<string, unknown>;
    workspace_tabs?: any[];
  }) {
    const result = await apiFetch("/messages", {
      method: "POST",
      body: JSON.stringify(message),
    });
    return { data: result, error: null };
  },

  async listByProject(projectId: string, limit = 100) {
    const messages = await apiFetch(`/messages/project/${projectId}?limit=${limit}`);
    return { data: messages, error: null };
  },

  async delete(messageId: string) {
    await apiFetch(`/messages/${messageId}`, { method: "DELETE" });
    return { error: null };
  },

  async updateTitle(messageId: string, title: string) {
    await apiFetch(`/messages/${messageId}/title`, {
      method: "PATCH",
      body: JSON.stringify({ title }),
    });
    return { error: null };
  },

  /** Persist knowledge-base deeplink JSON on the assistant row (same ``request_id`` as client ``requestId``). */
  async patchKnowledgeArchive(projectId: string, requestId: string, knowledgeArchive: Record<string, unknown>) {
    await apiFetch("/messages/knowledge-archive", {
      method: "PATCH",
      body: JSON.stringify({
        project_id: projectId,
        request_id: requestId,
        knowledge_archive: knowledgeArchive,
      }),
    });
    return { error: null };
  },
};

export const analysisApi = {
  getStreamUrl() {
    return analysisEndpoints.stream;
  },

  getAuthHeaders(): Record<string, string> {
    const token = getAuthToken();
    return {
      ...getClientTimezoneHeaders(),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    };
  },

  async cancelAnalysis(requestId: string): Promise<void> {
    try {
      await fetch(analysisEndpoints.cancelStream, {
        method: "POST",
        headers: buildAuthHeaders(),
        body: JSON.stringify({ request_id: requestId }),
      });
    } catch {
      // Fire-and-forget: best-effort cancellation
    }
  },
};

// ============================================
// Knowledge base (stored .docx under knowledge/<user_id>/)
// ============================================

export type KnowledgeItem = {
  filename: string;
  /** Human-readable title (report name), not filesystem path */
  display_name: string;
  /** Project/workspace this report was archived from — open in workspace when set */
  project_id?: string | null;
  /** Same as SSE `messages.request_id` / analysis run id when indexer stored it */
  message_id?: string | null;
  size_bytes: number;
  updated_at: string;
  /** Legacy/virtual path hint e.g. Workspace/knowledge/name.docx */
  display_path: string;
};

/** POST multipart — do not set Content-Type so the browser sends multipart boundary. */
export const knowledgeApi = {
  async list(): Promise<{ items: KnowledgeItem[] }> {
    return apiFetch("/knowledge");
  },

  async uploadReport(
    form: FormData,
    options?: { signal?: AbortSignal },
  ): Promise<Record<string, unknown>> {
    const token = getAuthToken();
    if (!token) throw new Error("Not authenticated");
    const requestId = generateRequestId();
    const headers: Record<string, string> = {
      ...getClientTimezoneHeaders(),
      "x-request-id": requestId,
      Authorization: `Bearer ${token}`,
    };
    const url = `${getApiBaseUrl()}/knowledge/reports`;
    let response: Response;
    try {
      response = await fetch(url, {
        method: "POST",
        headers,
        body: form,
        signal: options?.signal,
      });
    } catch (e) {
      const msg = e instanceof TypeError ? "Cannot reach backend" : String(e);
      throw new Error(msg);
    }
    if (!response.ok) {
      const errBody = await response.json().catch(() => ({ detail: "Failed" }));
      const detail = errBody.detail;
      const out =
        typeof detail === "string" ? detail : JSON.stringify(errBody.detail ?? errBody);
      throw new Error(out || `HTTP ${response.status}`);
    }
    return response.json();
  },

  async downloadBlob(filename: string): Promise<Blob> {
    const token = getAuthToken();
    if (!token) throw new Error("Not authenticated");
    const requestId = generateRequestId();
    const q = new URLSearchParams({ filename });
    const headers: Record<string, string> = {
      ...getClientTimezoneHeaders(),
      "x-request-id": requestId,
      Authorization: `Bearer ${token}`,
    };
    const url = `${getApiBaseUrl()}/knowledge/download?${q.toString()}`;
    const response = await fetch(url, { headers });
    if (!response.ok) {
      throw new Error(`Download failed (${response.status})`);
    }
    return response.blob();
  },
};

// ============================================
// Backend Health API
// ============================================

export interface BackendHealthInfo {
  status: string;
  version: string;
  build_date?: string;
  framework: string;
  agent_mode: string;
  database_mode: string;
  feature_flags?: Record<string, boolean>;
  skills?: {
    available: string[];
    count: number;
    directory: string;
  };
  workflow_enabled_skills?: Array<{
    name: string;
    steps_count: number;
    steps: string[];
  }>;
}

export const backendApi = {
  /**
   * Get Python backend health and version info
   */
  async getHealth(): Promise<{ data: BackendHealthInfo | null; error: Error | null }> {
    try {
      const response = await fetch(analysisEndpoints.health, {
        method: 'GET',
        headers: { Accept: "application/json", ...getClientTimezoneHeaders() },
      });
      
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      
      const data = await response.json();
      return { data, error: null };
    } catch (e: any) {
      return { data: null, error: e };
    }
  },
};

