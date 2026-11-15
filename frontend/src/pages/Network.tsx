import { useState, type FormEvent } from "react";
import { useSearchParams } from "react-router";
import { Building2, Globe2, Search } from "lucide-react";
import { qs } from "../lib/api";
import { dateLabel } from "../lib/format";
import { useFetch } from "../lib/useFetch";
import { useSession } from "../lib/session";
import type { NetworkItem, Page } from "../lib/types";
import { ClaimModal } from "../components/ClaimModal";
import { Button, Card, Empty, ErrorNote, Pagination, Skeleton, inputCls } from "../components/ui";

export function Network() {
  const { session } = useSession();
  const [params, setParams] = useSearchParams();
  const q = params.get("q") ?? "";
  const page = Number(params.get("page") ?? 1) || 1;
  const { data, error, loading, reload } = useFetch<Page<NetworkItem> & { enabled: boolean; colleges: { name: string; city: string | null }[] }>(`/api/v1/network/items${qs({ q, page })}`);
  const [claiming, setClaiming] = useState<NetworkItem | null>(null);
  const search = (e: FormEvent<HTMLFormElement>) => { e.preventDefault(); const v = String(new FormData(e.currentTarget).get("q") ?? "").trim(); setParams(v ? { q: v } : {}); };

  return (
    <div className="mx-auto max-w-4xl">
      <h1 className="flex items-center gap-2 text-2xl font-bold"><Globe2 className="size-6 text-brand-600" aria-hidden />Other colleges</h1>
      {data && !data.enabled ? (
        <div className="mt-5"><Empty icon={<Building2 className="size-6" aria-hidden />} title={`${session.college?.display_name} hasn't joined the inter-college network`}>A college admin can switch it on in Settings.</Empty></div>
      ) : (
        <>
          <p className="mt-1 text-sm text-stone-500">Lost something at another campus? Search found items at colleges in the network. Listings show only the item, date and college; staff there check your claim and hand it over.</p>
          {data?.colleges.length ? <p className="mt-2 text-xs text-stone-500">In the network: {data.colleges.map((c) => c.name + (c.city ? ` (${c.city})` : "")).join(", ")}</p> : null}
          <form role="search" onSubmit={search} className="relative mt-4">
            <Search className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-stone-400" aria-hidden />
            <input key={q} name="q" defaultValue={q} type="search" placeholder="Search other colleges' found items" aria-label="Search" className={`${inputCls} pl-10`} />
          </form>
          <div className="mt-5 space-y-3">
            {error ? <ErrorNote message={error} onRetry={reload} /> : loading && !data ? <Skeleton className="h-24" /> :
              !data?.items.length ? <Empty icon={<Search className="size-6" aria-hidden />} title={q ? `Nothing matches “${q}”` : "No open found items at other colleges"} /> :
              data.items.map((i) => (
                <Card key={i.id} className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:p-5">
                  <div className="min-w-0 flex-1">
                    <h3 className="font-semibold">{i.name}</h3>
                    <p className="text-xs text-stone-500">{i.category} · {i.college}{i.city ? `, ${i.city}` : ""} · {i.occurred_on ? `found ${dateLabel(i.occurred_on)}` : `reported ${dateLabel(i.reported_at)}`}</p>
                  </div>
                  <Button onClick={() => setClaiming(i)}>This is mine</Button>
                </Card>
              ))}
            {data && <Pagination page={data.page} pages={data.pages} total={data.total} onPage={(p) => setParams({ ...(q ? { q } : {}), page: String(p) })} />}
          </div>
        </>
      )}
      <ClaimModal item={claiming} onClose={() => setClaiming(null)} onDone={reload} endpoint="/api/v1/network/claims"
        note={claiming ? `Staff at ${claiming.college} will review this and email you. If approved, you collect it there with a pickup code.` : undefined} />
    </div>
  );
}
