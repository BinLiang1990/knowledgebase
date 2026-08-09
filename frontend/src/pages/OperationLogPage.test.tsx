import { describe, expect, it } from 'vitest';
import { screen } from '@testing-library/react';
import { OperationLogPage } from './OperationLogPage';
import { renderWithProviders } from '../test/renderWithProviders';
import { API_BASE, HttpResponse, envelope, errorEnvelope, http, makeGlobalChangeLogEntry, server } from '../test/server';

describe('OperationLogPage', () => {
  it('renders global entries with their knowledge base/point columns', async () => {
    server.use(
      http.get(`${API_BASE}/change-log`, () =>
        HttpResponse.json(envelope([makeGlobalChangeLogEntry({ knowledge_base_name: 'kb-x', knowledge_point_title: 'kp-x' })])),
      ),
    );
    renderWithProviders(<OperationLogPage />);
    expect(await screen.findByText('kb-x')).toBeInTheDocument();
    expect(screen.getByText('kp-x')).toBeInTheDocument();
  });

  it('renders a failure state with a retry link on error', async () => {
    server.use(http.get(`${API_BASE}/change-log`, () => HttpResponse.json(errorEnvelope('数据库异常'), { status: 500 })));
    renderWithProviders(<OperationLogPage />);
    expect(await screen.findByText(/加载失败/)).toBeInTheDocument();
  });

  it('renders an empty state when there is no history', async () => {
    server.use(http.get(`${API_BASE}/change-log`, () => HttpResponse.json(envelope([]))));
    renderWithProviders(<OperationLogPage />);
    expect(await screen.findByText('暂无变更记录')).toBeInTheDocument();
  });
});
