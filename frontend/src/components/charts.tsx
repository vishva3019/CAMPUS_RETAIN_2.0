import { useId, useMemo, useRef, useState } from "react";

export interface Series { key: string; label: string; color: string }
type Row = Record<string, number | string>;

const W = 640, H = 240, PAD = { l: 40, r: 88, t: 12, b: 28 };

function niceMax(v: number) {
  if (v <= 4) return 4;
  const pow = 10 ** Math.floor(Math.log10(v));
  const step = [1, 2, 2.5, 5, 10].find((s) => (s * pow * 4) >= v)! * pow;
  return step * 4;
}

const fmtMonth = (m: string) => new Date(m + "-01T00:00:00").toLocaleDateString(undefined, { month: "short", year: "2-digit" });

/** Multi-series line chart: 2px lines, crosshair tooltip, legend, end labels, table view. */
export function LineChart({ rows, xKey, series, title }: { rows: Row[]; xKey: string; series: Series[]; title: string }) {
  const [hover, setHover] = useState<number | null>(null);
  const [table, setTable] = useState(false);
  const svgRef = useRef<SVGSVGElement>(null);
  const id = useId();
  const max = useMemo(() => niceMax(Math.max(1, ...rows.flatMap((r) => series.map((s) => Number(r[s.key]) || 0)))), [rows, series]);
  const iw = W - PAD.l - PAD.r, ih = H - PAD.t - PAD.b;
  const x = (i: number) => PAD.l + (rows.length <= 1 ? iw / 2 : (i * iw) / (rows.length - 1));
  const y = (v: number) => PAD.t + ih - (v / max) * ih;
  const ticks = [0, 1, 2, 3, 4].map((i) => (max / 4) * i);
  const labelEvery = Math.max(1, Math.ceil(rows.length / 6));

  function onMove(e: React.PointerEvent<SVGSVGElement>) {
    const box = svgRef.current!.getBoundingClientRect();
    const px = ((e.clientX - box.left) / box.width) * W;
    const i = Math.round(((px - PAD.l) / iw) * (rows.length - 1));
    setHover(Math.min(rows.length - 1, Math.max(0, i)));
  }

  return (
    <figure className="m-0">
      <div className="mb-2 flex flex-wrap items-center gap-x-4 gap-y-1">
        <figcaption className="mr-auto text-sm font-semibold">{title}</figcaption>
        {series.map((s) => (
          <span key={s.key} className="flex items-center gap-1.5 text-xs text-stone-600 dark:text-stone-300">
            <span className="inline-block h-0.5 w-4 rounded" style={{ background: s.color }} aria-hidden />{s.label}
          </span>
        ))}
        <button className="text-xs font-semibold text-brand-600 dark:text-brand-400" onClick={() => setTable(!table)} aria-pressed={table}>
          {table ? "Show chart" : "Show table"}
        </button>
      </div>
      {table ? (
        <div className="max-h-72 overflow-auto rounded-xl border border-stone-200 dark:border-stone-800">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-stone-50 text-left text-xs text-stone-500 dark:bg-stone-900"><tr><th className="px-3 py-2">Month</th>{series.map((s) => <th key={s.key} className="px-3 py-2 text-right">{s.label}</th>)}</tr></thead>
            <tbody>{rows.map((r) => <tr key={String(r[xKey])} className="border-t border-stone-100 dark:border-stone-800"><td className="px-3 py-1.5">{fmtMonth(String(r[xKey]))}</td>{series.map((s) => <td key={s.key} className="px-3 py-1.5 text-right tabular-nums">{r[s.key]}</td>)}</tr>)}</tbody>
          </table>
        </div>
      ) : (
        <div className="relative">
          <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} className="w-full touch-none select-none" role="img" aria-labelledby={id}
            onPointerMove={onMove} onPointerLeave={() => setHover(null)}>
            <title id={id}>{title}. Use “Show table” for the values.</title>
            {ticks.map((t) => (
              <g key={t}>
                <line x1={PAD.l} x2={W - PAD.r} y1={y(t)} y2={y(t)} stroke="var(--chart-grid)" strokeWidth={1} />
                <text x={PAD.l - 8} y={y(t)} dy="0.32em" textAnchor="end" fontSize="11" fill="var(--chart-text)">{Math.round(t).toLocaleString()}</text>
              </g>
            ))}
            {rows.map((r, i) => i % labelEvery === 0 && (
              <text key={i} x={x(i)} y={H - 8} textAnchor="middle" fontSize="11" fill="var(--chart-text)">{fmtMonth(String(r[xKey]))}</text>
            ))}
            {hover !== null && <line x1={x(hover)} x2={x(hover)} y1={PAD.t} y2={PAD.t + ih} stroke="var(--chart-text)" strokeWidth={1} opacity={0.4} />}
            {series.map((s) => {
              const pts = rows.map((r, i) => `${x(i)},${y(Number(r[s.key]) || 0)}`).join(" ");
              const last = rows.length - 1;
              return (
                <g key={s.key}>
                  <polyline points={pts} fill="none" stroke={s.color} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
                  {last >= 0 && <circle cx={x(last)} cy={y(Number(rows[last][s.key]) || 0)} r={4} fill={s.color} stroke="var(--chart-surface)" strokeWidth={2} />}
                  {hover !== null && <circle cx={x(hover)} cy={y(Number(rows[hover][s.key]) || 0)} r={4.5} fill={s.color} stroke="var(--chart-surface)" strokeWidth={2} />}
                </g>
              );
            })}
            {/* direct end labels, nudged apart only when they would overlap */}
            {(() => {
              const last = rows.length - 1;
              if (last < 0) return null;
              const placed = series.map((s) => ({ s, v: Number(rows[last][s.key]) || 0, yy: y(Number(rows[last][s.key]) || 0) }))
                .sort((a, b) => a.yy - b.yy);
              for (let i = 1; i < placed.length; i++) if (placed[i].yy - placed[i - 1].yy < 13) placed[i].yy = placed[i - 1].yy + 13;
              return placed.map(({ s, v, yy }) => (
                <text key={s.key} x={x(last) + 10} y={yy} dy="0.32em" fontSize="11" fill="var(--chart-text)">{s.label} {v}</text>
              ));
            })()}
          </svg>
          {hover !== null && (
            <div className="pointer-events-none absolute top-0 z-10 rounded-lg border border-stone-200 bg-white px-3 py-2 text-xs shadow-lg dark:border-stone-700 dark:bg-stone-900"
              style={{ left: `${(x(hover) / W) * 100}%`, transform: hover > rows.length / 2 ? "translateX(calc(-100% - 8px))" : "translateX(8px)" }}>
              <div className="mb-1 font-semibold text-stone-500">{fmtMonth(String(rows[hover][xKey]))}</div>
              {series.map((s) => (
                <div key={s.key} className="flex items-center gap-2">
                  <span className="inline-block h-0.5 w-3 rounded" style={{ background: s.color }} aria-hidden />
                  <strong className="tabular-nums text-stone-900 dark:text-white">{rows[hover][s.key]}</strong>
                  <span className="text-stone-500">{s.label}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </figure>
  );
}

/** Horizontal bars for one measure, with a secondary note per row (e.g. "2 recovered"). */
export function BarList({ title, rows }: { title: string; rows: { label: string; value: number; note?: string }[] }) {
  const max = Math.max(1, ...rows.map((r) => r.value));
  return (
    <figure className="m-0">
      <figcaption className="mb-3 text-sm font-semibold">{title}</figcaption>
      {rows.length === 0 ? <p className="text-sm text-stone-500">No items in this period.</p> : (
        <ul className="space-y-2.5">
          {rows.map((r) => (
            <li key={r.label} className="group" title={`${r.label}: ${r.value}${r.note ? ` (${r.note})` : ""}`}>
              <div className="flex items-baseline justify-between gap-3 text-xs">
                <span className="truncate text-stone-700 dark:text-stone-300">{r.label}</span>
                <span className="shrink-0 tabular-nums text-stone-500"><strong className="text-stone-900 dark:text-white">{r.value}</strong>{r.note ? ` · ${r.note}` : ""}</span>
              </div>
              <div className="mt-1 h-2.5">
                <div className="h-full rounded-r-[4px] transition-all group-hover:opacity-80" style={{ width: `${Math.max(2, (r.value / max) * 100)}%`, background: "var(--series-1)" }} />
              </div>
            </li>
          ))}
        </ul>
      )}
    </figure>
  );
}
