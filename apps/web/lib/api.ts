// Browser-side helpers for the public API, shared by the map and insights panel.

export const API_BASE = (process.env.NEXT_PUBLIC_API_BASE_URL ||
  (process.env.NODE_ENV === "development" ? "http://localhost:8000/api/v1" : "/api/backend/api/v1")).replace(/\/$/, "");

// Free hosting sleeps when idle and takes about a minute to wake; the proxy gives up
// sooner (502/504). Retry these responses with growing delays (~90 s in total).
export const WAKE_RETRY_DELAYS_MS = [3_000, 6_000, 10_000, 15_000, 20_000, 20_000, 20_000];
const RETRYABLE_STATUSES = new Set([502, 503, 504]);

export class ApiError extends Error {}
class RetryableApiError extends ApiError {}

export function apiUrl(path: string, params: Record<string, string | number | undefined> = {}): URL {
  const endpoint = `${API_BASE}${path}`;
  const url = /^https?:\/\//i.test(endpoint) ? new URL(endpoint) : new URL(endpoint, window.location.origin);
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") url.searchParams.set(key, String(value));
  }
  return url;
}

/**
 * GET JSON, retrying while a sleeping API wakes. Returns null if `isCurrent`
 * reports the request was superseded, so callers can drop stale results.
 */
export async function getJsonWithWake<T>(
  url: URL,
  { onWaking, isCurrent = () => true }: { onWaking?: () => void; isCurrent?: () => boolean } = {},
): Promise<T | null> {
  for (let attempt = 0; ; attempt += 1) {
    try {
      let response: Response;
      try {
        response = await fetch(url.toString(), { cache: "no-store" });
      } catch {
        throw new RetryableApiError("the API could not be reached");
      }
      if (RETRYABLE_STATUSES.has(response.status)) throw new RetryableApiError(`API returned HTTP ${response.status}`);
      if (!response.ok) throw new ApiError(`API returned HTTP ${response.status}`);
      const body = await response.json() as T;
      return isCurrent() ? body : null;
    } catch (err) {
      if (!(err instanceof RetryableApiError) || attempt >= WAKE_RETRY_DELAYS_MS.length) throw err;
      if (!isCurrent()) return null;
      onWaking?.();
      await new Promise((resolve) => setTimeout(resolve, WAKE_RETRY_DELAYS_MS[attempt]));
      if (!isCurrent()) return null;
    }
  }
}

export function timeAgo(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return "never";
  const minutes = Math.max(0, Math.round((now - new Date(iso).getTime()) / 60_000));
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  return hours < 48 ? `${hours} h ago` : `${Math.round(hours / 24)} days ago`;
}

export function utcTime(iso: string): string {
  return `${new Date(iso).toISOString().slice(0, 16).replace("T", " ")} UTC`;
}
