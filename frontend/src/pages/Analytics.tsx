import { useMemo } from "react";
import { useSearchParams } from "react-router";
import { BarChart3, Download, FileText } from "lucide-react";
import { qs } from "../lib/api";
import { useFetch } from "../lib/useFetch";
import { useSession } from "../lib/session";
import { BarList, LineChart } from "../components/charts";
import { Card, ErrorNote, Input, Skeleton } from "../components/ui";

interface Analytics {
  period: { from: string; to: string };
  totals: { found_reported: number; lost_reported: number; recovered: number; recovery_rate: number | null; returned: number;
    lost_closed_found: number; claims_submitted: number; avg_days_to_return: number | null; median_days_to_return: number | null };
  claim_outcomes: Record<string, number>;
  backlog: { pending_claims: number; oldest_pending_days: number | null; awaiting_pickup: number; oldest_pickup_days: number | null; unclaimed_over_30_days: number };
  monthly: { month: string; found: number; lost: number; returned: number }[];
  by_category: { category: string; found: number; recovered: number }[];
  by_campus: { campus: string; found: number; recovered: number }[];
  by_collection_point: { collection_point: string; found: number }[];
}

// Local calendar date (toISOString would shift it to UTC and show the previous day east of UTC).
const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
function presets() {
  const today = new Date();
  const ago = (days: number) => iso(new Date(today.getTime() - days * 86400000));
  return [
    { label: "30 days", from: ago(29) },
    { label: "90 days", from: ago(89) },
    { label: "12 months", from: iso(new Date(today.getFullYear() - 1, today.getMonth(), 1)) },
    { label: "This year", from: `${today.getFullYear()}-01-01` },
  ].map((p) => ({ ...p, to: iso(today) }));
}

const OUTCOME_LABELS: Record<string, string> = {
  pending: "Waiting for review", approved: "Approved, not yet collected", collected: "Collected",
  rejected: "Rejected", withdrawn: "Withdrawn", closed: "Imported from 2.0",
};

function Stat({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <Card className="p-4">
      <div className="text-xs font-medium text-stone-500">{label}</div>
      <div className="mt-1 text-2xl font-bold tabular-nums">{value}</div>
      {note && <div className="mt-0.5 text-xs text-stone-500">{note}</div>}
    </Card>
  );
}

export function AnalyticsPage() {
  const { session, has } = useSession();
  const [params, setParams] = useSearchParams();
  const ranges = useMemo(presets, []);
  const from = params.get("from") ?? ranges[2].from;
  const to = params.get("to") ?? ranges[2].to;
  const query = qs({ from, to });
  const { data, error, loading, reload } = useFetch<Analytics>(`/api/v1/admin/analytics${query}`);
  const series = useMemo(() => [
    { key: "found", label: "Found", color: "var(--series-1)" },
    { key: "lost", label: "Lost", color: "var(--series-2)" },
    { key: "returned", label: "Returned", color: "var(--series-3)" },
  ], []);
  const t = data?.totals;
  const pct = (v: number | null | undefined) => (v === null || v === undefined ? "–" : `${(v * 100).toFixed(0)}%`);
  const days = (v: number | null | undefined) => (v === null || v === undefined ? "–" : `${v} days`);

  return (
    <div>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold"><BarChart3 className="size-6 text-brand-600" aria-hidden />Analytics</h1>
          <p className="text-sm text-stone-500">{session.college?.name}{session.user.campus ? ` · ${session.user.campus} campus` : ""}</p>
        </div>
        <div className={`flex gap-2 ${has("exports") ? "" : "hidden"}`}>
          <a href={`/api/v1/admin/analytics.xlsx${query}`} className="inline-flex items-center gap-2 rounded-xl border border-stone-200 bg-white px-3.5 py-2 text-sm font-semibold hover:bg-stone-50 dark:border-stone-700 dark:bg-stone-900"><Download className="size-4" aria-hidden />Excel</a>
          <a href={`/api/v1/admin/analytics.pdf${query}`} className="inline-flex items-center gap-2 rounded-xl border border-stone-200 bg-white px-3.5 py-2 text-sm font-semibold hover:bg-stone-50 dark:border-stone-700 dark:bg-stone-900"><FileText className="size-4" aria-hidden />PDF report</a>
        </div>
      </div>

      {/* Filters: one row, date range first, scope everything below */}
      <div className="mt-5 flex flex-wrap items-center gap-2">
        {ranges.map((r) => (
          <button key={r.label} onClick={() => setParams({ from: r.from, to: r.to })} aria-pressed={from === r.from && to === r.to}
            className={`rounded-full px-3.5 py-1.5 text-sm font-semibold ${from === r.from && to === r.to ? "bg-stone-900 text-white dark:bg-white dark:text-stone-900" : "bg-white text-stone-600 ring-1 ring-stone-200 hover:bg-stone-50 dark:bg-stone-900 dark:text-stone-300 dark:ring-stone-700"}`}>
            {r.label}
          </button>
        ))}
        <label className="ml-1 flex items-center gap-1.5 text-xs text-stone-500">From <Input type="date" value={from} max={to} onChange={(e) => e.target.value && setParams({ from: e.target.value, to })} className="!w-auto !py-1.5" /></label>
        <label className="flex items-center gap-1.5 text-xs text-stone-500">to <Input type="date" value={to} min={from} onChange={(e) => e.target.value && setParams({ from, to: e.target.value })} className="!w-auto !py-1.5" /></label>
      </div>

      {error ? <div className="mt-5"><ErrorNote message={error} onRetry={reload} /></div> : !data ? (
        <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">{Array.from({ length: 4 }, (_, i) => <Skeleton key={i} className="h-24" />)}</div>
      ) : (
        <div className={`mt-5 space-y-5 transition-opacity ${loading ? "opacity-60" : ""}`}>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Stat label="Found items reported" value={String(t!.found_reported)} note={`${t!.lost_reported} lost reports`} />
            <Stat label="Recovery rate" value={pct(t!.recovery_rate)} note={t!.found_reported ? `${t!.recovered} of ${t!.found_reported} matched to an owner` : "No found items in this period"} />
            <Stat label="Pickups confirmed" value={String(t!.returned)} note={`${t!.claims_submitted} claims submitted`} />
            <Stat label="Median time to pickup" value={days(t!.median_days_to_return)} note={t!.avg_days_to_return !== null ? `average ${t!.avg_days_to_return} days` : "No pickups yet"} />
          </div>

          <Card className="p-4 sm:p-5">
            <LineChart title="Items per month" rows={data.monthly} xKey="month" series={series} />
          </Card>

          <div className="grid gap-5 lg:grid-cols-2">
            <Card className="p-4 sm:p-5">
              <BarList title="Found items by category" rows={data.by_category.map((c) => ({ label: c.category, value: c.found, note: `${c.recovered} recovered` }))} />
            </Card>
            <Card className="p-4 sm:p-5">
              {data.by_campus.length > 1
                ? <BarList title="Found items by campus" rows={data.by_campus.map((c) => ({ label: c.campus, value: c.found, note: `${c.recovered} recovered` }))} />
                : <BarList title="Where found items were handed in" rows={data.by_collection_point.map((c) => ({ label: c.collection_point, value: c.found }))} />}
            </Card>
          </div>

          <div className="grid gap-5 lg:grid-cols-2">
            <Card className="p-4 sm:p-5">
              <h2 className="text-sm font-semibold">Claims in this period</h2>
              <dl className="mt-3 divide-y divide-stone-100 text-sm dark:divide-stone-800">
                {Object.entries(data.claim_outcomes).filter(([k, v]) => v > 0 || k !== "closed").map(([k, v]) => (
                  <div key={k} className="flex justify-between py-2"><dt className="text-stone-600 dark:text-stone-400">{OUTCOME_LABELS[k] ?? k}</dt><dd className="font-semibold tabular-nums">{v}</dd></div>
                ))}
              </dl>
            </Card>
            <Card className="p-4 sm:p-5">
              <h2 className="text-sm font-semibold">Needs attention now</h2>
              <dl className="mt-3 divide-y divide-stone-100 text-sm dark:divide-stone-800">
                <div className="flex justify-between py-2"><dt className="text-stone-600 dark:text-stone-400">Claims waiting for review</dt><dd className="font-semibold tabular-nums">{data.backlog.pending_claims}{data.backlog.oldest_pending_days !== null && <span className="ml-1 font-normal text-stone-500">(oldest {data.backlog.oldest_pending_days} d)</span>}</dd></div>
                <div className="flex justify-between py-2"><dt className="text-stone-600 dark:text-stone-400">Approved, not yet collected</dt><dd className="font-semibold tabular-nums">{data.backlog.awaiting_pickup}{data.backlog.oldest_pickup_days !== null && <span className="ml-1 font-normal text-stone-500">(oldest {data.backlog.oldest_pickup_days} d)</span>}</dd></div>
                <div className="flex justify-between py-2"><dt className="text-stone-600 dark:text-stone-400">Found items unclaimed 30+ days</dt><dd className="font-semibold tabular-nums">{data.backlog.unclaimed_over_30_days}</dd></div>
              </dl>
            </Card>
          </div>
          <p className="text-xs text-stone-500">Recovery rate: found items reported in the period that now have an approved or collected claim, divided by found items reported. Time to pickup runs from the report to the pickup confirmed at the desk. Removed listings are left out.</p>
        </div>
      )}
    </div>
  );
}
