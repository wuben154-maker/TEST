/**
 * Backend endpoint configuration
 * Uses VITE_* env vars when set; otherwise falls back to defaults.
 */

const env = import.meta.env;

export const endpointsConfig = {
  pythonBackendUrl: env.VITE_PYTHON_BACKEND_URL || "https://secmanus-workspace-production.up.railway.app",
  localApiUrl: env.VITE_LOCAL_API_URL || "http://127.0.0.1:8000",
} as const;
