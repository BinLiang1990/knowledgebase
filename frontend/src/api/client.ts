// Wraps every backend call so callers only ever see either the resolved
// `data` payload or a thrown ApiError with a user-facing message — never a
// raw fetch/JSON/HTTP-status error. docs/PRD.md §4.10: every response body
// is {code, data, msg}; code 200 = success, 444 = business/validation error
// (both surfaced with the same shape, see design doc §4.4/§4.5).

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000';
// Guards against a hung request never resolving — found by the Kimi review
// gate on PR #22, which also flagged that a caller-provided AbortSignal
// (e.g. TanStack Query's own signal, cancelling on unmount/refetch) was
// never forwarded to fetch at all.
const REQUEST_TIMEOUT_MS = 10_000;

export class ApiError extends Error {}

interface Envelope<T> {
  code: number;
  data: T;
  msg: string;
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  signal?: AbortSignal;
}

async function request<T>(path: string, options?: RequestOptions): Promise<T> {
  const timeoutSignal = AbortSignal.timeout(REQUEST_TIMEOUT_MS);
  const signal = options?.signal ? AbortSignal.any([options.signal, timeoutSignal]) : timeoutSignal;
  const hasBody = options?.body !== undefined;

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method: options?.method,
      // Content-Type is not a CORS-safelisted header, so setting it on a
      // bodyless GET forces an unnecessary preflight OPTIONS round-trip
      // for every list fetch. Only set it when there's actually a JSON
      // body to describe. Found by the Kimi review gate on PR #22.
      headers: hasBody ? { 'Content-Type': 'application/json' } : undefined,
      body: hasBody ? JSON.stringify(options.body) : undefined,
      signal,
    });
  } catch {
    // Network failure, CORS block, DNS error, timeout/abort, etc. — none of
    // these produce a response body to parse, so there's no envelope to
    // unwrap.
    throw new ApiError('网络异常，请稍后重试');
  }

  let body: Envelope<T>;
  try {
    body = await response.json();
  } catch {
    throw new ApiError('网络异常，请稍后重试');
  }

  if (body.code !== 200) {
    throw new ApiError(body.msg || '操作失败');
  }
  return body.data;
}

export const apiClient = {
  get: <T>(path: string, options?: { signal?: AbortSignal }) => request<T>(path, options),
  post: <T>(path: string, body?: unknown, options?: { signal?: AbortSignal }) =>
    request<T>(path, { ...options, method: 'POST', body }),
  patch: <T>(path: string, body: unknown, options?: { signal?: AbortSignal }) =>
    request<T>(path, { ...options, method: 'PATCH', body }),
  put: <T>(path: string, body: unknown, options?: { signal?: AbortSignal }) =>
    request<T>(path, { ...options, method: 'PUT', body }),
};
