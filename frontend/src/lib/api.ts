/** Small fetch wrapper: same-origin cookies, CSRF header on writes, readable errors. */
export class ApiError extends Error {
  status: number;
  /** Extra hints some endpoints send with an error (the onboarding screens use them). */
  field?: string;
  restart?: boolean;
  expired?: boolean;
  resend_in?: number;
  constructor(message: string, status: number, extra: Partial<Pick<ApiError, "field" | "restart" | "expired" | "resend_in">> = {}) {
    super(message);
    this.status = status;
    Object.assign(this, extra);
  }
}

let csrfToken = "";
export function setCsrfToken(token: string) {
  csrfToken = token;
}

const FALLBACK: Record<number, string> = {
  400: "That request wasn't valid.",
  401: "Your session has ended. Please sign in again.",
  403: "You don't have permission to do that.",
  404: "We couldn't find that.",
  413: "That upload is too large.",
  429: "Too many attempts. Please wait a little and try again.",
};

async function request<T>(method: string, url: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  let payload: BodyInit | undefined;
  if (body instanceof FormData) {
    payload = body;
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  if (method !== "GET") headers["X-CSRFToken"] = csrfToken;

  let res: Response;
  try {
    res = await fetch(url, { method, headers, body: payload, credentials: "same-origin" });
  } catch {
    throw new ApiError("Can't reach the server. Check your connection and try again.", 0);
  }
  if (res.status === 401) {
    window.dispatchEvent(new CustomEvent("cr:signed-out"));
  }
  const data = (res.headers.get("content-type") || "").includes("application/json")
    ? await res.json().catch(() => ({}))
    : {};
  if (!res.ok) {
    const d = data as { error?: string; field?: string; restart?: boolean; expired?: boolean; resend_in?: number };
    throw new ApiError(d.error || FALLBACK[res.status] || "Something went wrong. Please try again.", res.status,
      { field: d.field, restart: d.restart, expired: d.expired, resend_in: d.resend_in });
  }
  return data as T;
}

export const api = {
  get: <T>(url: string) => request<T>("GET", url),
  post: <T = { status: string }>(url: string, body?: unknown) => request<T>("POST", url, body ?? {}),
};

export function qs(params: Record<string, string | number | undefined | null>) {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") p.set(k, String(v));
  const s = p.toString();
  return s ? `?${s}` : "";
}
