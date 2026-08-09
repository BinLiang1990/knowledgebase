import { describe, expect, it } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { useCreateAnswer, useEditAnswer } from './answers';
import { useCreateKnowledgePoint, useUpdateKnowledgePointTitle } from './knowledgePoints';
import { useGlobalChangeLog } from './changeLog';
import { API_BASE, HttpResponse, envelope, http, makeAnswer, makeGlobalChangeLogEntry, makeKp, server } from '../test/server';

// Regression for the Kimi 终审 finding on PR #30: useRevokeAnswer was the
// only mutation invalidating the global change-log cache; write mutations
// that also produce/alter a change-log-visible fact (a new answer, a
// renamed knowledge point) were missed, leaving a cached /change-log page
// stale. These tests mount a probe on useGlobalChangeLog and a mutation
// hook against the SAME QueryClient, then assert the probe's query
// actually refetches after the mutation succeeds.
function makeWrapper(queryClient: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

describe('global change-log invalidation', () => {
  it('useCreateAnswer invalidates the global change-log', async () => {
    let fetchCount = 0;
    server.use(
      http.get(`${API_BASE}/change-log`, () => {
        fetchCount += 1;
        return HttpResponse.json(envelope([makeGlobalChangeLogEntry()]));
      }),
      http.post(`${API_BASE}/knowledge-bases/:kbId/knowledge-points/:kpId/answers`, () =>
        HttpResponse.json(envelope(makeAnswer({ id: 99 }))),
      ),
    );
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
    const wrapper = makeWrapper(queryClient);

    const log = renderHook(() => useGlobalChangeLog(), { wrapper });
    await waitFor(() => expect(fetchCount).toBe(1));

    const mutation = renderHook(() => useCreateAnswer(1, 1), { wrapper });
    mutation.result.current.mutate({ coord: {}, content: 'x', effective_time: '2026-08-09' });

    await waitFor(() => expect(fetchCount).toBe(2));
    log.unmount();
    mutation.unmount();
  });

  it('useEditAnswer invalidates the global change-log', async () => {
    let fetchCount = 0;
    server.use(
      http.get(`${API_BASE}/change-log`, () => {
        fetchCount += 1;
        return HttpResponse.json(envelope([makeGlobalChangeLogEntry()]));
      }),
      http.post(`${API_BASE}/knowledge-bases/:kbId/knowledge-points/:kpId/answers/:answerId/edit`, () =>
        HttpResponse.json(envelope(makeAnswer({ id: 99 }))),
      ),
    );
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
    const wrapper = makeWrapper(queryClient);

    const log = renderHook(() => useGlobalChangeLog(), { wrapper });
    await waitFor(() => expect(fetchCount).toBe(1));

    const mutation = renderHook(() => useEditAnswer(1, 1), { wrapper });
    mutation.result.current.mutate({ answerId: 1, content: 'x', effective_time: '2026-08-09' });

    await waitFor(() => expect(fetchCount).toBe(2));
    log.unmount();
    mutation.unmount();
  });

  it('useCreateKnowledgePoint (with a default answer) invalidates the global change-log', async () => {
    let fetchCount = 0;
    server.use(
      http.get(`${API_BASE}/change-log`, () => {
        fetchCount += 1;
        return HttpResponse.json(envelope([makeGlobalChangeLogEntry()]));
      }),
      http.post(`${API_BASE}/knowledge-bases/:kbId/knowledge-points`, () =>
        HttpResponse.json(envelope(makeKp({ id: 99 }))),
      ),
    );
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
    const wrapper = makeWrapper(queryClient);

    const log = renderHook(() => useGlobalChangeLog(), { wrapper });
    await waitFor(() => expect(fetchCount).toBe(1));

    const mutation = renderHook(() => useCreateKnowledgePoint(1), { wrapper });
    mutation.result.current.mutate({ title: 'new-kp', default_answer: { content: 'x', effective_time: '2026-08-09' } });

    await waitFor(() => expect(fetchCount).toBe(2));
    log.unmount();
    mutation.unmount();
  });

  it('useUpdateKnowledgePointTitle invalidates the global change-log (its rows show this KP\'s title)', async () => {
    let fetchCount = 0;
    server.use(
      http.get(`${API_BASE}/change-log`, () => {
        fetchCount += 1;
        return HttpResponse.json(envelope([makeGlobalChangeLogEntry()]));
      }),
      http.patch(`${API_BASE}/knowledge-bases/:kbId/knowledge-points/:kpId`, () =>
        HttpResponse.json(envelope(makeKp({ title: 'renamed' }))),
      ),
    );
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
    const wrapper = makeWrapper(queryClient);

    const log = renderHook(() => useGlobalChangeLog(), { wrapper });
    await waitFor(() => expect(fetchCount).toBe(1));

    const mutation = renderHook(() => useUpdateKnowledgePointTitle(1, 1), { wrapper });
    mutation.result.current.mutate('renamed');

    await waitFor(() => expect(fetchCount).toBe(2));
    log.unmount();
    mutation.unmount();
  });
});
