// UI规范 §3.12: 共 N 条 · 第 x/y 页；文案 → 上一页 → 页码 → 下一页。
// Page-count is small for this project's data volumes (§7 非功能需求 does
// not call for ellipsis-collapsing very large page counts), so unlike the
// spec's ">7 pages" ellipsis rule, all page numbers are rendered directly —
// revisit if a future list genuinely grows past that.
interface PagerProps {
  total: number;
  page: number;
  pageSize: number;
  onChange: (page: number) => void;
}

export function Pager({ total, page, pageSize, onChange }: PagerProps) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  return (
    <div className="pager">
      <span>
        共 <b className="num">{total}</b> 条 · 第 <b className="num">{page}</b>/<b className="num">{pages}</b> 页
      </span>
      <button type="button" disabled={page <= 1} onClick={() => onChange(page - 1)}>
        ‹
      </button>
      {Array.from({ length: pages }, (_, i) => i + 1).map((p) => (
        <button key={p} type="button" className={p === page ? 'cur' : ''} onClick={() => onChange(p)}>
          {p}
        </button>
      ))}
      <button type="button" disabled={page >= pages} onClick={() => onChange(page + 1)}>
        ›
      </button>
    </div>
  );
}
