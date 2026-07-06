/**
 * Server-only client for the Mobi estimating engine (FastAPI service).
 *
 * The engine runs as a separate service (see infra: Caddy -> uvicorn on the
 * VPS) and is reachable at MOBI_ENGINE_BASE_URL, gated by a shared secret in
 * MOBI_ENGINE_API_KEY. Never import this from a client component and never
 * expose either value with a NEXT_PUBLIC_ prefix.
 */

const BASE_URL = process.env.MOBI_ENGINE_BASE_URL;
const API_KEY = process.env.MOBI_ENGINE_API_KEY;

/** True when both the engine URL and API key are configured. */
export function engineConfigured(): boolean {
  return Boolean(BASE_URL && API_KEY);
}

/** Mirror of the engine's ProjectStatusResponse (app/schemas.py). */
export interface EngineProject {
  project_id: string;
  name: string;
  status: string;
  original_file_name: string | null;
  page_count: number;
  file_sha256: string | null;
  file_size_bytes: number;
  created_at: string;
  updated_at: string;
  error_message: string | null;
}

async function engineErrorMessage(res: Response): Promise<string> {
  try {
    const body = await res.json();
    // Engine envelope: { error: { code, message } }; FastAPI default: { detail }.
    return body?.error?.message || body?.detail || `Engine returned ${res.status}.`;
  } catch {
    return `Engine returned ${res.status}.`;
  }
}

export async function engineGetJson<T>(path: string): Promise<T> {
  if (!engineConfigured()) {
    throw new Error("The estimating engine is not configured on this deployment.");
  }
  const res = await fetch(`${BASE_URL}${path}`, {
    method: "GET",
    headers: { "X-API-Key": API_KEY! },
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(await engineErrorMessage(res));
  }
  return (await res.json()) as T;
}

export async function enginePostJson<T>(path: string, body?: unknown): Promise<T> {
  if (!engineConfigured()) {
    throw new Error("The estimating engine is not configured on this deployment.");
  }
  const headers: Record<string, string> = { "X-API-Key": API_KEY! };
  const init: RequestInit = { method: "POST", headers, cache: "no-store" };
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }
  const res = await fetch(`${BASE_URL}${path}`, init);
  if (!res.ok) {
    throw new Error(await engineErrorMessage(res));
  }
  return (await res.json()) as T;
}

/**
 * Upload a PDF plan set to the engine, creating an engine-side project record.
 * The engine validates and stores the PDF; it does not run takeoff/pricing here.
 */
export async function engineUploadPlan(opts: {
  projectName: string;
  contractorName?: string | null;
  file: Blob;
  fileName: string;
}): Promise<EngineProject> {
  if (!engineConfigured()) {
    throw new Error("The estimating engine is not configured on this deployment.");
  }

  const form = new FormData();
  form.append("project_name", opts.projectName);
  if (opts.contractorName) form.append("contractor_name", opts.contractorName);
  form.append("plan", opts.file, opts.fileName);

  const res = await fetch(`${BASE_URL}/api/v1/projects/upload`, {
    method: "POST",
    headers: { "X-API-Key": API_KEY! },
    body: form,
    cache: "no-store",
  });

  if (!res.ok) {
    throw new Error(await engineErrorMessage(res));
  }
  return (await res.json()) as EngineProject;
}

/** Fetch the current status of an engine-side project. */
export async function engineGetStatus(engineProjectId: string): Promise<EngineProject> {
  if (!engineConfigured()) {
    throw new Error("The estimating engine is not configured on this deployment.");
  }
  const res = await fetch(`${BASE_URL}/api/v1/projects/${engineProjectId}/status`, {
    method: "GET",
    headers: { "X-API-Key": API_KEY! },
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(await engineErrorMessage(res));
  }
  return (await res.json()) as EngineProject;
}
