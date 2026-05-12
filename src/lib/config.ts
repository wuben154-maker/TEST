/**
 * Application configuration
 * Centralized configuration for environment variables and app settings
 *
 * Backend URLs are loaded from src/config/endpoints.ts
 * Edit that file to change the backend addresses.
 */

import { endpointsConfig } from '@/config/endpoints';

// ============================================
// ENVIRONMENT VARIABLES (Frontend)
// ============================================
// VITE_API_MODE - API mode: 'local' or 'cloud'

// API Mode detection
export const isLocalMode = (): boolean => {
  return import.meta.env.VITE_API_MODE === 'local';
};

// Backend URLs (loaded from config file)
export const config = {
  // Python DeepAgent backend URL
  pythonBackendUrl: endpointsConfig.pythonBackendUrl,
  
  // Local API URL for local development mode
  localApiUrl: endpointsConfig.localApiUrl,
} as const;

/** Active backend base URL (local or cloud based on VITE_API_MODE) */
export const activeApiBaseUrl = isLocalMode()
  ? config.localApiUrl
  : config.pythonBackendUrl;

// Analysis API endpoints (derived from active backend base URL)
export const analysisEndpoints = {
  stream: `${activeApiBaseUrl}/analyze`,
  resumeStream: `${activeApiBaseUrl}/analyze/resume`,
  cancelStream: `${activeApiBaseUrl}/analyze/cancel`,
  uploads: `${activeApiBaseUrl}/uploads`,
  submitParameters: `${activeApiBaseUrl}/submit-parameters`,
  health: `${activeApiBaseUrl}/health`,
  models: `${activeApiBaseUrl}/api/models`,
} as const;

/** Max files per upload batch (align with python-agent-service MAX_UPLOAD_FILES_PER_BATCH). */
export const maxUploadFilesPerBatch = Number.parseInt(
  import.meta.env.VITE_MAX_UPLOAD_FILES ?? '10',
  10,
);

/** Max bytes per file (default 100 MiB; align with server). */
export const maxUploadBytesPerFile = Number.parseInt(
  import.meta.env.VITE_MAX_UPLOAD_BYTES_PER_FILE ?? String(100 * 1024 * 1024),
  10,
);

/**
 * Max characters of `tool_result.toolOutput` stored in ReAct timeline (`toolOutput`
 * for expanded `<pre>`). Default matches python-agent-service defaults for
 * `SSE_TOOL_RESULT_MAX_BLOCK_CHARS` / `SSE_TOOL_RESULT_MAX_SCALAR_CHARS` (2000).
 *
 * @see python-agent-service/app/config/settings.py — sse_tool_result_max_block_chars
 */
export const toolOutputTimelineMaxChars = (() => {
  const raw = import.meta.env.VITE_SSE_TOOL_RESULT_DISPLAY_MAX_CHARS;
  const n =
    raw != null && raw !== ''
      ? Number.parseInt(String(raw), 10)
      : Number.NaN;
  if (Number.isFinite(n) && n >= 1) {
    return Math.min(Math.floor(n), 2_000_000);
  }
  return 2000;
})();

// Export for debugging
export const getConfigSummary = () => ({
  mode: isLocalMode() ? 'local' : 'cloud',
  activeApiBaseUrl,
  pythonBackendUrl: config.pythonBackendUrl,
  localApiUrl: config.localApiUrl,
  isConfigured: true,
});
