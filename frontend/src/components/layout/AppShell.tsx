import type { ReactNode } from 'react';
import { Sidebar } from './Sidebar';
import { TopBar } from './TopBar';

interface AppShellProps {
  title: string;
  crumb: string;
  children: ReactNode;
}

// UI规范 §2.1: 侧栏228px + 顶栏64px + 自适应内容区.
export function AppShell({ title, crumb, children }: AppShellProps) {
  return (
    <div className="app">
      <Sidebar />
      <div className="main">
        <TopBar title={title} crumb={crumb} />
        <main className="content">{children}</main>
      </div>
    </div>
  );
}
