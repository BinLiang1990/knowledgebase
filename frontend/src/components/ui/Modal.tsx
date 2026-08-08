import type { ReactNode } from 'react';

interface ModalProps {
  open: boolean;
  title: string;
  onClose: () => void;
  wide?: boolean;
  children: ReactNode;
  footer: ReactNode;
}

// UI规范 §3.10: 顶部对齐（不垂直居中）、点遮罩关闭、.mo-body 独立滚动。
export function Modal({ open, title, onClose, wide, children, footer }: ModalProps) {
  if (!open) return null;
  return (
    <div
      className="mask show"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className={`modal${wide ? ' wide' : ''}`}>
        <div className="mo-head">
          <h3>{title}</h3>
          <button type="button" className="mo-close" onClick={onClose} aria-label="关闭">
            ✕
          </button>
        </div>
        <div className="mo-body">{children}</div>
        <div className="mo-foot">{footer}</div>
      </div>
    </div>
  );
}
