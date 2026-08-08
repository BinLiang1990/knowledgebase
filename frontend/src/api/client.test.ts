import { describe, expect, it } from 'vitest';
import { apiClient, ApiError } from './client';
import { API_BASE, HttpResponse, envelope, errorEnvelope, http, server } from '../test/server';

describe('apiClient', () => {
  it('returns data when code is 200', async () => {
    server.use(http.get(`${API_BASE}/probe`, () => HttpResponse.json(envelope({ ok: true }))));
    await expect(apiClient.get('/probe')).resolves.toEqual({ ok: true });
  });

  it('throws ApiError with the backend msg when code is 444', async () => {
    server.use(http.get(`${API_BASE}/probe`, () => HttpResponse.json(errorEnvelope('知识库名称已存在'))));
    await expect(apiClient.get('/probe')).rejects.toThrow(ApiError);
    await expect(apiClient.get('/probe')).rejects.toThrow('知识库名称已存在');
  });

  it('throws a generic ApiError on network failure, not a raw fetch error', async () => {
    server.use(http.get(`${API_BASE}/probe`, () => HttpResponse.error()));
    await expect(apiClient.get('/probe')).rejects.toThrow(ApiError);
    await expect(apiClient.get('/probe')).rejects.toThrow('网络异常');
  });

  it('throws a generic ApiError when the response body is not valid JSON', async () => {
    server.use(http.get(`${API_BASE}/probe`, () => new HttpResponse('not json', { status: 500 })));
    await expect(apiClient.get('/probe')).rejects.toThrow(ApiError);
  });

  it('post sends a JSON body', async () => {
    let receivedBody: unknown;
    server.use(
      http.post(`${API_BASE}/probe`, async ({ request }) => {
        receivedBody = await request.json();
        return HttpResponse.json(envelope({ ok: true }));
      }),
    );
    await apiClient.post('/probe', { name: 'x' });
    expect(receivedBody).toEqual({ name: 'x' });
  });
});
