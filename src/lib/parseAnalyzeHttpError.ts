/**
 * Parse FastAPI error bodies for POST /analyze and /analyze/resume.
 */

export type AnalyzeHttpError = { message: string; billingCode?: string };

export async function parseAnalyzeHttpError(
  response: Response
): Promise<AnalyzeHttpError> {
  try {
    const errorData: unknown = await response.json();
    if (errorData && typeof errorData === 'object') {
      const d = (errorData as { detail?: unknown }).detail;
      if (d && typeof d === 'object' && d !== null && 'error_code' in d) {
        const obj = d as { error_code?: string; detail?: string };
        return {
          message:
            typeof obj.detail === 'string'
              ? obj.detail
              : `HTTP ${response.status}`,
          billingCode: obj.error_code,
        };
      }
      if (typeof d === 'string') return { message: d };
      const err = (errorData as { error?: unknown }).error;
      if (typeof err === 'string') return { message: err };
    }
  } catch {
    /* non-JSON body */
  }
  return { message: `HTTP ${response.status}` };
}
