const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const DEFAULT_TIMEOUT_MS = 12 * 60 * 1000;
const TOKEN_KEY = "document-assistant-token";
const VISITOR_ID_KEY = "document-assistant-visitor-id";

export function getStoredToken(): string | null {
  return window.localStorage.getItem(TOKEN_KEY);
}

function getVisitorId(): string {
  const storedVisitorId = window.localStorage.getItem(VISITOR_ID_KEY);
  if (storedVisitorId) {
    return storedVisitorId;
  }

  const visitorId = window.crypto.randomUUID();
  window.localStorage.setItem(VISITOR_ID_KEY, visitorId);
  return visitorId;
}

export async function apiFetch(
  path: string,
  init: RequestInit = {},
  timeoutMs = DEFAULT_TIMEOUT_MS,
): Promise<Response> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  const headers = new Headers(init.headers);
  headers.set("X-Visitor-ID", getVisitorId());

  const token = getStoredToken();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers,
      signal: controller.signal,
    });

    return response;
  } catch (error) {
    if (error instanceof Error && error.name === "AbortError") {
      throw new Error("The request timed out. Please try again.");
    }
    throw error;
  } finally {
    window.clearTimeout(timeout);
  }
}

export async function getApiErrorMessage(
  response: Response,
  fallback: string,
): Promise<string> {
  try {
    const error = await response.json();
    const detail = error.detail;

    if (typeof detail === "string") {
      return detail;
    }
    if (Array.isArray(detail)) {
      return detail
        .map((item: { msg?: string }) => item.msg)
        .filter((message: unknown): message is string => typeof message === "string")
        .join(" ");
    }
  } catch {
    return fallback;
  }

  return fallback;
}
