import { useEffect, useRef, useState } from "react";
import { Link, Navigate, useSearchParams } from "react-router";
import { Check, ClipboardList, Clock3, Gift, ImageOff, KeyRound, MapPin, PackageOpen, Send, Sparkles, X } from "lucide-react";
import { api } from "../lib/api";
import { dateLabel, dateTimeLabel } from "../lib/format";
import { useFetch } from "../lib/useFetch";
import type { Item, Match, MyClaim } from "../lib/types";
import { useToast } from "../components/Toast";
import { Modal } from "../components/Modal";
import { ClaimFlight } from "../components/PlaneFlight";
import { Badge, Button, Card, Empty, ErrorNote, ITEM_LABELS, LOST_LABELS, Skeleton } from "../components/ui";

type Tab = "claims" | "reports" | "recovered";

function useAction() {
  const toast = useToast();
  const [busy, setBusy] = useState<string | null>(null);
  async function run(key: string, url: string, success: string, after: () => void) {
    setBusy(key);
    try {
      await api.post(url);
      toast(success);
      after();
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setBusy(null);
    }
  }
  return { busy, run };
}

function Thumb({ src, alt }: { src: string | null; alt: string }) {
  return src ? <img src={src} alt={alt} loading="lazy" className="size-16 shrink-0 rounded-xl object-cover" />
    : <div className="grid size-16 shrink-0 place-items-center rounded-xl bg-stone-100 text-stone-400 dark:bg-stone-800"><ImageOff className="size-6" aria-label="No photo" /></div>;
}

// ---------------------------------------------------------------- claim timeline

const STEPS = [["submitted", "Submitted"], ["under_review", "Under review"], ["approved", "Approved"], ["awaiting_pickup", "Awaiting pickup"], ["returned", "Returned"]] as const;

function Timeline({ c }: { c: MyClaim }) {
  if (c.stage === "rejected" || c.stage === "withdrawn" || c.stage === "closed") {
    return (
      <ol className="mt-3 flex items-center gap-2 text-xs" aria-label="Claim progress">
        <li className="flex items-center gap-1.5 text-stone-500"><span className="grid size-5 place-items-center rounded-full bg-brand-700 text-ivory"><Check className="size-3" aria-hidden /></span>Submitted</li>
        <span className="h-px w-6 bg-stone-300" aria-hidden />
        <li className="flex items-center gap-1.5 font-semibold text-rose-700 dark:text-rose-300"><span className="grid size-5 place-items-center rounded-full bg-rose-600 text-white"><X className="size-3" aria-hidden /></span>{c.stage_label}</li>
      </ol>
    );
  }
  const reached = c.stage === "under_review" ? 1 : c.stage === "awaiting_pickup" ? 3 : 4;
  return (
    <ol className="mt-3 grid grid-cols-5 gap-1" aria-label="Claim progress">
      {STEPS.map(([key, label], i) => {
        const done = i < reached || (i === reached && c.stage === "returned");
        const current = i === reached && c.stage !== "returned";
        return (
          <li key={key} className="flex flex-col items-center text-center" aria-current={current ? "step" : undefined}>
            <div className="flex w-full items-center">
              <span className={`h-0.5 flex-1 ${i === 0 ? "invisible" : i <= reached ? "bg-brand-600" : "bg-stone-200 dark:bg-stone-700"}`} aria-hidden />
              <span className={`grid size-6 shrink-0 place-items-center rounded-full text-[11px] font-bold ${done ? "bg-brand-700 text-ivory" : current ? "bg-amber-400 text-amber-950 ring-4 ring-amber-200 dark:ring-amber-500/30" : "bg-stone-200 text-stone-500 dark:bg-stone-700"}`}>
                {done ? <Check className="size-3.5" aria-hidden /> : current ? <Clock3 className="size-3.5" aria-hidden /> : i + 1}
              </span>
              <span className={`h-0.5 flex-1 ${i === STEPS.length - 1 ? "invisible" : i < reached ? "bg-brand-600" : "bg-stone-200 dark:bg-stone-700"}`} aria-hidden />
            </div>
            <span className={`mt-1 text-[10px] leading-tight sm:text-xs ${current ? "font-semibold text-stone-900 dark:text-stone-100" : "text-stone-500"}`}>{label}</span>
            <span className="sr-only">{done ? "(done)" : current ? "(current)" : ""}</span>
          </li>
        );
      })}
    </ol>
  );
}

function PickupCode({ claim, onIssued }: { claim: MyClaim; onIssued: () => void }) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const [code, setCode] = useState<{ code: string; expires_at: string } | null>(null);
  async function reveal() {
    setBusy(true);
    try {
      const r = await api.post<{ code: string; expires_at: string }>(`/api/v1/me/claims/${claim.id}/pickup-code`);
      setCode(r);
      onIssued();
    } catch (e) {
      toast((e as Error).message, "error");
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <Button busy={busy} onClick={reveal} className="mt-3"><KeyRound className="size-4" aria-hidden />Show my pickup code</Button>
      <p className="mt-1.5 text-xs text-emerald-900/70 dark:text-emerald-200/70">This makes a new code (older ones stop working) and also emails it to you.</p>
      <Modal open={!!code} onClose={() => setCode(null)} title="Your pickup code">
        {code && (
          <div className="text-center">
            <p className="text-sm text-stone-500">Show this and your college ID card at the desk.</p>
            <p className="my-5 font-mono text-5xl font-bold tracking-[0.25em] text-brand-800 dark:text-brand-300" aria-label={`Code ${code.code.split("").join(" ")}`}>{code.code}</p>
            <p className="text-sm text-stone-500">Valid until {dateLabel(code.expires_at)}. Don't share it with anyone else.</p>
            <Button className="mt-6 w-full" onClick={() => setCode(null)}>Done</Button>
          </div>
        )}
      </Modal>
    </>
  );
}

const planeSeen = (id: number) => { try { return !!localStorage.getItem(`cr-plane-${id}`); } catch { return true; } };

function ClaimCard({ c, reload, highlight, autoOpen = false }: { c: MyClaim; reload: () => void; highlight: boolean; autoOpen?: boolean }) {
  const { busy, run } = useAction();
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => { if (highlight) ref.current?.scrollIntoView({ behavior: "smooth", block: "center" }); }, [highlight]);
  const point = c.pickup?.point;
  // Once a claim is approved, the paper plane flies in by itself the first time (then on request).
  const seenKey = `cr-plane-${c.id}`;
  const [note, setNote] = useState(autoOpen);
  const closeNote = () => { try { localStorage.setItem(seenKey, "1"); } catch { /* private mode */ } setNote(false); };
  return (
    <div ref={ref}>
      {note && c.finder && <ClaimFlight approved finder={c.finder} itemName={c.item.name} onDone={closeNote} />}
      <Card className={`p-4 sm:p-5 ${highlight ? "ring-2 ring-brand-600" : ""}`}>
        <div className="flex gap-4">
          <Thumb src={c.item.photo} alt={c.item.name} />
          <div className="min-w-0 flex-1">
            <h3 className="font-semibold">{c.item.name}</h3>
            <p className="mt-0.5 text-xs text-stone-500">
              {c.item.ref} · claimed {dateLabel(c.timestamp)}{c.item.college ? ` · ${c.item.college}` : ""}
              {c.collected_at ? ` · collected ${dateLabel(c.collected_at)}` : ""}
            </p>
            <p className="mt-1 text-sm font-semibold text-stone-700 dark:text-stone-200">{c.stage_label}</p>
          </div>
        </div>
        <Timeline c={c} />
        {c.finder && (
          <button onClick={() => setNote(true)}
            className="mt-4 flex w-full items-center gap-3 rounded-xl border border-indigo-100 bg-gradient-to-r from-sky-50 to-indigo-50 px-4 py-3 text-left transition hover:border-indigo-300 dark:border-indigo-500/20 dark:from-sky-500/10 dark:to-indigo-500/10">
            <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-gradient-to-br from-sky-400 to-indigo-600 text-white"><Send className="size-4" aria-hidden /></span>
            <span className="min-w-0"><span className="block text-sm font-bold text-indigo-900 dark:text-indigo-100">See who found it</span>
              <span className="block truncate text-xs text-indigo-700/80 dark:text-indigo-300">{c.finder.name}{c.finder.email || c.finder.phone ? " · contact details" : ""}</span></span>
          </button>
        )}
        {c.stage === "under_review" && <p className="mt-3 text-sm text-stone-600 dark:text-stone-400">Staff are checking your proof against details only they can see. You'll be notified when they decide.</p>}
        {c.review_remarks && <p className="mt-3 rounded-xl bg-stone-50 px-3 py-2 text-sm text-stone-700 dark:bg-stone-800 dark:text-stone-300"><span className="font-semibold">Staff remarks:</span> {c.review_remarks}</p>}
        {c.pickup && (
          <div className="mt-4 rounded-xl bg-emerald-50 p-4 text-sm text-emerald-950 dark:bg-emerald-500/10 dark:text-emerald-100">
            <p className="font-semibold">How to collect it</p>
            {point && (
              <p className="mt-1.5 flex items-start gap-2"><MapPin className="mt-0.5 size-4 shrink-0" aria-hidden />
                <span><strong>{point.name}</strong>{point.campus ? ` · ${point.campus}` : ""}{point.opening_hours ? ` · ${point.opening_hours}` : ""}{point.description ? <span className="block text-xs">{point.description}</span> : null}</span>
              </p>
            )}
            <p className="mt-1.5">{c.pickup.instructions}</p>
            <p className="mt-1.5">Bring your college ID card and your 6-digit pickup code.
              {c.pickup.code_expires_at && ` Your current code works until ${dateLabel(c.pickup.code_expires_at)}.`}
              {c.pickup.locked && " Too many wrong codes were entered, so get a new one below."}</p>
            <PickupCode claim={c} onIssued={reload} />
          </div>
        )}
        {c.status === "pending" && (
          <Button variant="ghost" className="mt-3 text-rose-700" busy={busy === `w${c.id}`}
            onClick={() => confirm("Withdraw this claim? Someone else can then claim the item.") && run(`w${c.id}`, `/api/v1/me/claims/${c.id}/withdraw`, "Claim withdrawn.", reload)}>
            Withdraw claim
          </Button>
        )}
      </Card>
    </div>
  );
}

function Claims({ claims, reload, focus }: { claims: MyClaim[]; reload: () => void; focus: number }) {
  const active = claims.filter((c) => c.stage === "under_review" || c.stage === "awaiting_pickup");
  const history = claims.filter((c) => !active.includes(c) && c.stage !== "returned");
  // Only one plane flies in by itself: the newest approved claim the student hasn't seen yet.
  const [autoId] = useState(() => claims.find((c) => c.finder && c.stage === "awaiting_pickup" && !planeSeen(c.id))?.id ?? 0);
  if (!claims.length) {
    return <Empty icon={<ClipboardList className="size-6" aria-hidden />} title="You haven't submitted any claims yet">See your item among the <Link to="/" className="font-semibold text-brand-700">found items</Link>? Open it and tap “This is mine”.</Empty>;
  }
  return (
    <div className="space-y-6">
      <section>
        <h2 className="text-lg">Active claims</h2>
        {active.length ? <div className="mt-3 space-y-3">{active.map((c) => <ClaimCard key={c.id} c={c} reload={reload} highlight={c.id === focus} autoOpen={c.id === autoId} />)}</div>
          : <p className="mt-2 text-sm text-stone-500">Nothing in progress right now.</p>}
      </section>
      {history.length > 0 && (
        <section>
          <h2 className="text-lg">Claim history</h2>
          <div className="mt-3 space-y-3">{history.map((c) => <ClaimCard key={c.id} c={c} reload={reload} highlight={c.id === focus} />)}</div>
        </section>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- reports

function Matches() {
  const { busy, run } = useAction();
  const { data, reload } = useFetch<{ items: Match[] }>("/api/v1/me/matches");
  if (!data?.items.length) return null;
  return (
    <Card className="border-emerald-200 p-4 dark:border-emerald-500/30 sm:p-5">
      <h2 className="flex items-center gap-2 font-sans text-base font-semibold"><Sparkles className="size-4 text-emerald-600" aria-hidden />Found items that may be yours</h2>
      <p className="text-xs text-stone-500">Suggested because the name, category, place or date is close to your lost report. Only you can tell if it's yours.</p>
      <ul className="mt-3 space-y-3">
        {data.items.map((m) => (
          <li key={m.id} className="flex flex-col gap-3 rounded-xl bg-stone-50 p-3 dark:bg-stone-800/60 sm:flex-row sm:items-center">
            <Thumb src={m.item.photos[0] ?? null} alt={m.item.name} />
            <div className="min-w-0 flex-1 text-sm">
              <p><strong>{m.item.name}</strong> <span className="text-stone-500">· found at {m.item.location} · {dateLabel(m.item.reported_at)}</span></p>
              <p className="text-xs text-stone-500">For your lost report “{m.lost_item_name}”</p>
            </div>
            <div className="flex gap-2">
              <Link to={`/?item=${m.item.id}`} className="inline-flex items-center rounded-xl bg-brand-700 px-4 py-2.5 text-sm font-semibold text-white hover:bg-brand-800">View</Link>
              <Button variant="secondary" busy={busy === `d${m.id}`} onClick={() => run(`d${m.id}`, `/api/v1/matches/${m.id}/dismiss`, "Hidden. We won't suggest it again.", reload)}>Not mine</Button>
            </div>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function ReportList({ items, reload }: { items: Item[]; reload: () => void }) {
  const { busy, run } = useAction();
  return (
    <div className="mt-3 space-y-3">
      {items.map((i) => (
        <Card key={i.id} className="flex flex-col gap-4 p-4 sm:flex-row sm:items-center sm:p-5">
          <Link to={`/?item=${i.id}`} className="flex min-w-0 flex-1 gap-4">
            <Thumb src={i.photos[0] ?? null} alt={i.name} />
            <div className="min-w-0">
              <h3 className="font-semibold">{i.name}</h3>
              <p className="mt-0.5 text-xs text-stone-500">{i.ref} · {i.location} · reported {dateLabel(i.reported_at)}</p>
              <div className="mt-1.5"><Badge status={i.kind === "lost" && i.status === "Available" ? "Pending" : i.status}
                label={i.kind === "lost" ? (i.status === "Available" ? "Still missing" : LOST_LABELS[i.status]) : ITEM_LABELS[i.status]} /></div>
            </div>
          </Link>
          {i.kind === "lost" && i.status === "Available" && (
            <div className="flex gap-2">
              <Button busy={busy === `f${i.id}`} onClick={() => run(`f${i.id}`, `/api/v1/me/lost/${i.id}/found`, "Glad you got it back!", reload)}>I got it back</Button>
              <Button variant="secondary" busy={busy === `r${i.id}`} onClick={() => confirm("Remove this lost-item report?") && run(`r${i.id}`, `/api/v1/me/lost/${i.id}/withdraw`, "Report removed.", reload)}>Remove</Button>
            </div>
          )}
        </Card>
      ))}
    </div>
  );
}

function Reports({ reports, reload }: { reports: Item[]; reload: () => void }) {
  const found = reports.filter((r) => r.kind === "found");
  const lost = reports.filter((r) => r.kind === "lost");
  if (!reports.length) return <Empty icon={<PackageOpen className="size-6" aria-hidden />} title="You haven't reported anything yet">Found or lost something? Use “Report an item” on the home page.</Empty>;
  return (
    <div className="space-y-6">
      <Matches />
      {lost.length > 0 && <section><h2 className="text-lg">Things I lost</h2><ReportList items={lost} reload={reload} /></section>}
      {found.length > 0 && <section><h2 className="text-lg">Things I found</h2><ReportList items={found} reload={reload} /></section>}
    </div>
  );
}

function Recovered({ claims, reports }: { claims: MyClaim[]; reports: Item[] }) {
  const back = claims.filter((c) => c.stage === "returned");
  const selfFound = reports.filter((r) => r.kind === "lost" && r.status === "Returned");
  if (!back.length && !selfFound.length) {
    return <Empty icon={<Gift className="size-6" aria-hidden />} title="Nothing recovered yet">Items handed back to you appear here.</Empty>;
  }
  return (
    <div className="space-y-3">
      {back.map((c) => (
        <Card key={c.id} className="flex gap-4 p-4 sm:p-5">
          <Thumb src={c.item.photo} alt={c.item.name} />
          <div className="min-w-0">
            <h3 className="font-semibold">{c.item.name}</h3>
            <p className="mt-0.5 text-xs text-stone-500">{c.item.ref}{c.item.college ? ` · ${c.item.college}` : ""}</p>
            <p className="mt-1.5 text-sm text-brand-800 dark:text-brand-300">Returned to you {dateTimeLabel(c.collected_at)}</p>
          </div>
        </Card>
      ))}
      {selfFound.map((i) => (
        <Card key={i.id} className="flex gap-4 p-4 sm:p-5">
          <Thumb src={i.photos[0] ?? null} alt={i.name} />
          <div className="min-w-0">
            <h3 className="font-semibold">{i.name}</h3>
            <p className="mt-0.5 text-xs text-stone-500">{i.ref}</p>
            <p className="mt-1.5 text-sm text-brand-800 dark:text-brand-300">You marked this as found</p>
          </div>
        </Card>
      ))}
    </div>
  );
}

export function Activity() {
  const [params, setParams] = useSearchParams();
  if (params.get("tab") === "notifications") return <Navigate to="/notifications" replace />;
  const focus = Number(params.get("claim")) || 0;
  const tab = (["claims", "reports", "recovered"].includes(params.get("tab") ?? "") ? params.get("tab") : "claims") as Tab;
  return <ActivityTabs tab={tab} focus={focus} setTab={(t) => setParams(t === "claims" ? {} : { tab: t })} />;
}

function ActivityTabs({ tab, focus, setTab }: { tab: Tab; focus: number; setTab: (t: Tab) => void }) {
  const { data, error, loading, reload } = useFetch<{ claims: MyClaim[]; reports: Item[] }>("/api/v1/me/activity");
  const activeCount = data?.claims.filter((c) => c.stage === "under_review" || c.stage === "awaiting_pickup").length ?? 0;
  const tabs: { key: Tab; label: string; icon: typeof KeyRound; count?: number }[] = [
    { key: "claims", label: "My claims", icon: KeyRound, count: activeCount },
    { key: "reports", label: "My reports", icon: PackageOpen },
    { key: "recovered", label: "Recovered", icon: Gift },
  ];
  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="text-2xl font-bold">My activity</h1>
      <p className="mt-1 text-sm text-stone-500">Your claims, your reports and everything you've got back, in one place.</p>
      <div role="tablist" className="mt-4 flex gap-1 rounded-2xl bg-stone-200/70 p-1 dark:bg-stone-800">
        {tabs.map((t) => (
          <button key={t.key} role="tab" aria-selected={tab === t.key} onClick={() => setTab(t.key)}
            className={`flex flex-1 items-center justify-center gap-1.5 whitespace-nowrap rounded-xl px-2 py-2.5 text-sm font-semibold ${tab === t.key ? "bg-white shadow dark:bg-stone-950" : "text-stone-600 dark:text-stone-400"}`}>
            <t.icon className="hidden size-4 sm:block" aria-hidden />{t.label}
            {!!t.count && <span className="rounded-full bg-brand-700 px-1.5 text-[10px] text-white">{t.count}</span>}
          </button>
        ))}
      </div>
      <div className="mt-5">
        {error ? <ErrorNote message={error} onRetry={reload} /> : loading && !data ? (
          <div className="space-y-3"><Skeleton className="h-36" /><Skeleton className="h-36" /></div>
        ) : data && (
          tab === "claims" ? <Claims claims={data.claims} reload={reload} focus={focus} />
            : tab === "reports" ? <Reports reports={data.reports} reload={reload} />
              : <Recovered claims={data.claims} reports={data.reports} />
        )}
      </div>
    </div>
  );
}
