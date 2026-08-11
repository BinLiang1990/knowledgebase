import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter } from 'react-router-dom';
import { App } from './App.tsx';
import { ToastProvider } from './components/ui/Toast.tsx';
import { createQueryClient } from './queryClient.ts';
import './styles/tokens.css';
import './styles/components.css';

const queryClient = createQueryClient();

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        {/* import.meta.env.BASE_URL 跟 vite.config.ts 里的 `base` 保持一致——
            生产构建是 "/kb-web/"，路由 basename 必须匹配，否则线上二级路径
            (如 /kb-web/knowledge-bases/1) 刷新或直接访问会被 react-router
            当成未知路由。 */}
        <BrowserRouter basename={import.meta.env.BASE_URL}>
          <App />
        </BrowserRouter>
      </ToastProvider>
    </QueryClientProvider>
  </StrictMode>,
);
