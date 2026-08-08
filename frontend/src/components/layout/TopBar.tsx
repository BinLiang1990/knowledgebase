import { useEffect, useState } from 'react';

interface TopBarProps {
  title: string;
  crumb: string;
}

export function TopBar({ title, crumb }: TopBarProps) {
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  return (
    <header className="top">
      <span className="h-bar" />
      <h1>{title}</h1>
      <span className="crumb">{crumb}</span>
      <span className="spacer" />
      <span className="top-badge">已接入真实后端</span>
      <div className="top-clock">
        <div className="t num">{now.toLocaleTimeString('zh-CN', { hour12: false })}</div>
        <div className="d">{now.toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' })}</div>
      </div>
      <div className="top-avatar">AD</div>
    </header>
  );
}
