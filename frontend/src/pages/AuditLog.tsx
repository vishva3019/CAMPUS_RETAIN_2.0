import { useSearchParams } from "react-router";
import { History } from "lucide-react";
import { qs } from "../lib/api";
import { dateTimeLabel } from "../lib/format";
import { useFetch } from "../lib/useFetch";
import type { Page } from "../lib/types";
import { Card, Empty, ErrorNote, Pagination, Select, Skeleton, inputCls } from "../components/ui";

interface Entry { id: number; action: string; actor: string | null; target_type: string | null; target_id: number | null; details: Record<string, unknown>; ip_address: string | null; created_at: string; college_id?: number }

const ACTION_LABELS: Record<string, string> = {
  "item.reported": "Reported an item", "item.removed": "Removed a listing", "claim.submitted": "Submitted a claim",
  "claim.approved": "Approved a claim", "claim.rejected": "Rejected a claim", "claim.withdrawn": "Withdrew a claim",
  "pickup.collected": "Handed an item over", "pickup.code_failed": "Wrong pickup code entered", "pickup.code_resent": "Sent a new pickup code",
  "items.exported": "Exported items (CSV)", "analytics.exported": "Exported analytics", "auth.login": "Signed in",
  "auth.login_failed": "Failed sign-in", "collection_point.created": "Added a collection point",
  "collection_point.updated": "Changed a collection point", "lost.closed": "Closed a lost report",
};

function details(d: Record<string, unknown>) {
  return Object.entries(d).filter(([, v]) => v !== null && v !== undefined && typeof v !== "object")
    .map(([k, v]) => `${k.replace(/_/g, " ")}: ${v}`).join(" · ");
}

export function AuditLog({ platform = false }: { platform?: boolean }) {
  const [params, setParams] = useSearchParams();
  const action = params.get("action") ?? "";
  const actor = params.get("actor") ?? "";
  const page = Number(params.get("page") ?? 1) || 1;
  const { data, error, loading, reload } = useFetch<Page<Entry> & { actions?: string[] }>(
    `/api/v1/${platform ? "platform" : "admin"}/audit${qs({ action, actor, page })}`);
  const set = (next: Record<string, string>) => {
    const p = new URLSearchParams(params);
    for (const [k, v] of Object.entries(next)) (v ? p.set(k, v) : p.delete(k));
    if (!("page" in next)) p.delete("page");
    setParams(p);
  };
  return (
    <div className="mx-auto max-w-5xl">
      <h1 className="flex items-center gap-2 text-2xl font-bold"><History className="size-6 text-brand-600" aria-hidden />Activity log</h1>
      <p className="mt-1 text-sm text-stone-500">Every sign-in, report, claim decision, handover and export{platform ? " across all colleges" : ""}. Entries can't be edited or deleted.</p>
      <div className="mt-5 flex flex-col gap-2 sm:flex-row">
        {data?.actions ? (
          <Select aria-label="Action" value={action} onChange={(e) => set({ action: e.target.value })} className="sm:!w-64">
            <option value="">All actions</option>
            {data.actions.map((a) => <option key={a} value={a}>{ACTION_LABELS[a] ?? a}</option>)}
          </Select>
        ) : (
          <input defaultValue={action} placeholder="Action starts with… (e.g. claim.)" aria-label="Action" className={`${inputCls} sm:!w-64`}
            onKeyDown={(e) => e.key === "Enter" && set({ action: (e.target as HTMLInputElement).value.trim() })} />
        )}
        <form className="flex-1" onSubmit={(e) => { e.preventDefault(); set({ actor: String(new FormData(e.currentTarget).get("actor") ?? "").trim() }); }}>
          <input key={actor} name="actor" type="email" defaultValue={actor} placeholder="Filter by person (exact email)" aria-label="Person" className={inputCls} />
        </form>
      </div>
      <div className="mt-5">
        {error ? <ErrorNote message={error} onRetry={reload} /> : loading && !data ? <Skeleton className="h-64" /> :
          !data?.items.length ? <Empty icon={<History className="size-6" aria-hidden />} title="No activity matches" /> : (
            <Card className="divide-y divide-stone-100 dark:divide-stone-800">
              {data.items.map((e) => (
                <div key={e.id} className="flex flex-col gap-1 px-4 py-3 text-sm sm:flex-row sm:items-start sm:gap-4 sm:px-5">
                  <span className="w-36 shrink-0 text-xs text-stone-500 tabular-nums">{dateTimeLabel(e.created_at)}</span>
                  <div className="min-w-0 flex-1">
                    <div><strong>{e.actor ?? "System"}</strong> <span className="text-stone-600 dark:text-stone-400">{ACTION_LABELS[e.action] ?? e.action}</span>
                      {e.target_type && <span className="text-stone-400"> · {e.target_type} #{e.target_id}</span>}
                      {platform && e.college_id && <span className="text-stone-400"> · college #{e.college_id}</span>}</div>
                    {details(e.details) && <div className="mt-0.5 break-words text-xs text-stone-500">{details(e.details)}</div>}
                  </div>
                  {e.ip_address && <span className="shrink-0 font-mono text-[11px] text-stone-400">{e.ip_address}</span>}
                </div>
              ))}
            </Card>
          )}
        {data && <Pagination page={data.page} pages={data.pages} total={data.total} onPage={(p) => set({ page: String(p) })} />}
      </div>
    </div>
  );
}
