import { useEffect, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router";
import { motion } from "motion/react";
import { AlertTriangle, CheckCircle2, Clock, Sparkles, Download, ImageOff, PackageCheck, PackageSearch, Search, ShieldAlert, Trash2 } from "lucide-react";
import { api, qs } from "../lib/api";
import { dateLabel, dateTimeLabel } from "../lib/format";
import { useFetch } from "../lib/useFetch";
import { useSession } from "../lib/session";
import type { CollectionPoint, Item, Kind, Match, Page, ReviewClaim } from "../lib/types";
import { Modal } from "../components/Modal";
import { useToast } from "../components/Toast";
import { Badge, Button, Card, CLAIM_LABELS, Empty, ErrorNote, Field, ITEM_LABELS, LOST_LABELS, Pagination, Select, Skeleton, Textarea, inputCls } from "../components/ui";

type Counts = { Available: number; Pending: number; Claimed: number; lost: number };
const STATUS_OPTIONS = [["", "All active"], ["available", "Available"], ["pending", "Claim under review"], ["claimed", "Awaiting pickup"], ["returned", "Returned"], ["removed", "Removed"]];

type Review = { item: Item; action: "approve" | "reject" | "remove" } | null;

const VERDICT: Record<string, string> = { likely: "AI: likely the same item", unlikely: "AI: probably not the same item", unsure: "AI: can't tell" };

function MatchesPanel({ item }: { item: Item }) {
  const { session, can } = useSession();
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [checking, setChecking] = useState<number | null>(null);
  const { data, error, loading, setData } = useFetch<{ items: Match[] }>(open ? `/api/v1/admin/items/${item.id}/matches` : null);
  if (!can("claims.review") || item.status === "Removed") return null;
  async function aiCheck(m: Match) {
    setChecking(m.id);
    try {
      const r = await api.post<{ match: Match }>(`/api/v1/matches/${m.id}/ai-check`);
      setData((d) => d && { items: d.items.map((x) => (x.id === m.id ? { ...x, ...r.match, item: x.item } : x)) });
    } catch (err) {
      toast((err as Error).message, "error");
    } finally {
      setChecking(null);
    }
  }
  return (
    <div className="mt-3">
      <button className="text-sm font-semibold text-brand-600 dark:text-brand-400" onClick={() => setOpen(!open)} aria-expanded={open}>
        {open ? "Hide possible matches" : item.kind === "found" ? "Possible matching lost reports" : "Possible matching found items"}
      </button>
      {open && (
        <div className="mt-2 space-y-2">
          {error ? <ErrorNote message={error} /> : loading ? <Skeleton className="h-12" /> : !data?.items.length ? (
            <p className="text-sm text-stone-500">No similar {item.kind === "found" ? "lost reports" : "found items"} yet.</p>
          ) : data.items.map((m) => (
            <div key={m.id} className="rounded-xl border border-stone-200 p-3 text-sm dark:border-stone-800">
              <div className="flex flex-wrap items-center gap-2">
                <strong>{m.item.name}</strong>
                <span className="text-stone-500">· {m.item.location} · {dateLabel(m.item.reported_at)}</span>
                <span className="rounded-full bg-stone-100 px-2 py-0.5 text-xs dark:bg-stone-800">{Math.round(m.score * 100)}% text match</span>
                {m.status !== "suggested" && <Badge status={m.status === "confirmed" ? "approved" : "Returned"} label={m.status} />}
                {session.config.ai_enabled && (
                  <Button variant="ghost" className="ml-auto !py-1.5" busy={checking === m.id} onClick={() => aiCheck(m)}>
                    <Sparkles className="size-4" aria-hidden />{m.ai_verdict ? "Ask AI again" : "Ask AI"}
                  </Button>
                )}
              </div>
              {m.item.description && <p className="mt-1 text-stone-600 dark:text-stone-400">{m.item.description}</p>}
              {m.ai_verdict && <p className="mt-2 rounded-lg bg-brand-50 px-3 py-2 text-xs text-brand-900 dark:bg-brand-500/10 dark:text-brand-200"><strong>{VERDICT[m.ai_verdict] ?? m.ai_verdict}.</strong> {m.ai_reason} <span className="opacity-70">Only a suggestion: you decide.</span></p>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

const HISTORY_LABELS: Record<string, string> = { approved: "approved", collected: "collected", rejected: "rejected", withdrawn: "withdrawn", pending: "pending", closed: "closed" };

/** The pending-claims workflow: the item (with its private detail) beside the claimant's
 * proof, warnings and history, so staff can decide without hunting around. */
function ClaimsQueue({ onDecide, refreshKey }: { onDecide: (item: Item, action: "approve" | "reject") => void; refreshKey: number }) {
  const [page, setPage] = useState(1);
  const { data, error, loading, reload } = useFetch<Page<ReviewClaim>>(`/api/v1/admin/claims${qs({ page, per_page: 5 })}`);
  useEffect(() => { if (refreshKey) reload(); }, [refreshKey, reload]);
  return (
    <section id="claims-queue" className="mt-6 scroll-mt-24">
      <h2 className="flex items-center gap-2 text-xl">Claims to review {data && <span className="rounded-full bg-amber-100 px-2 py-0.5 font-sans text-sm font-semibold text-amber-800 dark:bg-amber-500/15 dark:text-amber-300">{data.total}</span>}</h2>
      <p className="mt-1 text-sm text-stone-500">Oldest first. Compare the claimant's proof with the private detail only staff can see.</p>
      <div className="mt-3 space-y-3">
        {error ? <ErrorNote message={error} onRetry={reload} /> : loading && !data ? <Skeleton className="h-48" /> :
          !data?.items.length ? (
            <div className="flex items-center gap-3 rounded-2xl border border-stone-200 bg-white px-4 py-4 text-sm text-stone-600 dark:border-stone-800 dark:bg-stone-900 dark:text-stone-300">
              <CheckCircle2 className="size-5 text-brand-600" aria-hidden />No claims waiting. You're all caught up.
            </div>
          ) : data.items.map((c) => {
            const item = c.item;
            const others = (item.claims ?? []).filter((x) => x.id !== c.id);
            const hist = Object.entries(c.claimant_history).filter(([, n]) => n);
            return (
              <Card key={c.id} className="overflow-hidden">
                <div className="grid md:grid-cols-2">
                  <div className="border-b border-stone-100 p-4 sm:p-5 md:border-b-0 md:border-r dark:border-stone-800">
                    <p className="text-xs font-semibold uppercase tracking-wider text-stone-500">The item</p>
                    <div className="mt-2 flex gap-3">
                      {item.photos[0] ? <img src={item.photos[0]} alt="" className="size-20 shrink-0 rounded-xl object-cover" />
                        : <div className="grid size-20 shrink-0 place-items-center rounded-xl bg-stone-100 text-stone-400 dark:bg-stone-800"><ImageOff className="size-6" aria-label="No photo" /></div>}
                      <div className="min-w-0 text-sm">
                        <p className="font-semibold">{item.name}</p>
                        <p className="text-xs text-stone-500">{item.ref} · {item.category} · {item.location} · found {dateLabel(item.occurred_on ?? item.reported_at)}</p>
                        {item.collection_point && <p className="text-xs text-stone-500">Held at {item.collection_point.name}</p>}
                      </div>
                    </div>
                    {item.description && <p className="mt-2 text-sm text-stone-600 dark:text-stone-400">Public: {item.description}</p>}
                    <p className="mt-2 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-950 dark:bg-amber-500/10 dark:text-amber-100">
                      <strong>Private detail:</strong> {item.secret_detail || <span className="italic text-amber-800/70 dark:text-amber-200/70">none recorded by the finder</span>}
                    </p>
                  </div>
                  <div className="p-4 sm:p-5">
                    <p className="text-xs font-semibold uppercase tracking-wider text-stone-500">The claim</p>
                    <p className="mt-2 text-sm"><strong>{c.student_email}</strong>{c.student_id ? ` · ID ${c.student_id}` : ""}{c.phone ? ` · ${c.phone}` : ""}</p>
                    {c.claimant_college && <p className="text-xs text-sky-700 dark:text-sky-300">Student at {c.claimant_college} (college network)</p>}
                    <p className="text-xs text-stone-500">Submitted {dateTimeLabel(c.timestamp)}</p>
                    <blockquote className="mt-2 rounded-lg border-l-4 border-brand-600 bg-stone-50 px-3 py-2 text-sm text-stone-800 dark:bg-stone-800 dark:text-stone-200">{c.proof_description}</blockquote>
                    {!!c.flags?.length && (
                      <ul className="mt-2 space-y-1">{c.flags.map((f) => <li key={f.code} className="flex items-start gap-1.5 text-xs text-amber-800 dark:text-amber-300"><AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden />{f.message}</li>)}</ul>
                    )}
                    <p className="mt-2 text-xs text-stone-500">
                      Claimant's other claims: {hist.length ? hist.map(([k, n]) => `${n} ${HISTORY_LABELS[k] ?? k}`).join(", ") : "none"}
                      {others.length > 0 && ` · ${others.length} earlier claim${others.length === 1 ? "" : "s"} on this item (${others.map((o) => CLAIM_LABELS[o.status].toLowerCase()).join(", ")})`}
                    </p>
                  </div>
                </div>
                <div className="flex gap-2 border-t border-stone-100 bg-stone-50/60 px-4 py-3 sm:px-5 dark:border-stone-800 dark:bg-stone-900/60">
                  <Button onClick={() => onDecide(item, "approve")}><CheckCircle2 className="size-4" aria-hidden />Approve</Button>
                  <Button variant="secondary" onClick={() => onDecide(item, "reject")}>Reject with reason</Button>
                </div>
              </Card>
            );
          })}
        {data && <Pagination page={data.page} pages={data.pages} total={data.total} onPage={setPage} />}
      </div>
    </section>
  );
}

export function Admin() {
  const { session, can, has } = useSession();
  const toast = useToast();
  const [params, setParams] = useSearchParams();
  const plan = session.college?.plan;
  const kind: Kind = params.get("kind") === "lost" ? "lost" : "found";
  const status = params.get("status") ?? "";
  const q = params.get("q") ?? "";
  const category = params.get("category") ?? "";
  const campus = params.get("campus") ?? "";
  const page = Number(params.get("page") ?? 1) || 1;
  const filters = { kind, status, q, category, campus };
  const campuses = session.college?.campuses ?? [];
  const [queueKey, setQueueKey] = useState(0);
  const { data, error, loading, reload } = useFetch<Page<Item> & { counts: Counts }>(`/api/v1/admin/items${qs({ ...filters, page })}`);
  const [points, setPoints] = useState<CollectionPoint[]>([]);
  const [review, setReview] = useState<Review>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (can("items.manage")) api.get<{ items: CollectionPoint[] }>("/api/v1/collection-points").then((d) => setPoints(d.items)).catch(() => {});
  }, [can]);

  function update(next: Record<string, string | null>) {
    const p = new URLSearchParams(params);
    for (const [k, v] of Object.entries(next)) (v ? p.set(k, v) : p.delete(k));
    if (!("page" in next)) p.delete("page");
    setParams(p);
  }

  async function act(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!review) return;
    const remarks = String(new FormData(e.currentTarget).get("remarks") ?? "").trim();
    const url = review.action === "remove" ? `/api/item/delete/${review.item.id}` : `/api/admin/${review.action}/${review.item.id}`;
    setBusy(true);
    try {
      await api.post(url, { remarks });
      toast({ approve: "Claim approved. The student was emailed a pickup code.", reject: "Claim rejected. The item is available again.", remove: "Listing removed. Its history is kept." }[review.action]);
      setReview(null);
      reload();
      setQueueKey((k) => k + 1);
    } catch (err) {
      toast((err as Error).message, "error");
    } finally {
      setBusy(false);
    }
  }

  async function movePoint(item: Item, value: string) {
    try {
      await api.post(`/api/item/${item.id}/collection-point`, { collection_point_id: value ? Number(value) : null });
      toast("Collection point saved.");
      reload();
    } catch (err) {
      toast((err as Error).message, "error");
    }
  }

  const counts = data?.counts;
  const stats = [
    { label: "Available", value: counts?.Available, icon: PackageSearch, tone: "text-emerald-600 bg-emerald-50 dark:bg-emerald-500/10", filter: { kind: null, status: "available" } },
    { label: "Claims to review", value: counts?.Pending, icon: Clock, tone: "text-amber-600 bg-amber-50 dark:bg-amber-500/10", filter: null },
    { label: "Awaiting pickup", value: counts?.Claimed, icon: PackageCheck, tone: "text-sky-600 bg-sky-50 dark:bg-sky-500/10", filter: { kind: null, status: "claimed" } },
    { label: "Open lost reports", value: counts?.lost, icon: ShieldAlert, tone: "text-rose-600 bg-rose-50 dark:bg-rose-500/10", filter: { kind: "lost", status: null } },
  ];
  const canExport = (can("items.manage") || can("claims.review")) && has("exports");

  return (
    <div>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">Admin</h1>
          <p className="text-sm text-stone-500">{session.college?.name} · {session.user.role_label}{session.user.campus ? ` · ${session.user.campus} campus` : ""}</p>
        </div>
        {canExport && (
          <a href={`/api/v1/admin/items.csv${qs(filters)}`} className="inline-flex items-center gap-2 rounded-xl border border-stone-200 bg-white px-4 py-2.5 text-sm font-semibold hover:bg-stone-50 dark:border-stone-700 dark:bg-stone-900 dark:hover:bg-stone-800">
            <Download className="size-4" aria-hidden /> Export CSV
          </a>
        )}
      </div>

      <nav aria-label="Admin tools" className="mt-4 flex flex-wrap gap-2">
        {[can("collection.verify") && ["/desk", "Pickup desk"], can("analytics.view") && has("analytics") && ["/admin/analytics", "Analytics"],
          can("college.settings") && ["/admin/collection-points", "Collection points"], has("events") && ["/events", "Events"],
          can("college.settings") && ["/admin/settings", "Settings"], can("audit.view") && ["/admin/activity", "Activity log"]]
          .filter(Boolean).map((l) => { const [to, label] = l as string[]; return (
            <Link key={to} to={to} className="rounded-full bg-white px-3.5 py-1.5 text-sm font-semibold text-stone-700 ring-1 ring-stone-200 hover:bg-stone-50 dark:bg-stone-900 dark:text-stone-200 dark:ring-stone-700">{label}</Link>
          ); })}
      </nav>

      {plan && plan.key !== "pilot" && (
        <p className="mt-3 text-xs text-stone-500">Plan: <strong>{plan.label}</strong>{plan.period_end ? ` until ${dateLabel(plan.period_end)}` : ""}.{plan.note ? ` ${plan.note}` : ""}</p>
      )}

      <div className="mt-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
        {stats.map((s) => (
          <button key={s.label} onClick={() => (s.filter ? update(s.filter) : document.getElementById("claims-queue")?.scrollIntoView({ behavior: "smooth" }))} className="rounded-2xl border border-stone-200 bg-white p-4 text-left transition hover:shadow-md dark:border-stone-800 dark:bg-stone-900">
            <span className={`inline-grid size-9 place-items-center rounded-xl ${s.tone}`}><s.icon className="size-5" aria-hidden /></span>
            <span className="mt-3 block text-2xl font-bold">{s.value ?? "–"}</span>
            <span className="block text-xs font-medium text-stone-500">{s.label}</span>
          </button>
        ))}
      </div>

      {can("claims.review") && <ClaimsQueue refreshKey={queueKey} onDecide={(item, action) => setReview({ item, action })} />}

      <h2 className="mt-8 text-xl">All items</h2>
      <div className="mt-3 flex flex-col gap-3 lg:flex-row lg:items-center">
        <div role="tablist" className="flex rounded-2xl bg-stone-200/70 p-1 dark:bg-stone-800">
          {(["found", "lost"] as Kind[]).map((k) => (
            <button key={k} role="tab" aria-selected={kind === k} onClick={() => update({ kind: k === "lost" ? "lost" : null, status: null })}
              className={`flex-1 whitespace-nowrap rounded-xl px-4 py-2 text-sm font-semibold ${kind === k ? "bg-white shadow dark:bg-stone-950" : "text-stone-600 dark:text-stone-400"}`}>
              {k === "found" ? "Found items" : "Lost reports"}
            </button>
          ))}
        </div>
        <form className="relative flex-1" role="search" onSubmit={(e) => { e.preventDefault(); update({ q: String(new FormData(e.currentTarget).get("q") ?? "").trim() || null }); }}>
          <Search className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-stone-400" aria-hidden />
          <input key={q} name="q" defaultValue={q} type="search" placeholder="Search name, place or category" aria-label="Search items" className={`${inputCls} pl-10`} />
        </form>
        <div className="flex gap-3">
          <Select aria-label="Status" value={status} onChange={(e) => update({ status: e.target.value || null })} className="lg:!w-48">
            {STATUS_OPTIONS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </Select>
          <Select aria-label="Category" value={category} onChange={(e) => update({ category: e.target.value || null })} className="lg:!w-44">
            <option value="">All categories</option>
            {session.config.categories.map((c) => <option key={c}>{c}</option>)}
          </Select>
          {campuses.length > 1 && (
            <Select aria-label="Campus" value={campus} onChange={(e) => update({ campus: e.target.value || null })} className="lg:!w-40">
              <option value="">All campuses</option>
              {campuses.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </Select>
          )}
        </div>
      </div>

      <div className="mt-5 space-y-3">
        {error ? <ErrorNote message={error} onRetry={reload} /> : loading && !data ? Array.from({ length: 4 }, (_, i) => <Skeleton key={i} className="h-32" />) :
          data && data.items.length === 0 ? (
            <Empty icon={<PackageSearch className="size-6" aria-hidden />} title={q || status || category || campus ? "Nothing matches these filters" : "No items reported yet"}>
              {q || status || category || campus ? "Try another search or status." : `Items reported at ${session.college?.display_name} appear here.`}
            </Empty>
          ) : data?.items.map((item) => (
            <motion.div key={item.id} layout initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
              <Card className={`p-4 sm:p-5 ${loading ? "opacity-60" : ""}`}>
                <div className="flex flex-col gap-4 md:flex-row">
                  <div className="flex min-w-0 flex-1 gap-4">
                    {item.photos[0] ? <img src={item.photos[0]} alt="" className="size-20 shrink-0 rounded-xl object-cover" />
                      : <div className="grid size-20 shrink-0 place-items-center rounded-xl bg-stone-100 text-stone-400 dark:bg-stone-800"><ImageOff className="size-6" aria-label="No photo" /></div>}
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="font-semibold">{item.name}</h3>
                        <Badge status={item.status} label={(item.kind === "lost" ? LOST_LABELS : ITEM_LABELS)[item.status]} />
                      </div>
                      <p className="mt-0.5 text-xs text-stone-500">{item.ref} · {item.category} · {item.location}{item.campus ? ` · ${item.campus}` : ""} · {dateLabel(item.reported_at)}{item.reported_by ? ` · by ${item.reported_by}` : ""}</p>
                      {item.description && <p className="mt-1 text-sm text-stone-600 dark:text-stone-400">{item.description}</p>}
                      {item.secret_detail && <p className="mt-2 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:bg-amber-500/10 dark:text-amber-200"><strong>Private detail:</strong> {item.secret_detail}</p>}
                      {kind === "found" && can("items.manage") && points.length > 0 && ["Available", "Pending", "Claimed"].includes(item.status) ? (
                        <label className="mt-2 flex items-center gap-2 text-xs text-stone-500">Held at
                          <Select value={item.collection_point?.id ?? ""} onChange={(e) => movePoint(item, e.target.value)} className="!w-auto !py-1.5 text-xs">
                            <option value="">No collection point</option>
                            {points.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                          </Select>
                        </label>
                      ) : item.collection_point && <p className="mt-1 text-xs text-stone-500">Held at {item.collection_point.name}</p>}
                    </div>
                  </div>
                  <div className="flex shrink-0 flex-wrap items-start gap-2 md:flex-col md:items-stretch">
                    {item.status === "Pending" && can("claims.review") && <>
                      <Button onClick={() => setReview({ item, action: "approve" })}><CheckCircle2 className="size-4" aria-hidden />Approve</Button>
                      <Button variant="secondary" onClick={() => setReview({ item, action: "reject" })}>Reject</Button>
                    </>}
                    {can("items.manage") && !["Pending", "Removed"].includes(item.status) && (
                      <Button variant="ghost" onClick={() => setReview({ item, action: "remove" })} aria-label={`Remove ${item.name}`}><Trash2 className="size-4" aria-hidden />Remove</Button>
                    )}
                  </div>
                </div>
                <MatchesPanel item={item} />
                {!!item.claims?.length && (
                  <details className="mt-4 group" open={item.status === "Pending"}>
                    <summary className="cursor-pointer text-sm font-semibold text-stone-600 dark:text-stone-300">Claims ({item.claims.length})</summary>
                    <div className="mt-3 space-y-2">
                      {item.claims.map((c) => (
                        <div key={c.id} className={`rounded-xl border p-3 text-sm ${["pending", "approved"].includes(c.status) ? "border-amber-200 bg-amber-50/50 dark:border-amber-500/20 dark:bg-amber-500/5" : "border-stone-200 dark:border-stone-800"}`}>
                          <div className="flex flex-wrap items-center gap-2">
                            <Badge status={c.status} label={CLAIM_LABELS[c.status]} />
                            {c.student_email && <span className="font-medium">{c.student_email}</span>}
                            {c.student_id && <span className="text-stone-500">ID {c.student_id}</span>}
                            {c.phone && <span className="text-stone-500">{c.phone}</span>}
                            <span className="ml-auto text-xs text-stone-400">{dateTimeLabel(c.timestamp)}</span>
                          </div>
                          {c.proof_description && <p className="mt-2 text-stone-700 dark:text-stone-300">“{c.proof_description}”</p>}
                          {!!c.flags?.length && (
                            <ul className="mt-2 space-y-1">
                              {c.flags.map((f) => <li key={f.code} className="flex items-start gap-1.5 text-xs text-amber-800 dark:text-amber-300"><AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden />{f.message}</li>)}
                            </ul>
                          )}
                          {c.reviewed_by && <p className="mt-1 text-xs text-stone-500">Reviewed by {c.reviewed_by} {dateTimeLabel(c.reviewed_at)}{c.review_remarks ? `: ${c.review_remarks}` : ""}</p>}
                          {c.collected_at && <p className="mt-1 text-xs text-emerald-700 dark:text-emerald-400">Collected {dateTimeLabel(c.collected_at)}{c.collected_by ? ` · handed over by ${c.collected_by}` : ""}</p>}
                        </div>
                      ))}
                    </div>
                  </details>
                )}
              </Card>
            </motion.div>
          ))}
        {data && <Pagination page={data.page} pages={data.pages} total={data.total} onPage={(p) => update({ page: String(p) })} />}
      </div>

      <Modal open={!!review} onClose={() => setReview(null)}
        title={review ? { approve: `Approve claim for ${review.item.name}?`, reject: `Reject claim for ${review.item.name}?`, remove: `Remove ${review.item.name}?` }[review.action] : ""}>
        {review && (
          <form onSubmit={act} className="space-y-4">
            <p className="text-sm text-stone-600 dark:text-stone-400">
              {{ approve: "The student gets an email with pickup details and a one-time pickup code. Staff check the code at handover.",
                 reject: "The student is told why, and the item becomes available to claim again.",
                 remove: "The listing disappears for students. Its claim history is kept." }[review.action]}
            </p>
            {review.action !== "remove" && (
              <Field label={review.action === "reject" ? "Reason (sent to the student)" : "Note to the student (optional)"}>
                <Textarea name="remarks" maxLength={1000} required={review.action === "reject"} rows={3} />
              </Field>
            )}
            <div className="flex gap-3">
              <Button type="button" variant="secondary" className="flex-1" onClick={() => setReview(null)}>Cancel</Button>
              <Button type="submit" className="flex-1" busy={busy} variant={review.action === "approve" ? "primary" : "danger"}>
                {{ approve: "Approve", reject: "Reject claim", remove: "Remove listing" }[review.action]}
              </Button>
            </div>
          </form>
        )}
      </Modal>
    </div>
  );
}
