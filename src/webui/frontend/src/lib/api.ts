export type CoordSpace = "pixel" | "norm1000";
export interface Dataset { name: string; screen_count: number; image_count: number; is_archived?: boolean }
export interface Model { id: string; coord_space: CoordSpace }
export interface Provider { provider?: string; name?: string; env_vars: string[]; env_var?: string; configured: boolean; env_configured?: boolean; session_configured?: boolean }
export interface Preflight { expected_total: number; already_done: number; results_csv: string; lock_present?: boolean; lock_holder?: string }
export interface StartedRun { run_id: string; equivalent_command?: string }
export interface RunSnapshot { status: string; lines?: string[]; next_since: number }
export interface CollectPreflight { adb_available: boolean; adb_path?: string; error?: string; devices?: Array<{serial: string; status: string}> }
export interface SmokeResult {
  ok: boolean; error?: string; hit?: number | null; target_text?: string; latency_seconds?: number;
  coord_space_detected?: string; coord_space_used?: string; coord_space_mismatch?: boolean;
  raw_response?: string; box?: number[]; x_pred?: number | null; y_pred?: number | null;
}

export class ApiError extends Error {
  readonly path: string;
  readonly status?: number;
  constructor(message: string, path: string, status?: number) { super(message); this.name = "ApiError"; this.path = path; this.status = status; }
}

export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, { ...options, headers: { "Content-Type": "application/json", ...(options?.headers ?? {}) } });
  } catch (error) {
    throw new ApiError(`Could not reach ${path}. Check that the API process is running.`, path);
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => ({})) as { detail?: string };
    throw new ApiError(payload.detail || `Request failed (${response.status})`, path, response.status);
  }
  const contentType = response.headers.get("content-type") || "";
  return (contentType.includes("application/json") ? response.json() : response) as Promise<T>;
}
export const enc = encodeURIComponent;
export const imageUrl = (dataset: string, screen: string, profile: string) => `/api/datasets/${enc(dataset)}/image/${enc(screen)}/${enc(profile)}?_=${Date.now()}`;
export const isTerminalRunStatus = (status: string) => ["completed", "failed", "cancelled"].includes(status);

export function readModels(): Model[] {
  try { const value = JSON.parse(localStorage.getItem("agb_models") || "[]"); return Array.isArray(value) ? value.filter((m): m is Model => Boolean(m?.id && (m.coord_space === "pixel" || m.coord_space === "norm1000"))) : []; } catch { return []; }
}
export function writeModels(models: Model[]) { localStorage.setItem("agb_models", JSON.stringify(models)); }
