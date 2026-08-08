import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from 'react';

type ToastType = 'ok' | 'err' | 'info';

interface ToastItem {
  id: number;
  type: ToastType;
  message: string;
}

interface ToastApi {
  ok: (message: string) => void;
  err: (message: string) => void;
  info: (message: string) => void;
}

const ToastContext = createContext<ToastApi | null>(null);

// UI规范 §3.13: 深色胶囊、底部居中、2.6s 自动消失、可堆叠。
const AUTO_DISMISS_MS = 2600;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const nextId = useRef(0);

  const push = useCallback((type: ToastType, message: string) => {
    const id = nextId.current++;
    setItems((prev) => [...prev, { id, type, message }]);
    setTimeout(() => setItems((prev) => prev.filter((item) => item.id !== id)), AUTO_DISMISS_MS);
  }, []);

  const api: ToastApi = {
    ok: (message) => push('ok', message),
    err: (message) => push('err', message),
    info: (message) => push('info', message),
  };

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div id="toast">
        {items.map((item) => (
          <div key={item.id} className={`toast-item ${item.type}`}>
            {item.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastApi {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error('useToast must be used within a ToastProvider');
  return ctx;
}
