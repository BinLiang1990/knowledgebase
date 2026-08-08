// Wraps every backend call so callers only ever see either the resolved
// `data` payload or a thrown ApiError with a user-facing message — never a
// raw fetch/JSON/HTTP-status error. docs/PRD.md §4.10: every response body
// is {code, data, msg}; code 200 = success, 444 = business/validation error
// (both surfaced with the same shape, see design doc §4.4/§4.5).

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000';

export class ApiError extends Error {}

interface Envelope<T> {
  code: number;
  data: T;
  msg: string;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...init?.headers },
    });
  } catch {
    // Network failure, CORS block, DNS error, etc. — none of these produce
    // a response body to parse, so there's no envelope to unwrap.
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
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) }),
  patch: <T>(path: string, body: unknown) =>
    request<T>(path, { method: 'PATCH', body: JSON.stringify(body) }),
};
