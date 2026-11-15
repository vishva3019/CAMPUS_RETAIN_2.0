import { useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router";
import { ArrowRight, CalendarRange, ClipboardList, FileText, List, Map as MapIcon, PackageSearch, Plus, Search, SearchX, SlidersHorizontal, Sparkles, X } from "lucide-react";
import { MapView } from "../components/MapView";
import { qs } from "../lib/api";
import { useFetch } from "../lib/useFetch";
import { useSession } from "../lib/session";
import type { CollegeEvent, Item, Kind, MapPin, Page } from "../lib/types";
import { ItemCard } from "../components/ItemCard";
import { ItemDetails } from "../components/ItemDetails";
import { ReportModal } from "../components/ReportModal";
import { ClaimModal } from "../components/ClaimModal";
import { Button, Empty, ErrorNote, Pagination, Select, Skeleton, inputCls } from "../components/ui";

const EXAMPLES = ["Black backpack near library", "Blue water bottle in canteen", "Calculator in exam hall", "Keys with red keychain"];

interface Smart { items: Item[]; plan: { keywords: string; category: string; place: string; since_days: number }; relaxed: string[]; mode: "ai" | "basic" }

/** Results for "Describe what you lost": real items from this college only. */
function SmartResults({ ask, onOpen, onClear, onReportLost }: { ask: string; onOpen: (i: Item) => void; onClear: () => void; onReportLost: () => void }) {
  const { data, error, loading, reload } = useFetch<Smart>(`/api/v1/search/smart${qs({ q: ask })}`);
  const p = data?.plan;
  const since: Record<number, string> = { 1: "since yesterday", 7: "in the last week", 30: "in the last month", 90: "in the last 3 months" };
  const chips = p ? [p.keywords && `“${p.keywords}”`, p.category, p.place && `near ${p.place}`, p.since_days ? since[p.since_days] : ""].filter(Boolean) as string[] : [];
  return (
    <section className="mt-6 rounded-3xl border border-brand-200 bg-white p-4 sm:p-6 dark:border-brand-500/30 dark:bg-stone-900" aria-live="polite">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-xl">Matches for “{ask}”</h2>
          {chips.length > 0 && (
            <p className="mt-1.5 flex flex-wrap items-center gap-1.5 text-xs text-stone-500">
              {data?.mode === "ai" ? "AI understood:" : "Searching for:"}
              {chips.map((c) => <span key={c} className="rounded-full bg-brand-50 px-2 py-0.5 font-medium text-brand-800 dark:bg-brand-500/10 dark:text-brand-300">{c}</span>)}
            </p>
          )}
          {!!data?.relaxed.length && <p className="mt-1 text-xs text-stone-500">No exact match, so I widened the search (ignored the {data.relaxed.join(" and ")}).</p>}
        </div>
        <Button variant="ghost" onClick={onClear}><X className="size-4" aria-hidden />Clear</Button>
      </div>
      <div className="mt-4">
        {error ? <ErrorNote message={error} onRetry={reload} /> : loading && !data ? (
          <div className="grid grid-cols-2 gap-3 sm:gap-5 lg:grid-cols-4">{Array.from({ length: 4 }, (_, i) => <Skeleton key={i} className="h-60 sm:h-72" />)}</div>
        ) : data && data.items.length === 0 ? (
          <div className="rounded-2xl bg-stone-50 px-4 py-6 text-center dark:bg-stone-800/60">
            <p className="font-semibold text-stone-800 dark:text-stone-100">Nothing like that has been handed in yet</p>
            <p className="mt-1 text-sm text-stone-500">Report it as lost and you'll be notified as soon as something similar turns up.</p>
            <Button className="mt-4" onClick={onReportLost}><FileText className="size-4" aria-hidden />Report it as lost</Button>
          </div>
        ) : (<>
          <div className="grid grid-cols-2 gap-3 sm:gap-5 lg:grid-cols-4">{data?.items.map((i) => <ItemCard key={i.id} item={i} onOpen={onOpen} />)}</div>
          <p className="mt-4 text-center text-sm text-stone-500">Not there? <button onClick={onReportLost} className="py-1 font-semibold text-brand-700 underline dark:text-brand-400">Report it as lost</button> and we'll alert you.</p>
        </>)}
      </div>
    </section>
  );
}

const WHEN = [["", "Any time"], ["1", "Today"], ["7", "Last 7 days"], ["30", "Last 30 days"], ["90", "Last 3 months"]];
const STATUS = [["open", "Not yet returned"], ["available", "Available to claim"], ["returned", "Returned"], ["all", "All"]];

export function Browse() {
  const { session, can } = useSession();
  const [params, setParams] = useSearchParams();
  const view: Kind = params.get("view") === "lost" ? "lost" : "found";
  const q = params.get("q") ?? "";
  const category = params.get("category") ?? "";
  const campus = params.get("campus") ?? "";
  const since = params.get("since") ?? "";
  const place = params.get("place") ?? "";
  const availability = params.get("availability") ?? "open";
  const page = Number(params.get("page") ?? 1) || 1;
  const eventId = params.get("event") ?? "";
  const itemId = Number(params.get("item")) || null;
  const ask = params.get("ask") ?? "";
  const ai = !!session.config.ai_enabled;
  const showMap = params.get("display") === "map" && view === "found";
  const campuses = session.college?.campuses ?? [];
  const filterCount = [q, category, campus, since, place, view === "found" && availability !== "open" ? "x" : ""].filter(Boolean).length;
  const [filtersOpen, setFiltersOpen] = useState(filterCount > 0);

  const { data, error, loading, reload } = useFetch<Page<Item>>(
    showMap ? null : `/api/v1/items${qs({ kind: view, q, category, campus, since, place, page, event: eventId,
      availability: view === "found" ? availability : null })}`,
  );
  const pins = useFetch<{ items: MapPin[] }>(showMap ? "/api/v1/map/items" : null);
  const events = useFetch<{ items: CollegeEvent[] }>("/api/v1/events").data?.items ?? [];
  const event = events.find((e) => String(e.id) === eventId);
  const [reportOpen, setReportOpen] = useState(false);
  const [match, setMatch] = useState<Item | null>(null);
  const [claiming, setClaiming] = useState<Item | null>(null);
  const [reportKind, setReportKind] = useState<Kind | null>(null);

  function update(next: Record<string, string | null>) {
    const p = new URLSearchParams(params);
    for (const [k, v] of Object.entries(next)) (v ? p.set(k, v) : p.delete(k));
    if (!("page" in next) && !("item" in next)) p.delete("page");
    setParams(p, { replace: "item" in next });
  }
  const openItem = (i: Item) => update({ item: String(i.id) });
  const clearAll = () => update({ q: null, category: null, campus: null, since: null, place: null, availability: null });

  function onSearch(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    update({ q: String(new FormData(e.currentTarget).get("q") ?? "").trim() || null });
  }

  function startReport(found?: Item, kind?: Kind) {
    setMatch(found ?? null);
    setReportKind(kind ?? null);
    setReportOpen(true);
  }

  function onAsk(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const v = String(new FormData(e.currentTarget).get("ask") ?? "").trim();
    update({ ask: v.length >= 2 ? v : null });
  }

  const anyFilter = !!(q || filterCount);
  const college = session.college;

  return (
    <div>
      {/* Hero: find (describe it), report, track */}
      <section className="relative px-1 pb-8 pt-4 text-center sm:pb-12 sm:pt-10">
        <span className="pointer-events-none absolute -left-40 -top-32 size-[28rem] rounded-full bg-brand-200/45 blur-3xl dark:bg-brand-500/15" aria-hidden />
        <span className="pointer-events-none absolute -right-40 top-1/3 size-[26rem] rounded-full bg-cyan-200/40 blur-3xl dark:bg-cyan-500/10" aria-hidden />
        <p className="relative mx-auto inline-flex items-center gap-2 rounded-full border border-stone-200 bg-white px-3.5 py-1.5 text-xs font-semibold text-brand-800 dark:border-stone-700 dark:bg-stone-900 dark:text-brand-300">
          <span className="size-1.5 rounded-full bg-brand-600" aria-hidden />{college?.name} · Lost &amp; Found{ai ? " · AI-assisted" : ""}
        </p>
        <h1 className="relative mt-5 text-4xl leading-[1.05] tracking-tight sm:text-6xl">
          Lost something?<br /><span className="text-brand-700 dark:text-brand-400">{ai ? "AI helps you find it." : "Let's find it."}</span>
        </h1>
        <p className="relative mx-auto mt-4 max-w-2xl text-[15px] text-stone-600 sm:text-lg dark:text-stone-300">
          {ai ? `Describe it in your own words. Campus Retain reads your description, searches every report at ${college?.display_name} and shows the closest matches. Staff verify every claim before anything is handed over.`
            : `Search every item reported at ${college?.display_name}, report what you've lost or found, and track your claims in one place.`}
        </p>
        <div className="relative mt-6 flex flex-wrap justify-center gap-2 sm:gap-3">
          <a href="#catalog" className="inline-flex items-center gap-2 rounded-xl border border-stone-200 bg-white px-4 py-2.5 text-sm font-semibold text-stone-800 shadow-sm transition hover:border-stone-300 active:scale-[0.98] sm:px-5 sm:py-3 dark:border-stone-700 dark:bg-stone-900 dark:text-stone-100">
            <Search className="size-4" aria-hidden />Browse catalog
          </a>
          {can("items.report") && (
            <button onClick={() => startReport(undefined, "lost")}
              className="inline-flex items-center gap-2 rounded-xl border border-brand-200 bg-white px-4 py-2.5 text-sm font-semibold text-brand-800 shadow-sm transition hover:border-brand-500 active:scale-[0.98] sm:px-5 sm:py-3 dark:border-brand-500/30 dark:bg-stone-900 dark:text-brand-300">
              <FileText className="size-4" aria-hidden />Report lost item
            </button>
          )}
          {can("items.report") && (
            <button onClick={() => startReport(undefined, "found")}
              className="inline-flex items-center gap-2 rounded-xl bg-brand-700 px-4 py-2.5 text-sm font-semibold text-ivory shadow-sm transition hover:bg-brand-800 active:scale-[0.98] sm:px-5 sm:py-3">
              <Plus className="size-4" aria-hidden />I found something
            </button>
          )}
        </div>

        <form onSubmit={onAsk} role="search" className="relative mx-auto mt-8 flex max-w-3xl flex-col gap-2 rounded-2xl border border-stone-200 bg-white p-2 shadow-lg shadow-stone-900/[0.04] sm:flex-row sm:items-center dark:border-stone-700 dark:bg-stone-900">
          <label className="flex min-w-0 flex-1 items-center gap-2">
            <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-brand-50 text-brand-700 dark:bg-brand-500/10 dark:text-brand-300"><Sparkles className="size-5" aria-hidden /></span>
            <span className="sr-only">Describe what you lost</span>
            <input key={ask} name="ask" defaultValue={ask} type="search" enterKeyHint="search" maxLength={300}
              placeholder="Describe what you lost, e.g. black backpack near library yesterday"
              className="min-w-0 flex-1 bg-transparent px-1 py-2.5 text-[15px] text-stone-900 placeholder:text-stone-400 outline-none dark:text-stone-100" />
          </label>
          <Button type="submit" className="shrink-0 !px-5 !py-3">{ai ? "Search with AI" : "Search"} <ArrowRight className="size-4" aria-hidden /></Button>
        </form>
        <div className="relative mx-auto mt-3 flex max-w-3xl flex-wrap items-center justify-center gap-2 text-sm">
          <span className="text-stone-500">Try:</span>
          {EXAMPLES.map((ex) => (
            <button key={ex} onClick={() => update({ ask: ex, item: null })}
              className="rounded-full border border-stone-200 bg-white px-3 py-1.5 text-stone-700 transition hover:border-brand-500 hover:text-brand-800 dark:border-stone-700 dark:bg-stone-900 dark:text-stone-300">
              “{ex}”
            </button>
          ))}
        </div>
        <Link to="/activity" className="relative mt-5 inline-flex items-center gap-1.5 py-2 text-sm font-semibold text-stone-600 hover:text-brand-800 dark:text-stone-300">
          <ClipboardList className="size-4" aria-hidden />Track my claims and reports
        </Link>
      </section>

      {ask && <SmartResults ask={ask} onOpen={openItem} onClear={() => update({ ask: null })} onReportLost={() => startReport(undefined, "lost")} />}

      <div id="catalog" className="scroll-mt-20" />
      {/* Tabs + tools */}
      <div className="mt-7 flex flex-wrap items-center gap-2 sm:gap-3">
        <div role="tablist" aria-label="What to show" className="flex rounded-2xl bg-stone-200/70 p-1 dark:bg-stone-800">
          {(["found", "lost"] as Kind[]).map((k) => (
            <button key={k} role="tab" aria-selected={view === k} onClick={() => update({ view: k === "lost" ? "lost" : null, display: null })}
              className={`rounded-xl px-4 py-2 text-sm font-semibold transition ${view === k ? "bg-white shadow dark:bg-stone-950" : "text-stone-600 dark:text-stone-400"}`}>
              {k === "found" ? "Found items" : "Lost reports"}
            </button>
          ))}
        </div>
        <Button variant="secondary" onClick={() => setFiltersOpen((o) => !o)} aria-expanded={filtersOpen} aria-controls="filters">
          <SlidersHorizontal className="size-4" aria-hidden /> Filters{filterCount ? ` (${filterCount})` : ""}
        </Button>
        {view === "found" && (
          <div role="group" aria-label="Display" className="flex rounded-2xl bg-stone-200/70 p-1 dark:bg-stone-800">
            {[["", "List", List], ["map", "Map", MapIcon]].map(([v, label, Icon]) => {
              const I = Icon as typeof List;
              const on = (params.get("display") ?? "") === v;
              return (
                <button key={label as string} aria-pressed={on} onClick={() => update({ display: (v as string) || null })}
                  className={`flex items-center gap-1.5 rounded-xl px-3 py-2 text-sm font-semibold ${on ? "bg-white shadow dark:bg-stone-950" : "text-stone-600 dark:text-stone-400"}`}>
                  <I className="size-4" aria-hidden />{label as string}
                </button>
              );
            })}
          </div>
        )}
        {events.some((e) => e.is_open) && !eventId && (
          <Link to="/events" className="px-1 py-2 text-sm font-semibold text-brand-700 dark:text-brand-400">Events</Link>
        )}
        {anyFilter && <Button variant="ghost" onClick={clearAll}><X className="size-4" aria-hidden />Clear</Button>}
      </div>

      {filtersOpen && (
        <div id="filters" className="mt-3 grid grid-cols-2 gap-3 rounded-2xl border border-stone-200 bg-white p-3 sm:grid-cols-3 lg:grid-cols-6 dark:border-stone-800 dark:bg-stone-900">
          <form onSubmit={onSearch} role="search" className="col-span-2 sm:col-span-1">
            <input key={q} name="q" defaultValue={q} type="search" aria-label="Keyword" placeholder="Keyword" enterKeyHint="search" className={inputCls} />
          </form>
          <Select aria-label="Category" value={category} onChange={(e) => update({ category: e.target.value || null })}>
            <option value="">All categories</option>
            {session.config.categories.map((c) => <option key={c}>{c}</option>)}
          </Select>
          {campuses.length > 0 && (
            <Select aria-label="Campus" value={campus} onChange={(e) => update({ campus: e.target.value || null })}>
              <option value="">All campuses</option>
              {campuses.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </Select>
          )}
          <Select aria-label="Date reported" value={since} onChange={(e) => update({ since: e.target.value || null })}>
            {WHEN.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </Select>
          {view === "found" && (
            <Select aria-label="Status" value={availability} onChange={(e) => update({ availability: e.target.value === "open" ? null : e.target.value })}>
              {STATUS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </Select>
          )}
          <form className="col-span-2 sm:col-span-1" onSubmit={(e) => { e.preventDefault(); update({ place: String(new FormData(e.currentTarget).get("place") ?? "").trim() || null }); }}>
            <input key={place} name="place" defaultValue={place} aria-label="Place" placeholder="Place, e.g. library" enterKeyHint="search"
              className={inputCls} onBlur={(e) => e.target.value.trim() !== place && update({ place: e.target.value.trim() || null })} />
          </form>
        </div>
      )}

      {eventId && (
        <div className="mt-4 flex flex-wrap items-center gap-3 rounded-2xl bg-brand-50 px-4 py-3 text-sm text-brand-900 dark:bg-brand-500/10 dark:text-brand-200">
          <CalendarRange className="size-4" aria-hidden />
          <span>Showing items from <strong>{event?.name ?? "this event"}</strong></span>
          <button className="ml-auto py-1 font-semibold underline" onClick={() => update({ event: null })}>Show all items</button>
        </div>
      )}

      {showMap ? (
        <div className="mt-6">
          <p className="mb-3 text-sm text-stone-500">Found items with an approximate location (within about 100 m). Blue: available. Yellow: claim under review.</p>
          {pins.error ? <ErrorNote message={pins.error} onRetry={pins.reload} /> : !pins.data ? <Skeleton className="h-[420px]" /> :
            pins.data.items.length === 0 ? <Empty icon={<MapIcon className="size-6" aria-hidden />} title="No items with a location yet">When someone adds an approximate location to a found item, it shows on the map.</Empty> :
            <MapView pins={pins.data.items} />}
        </div>
      ) : (<>
        <h2 className="mt-7 text-xl">
          {q ? `Results for “${q}”` : view === "lost" ? "Things people are looking for" : "Recently found"}
          {data && <span className="ml-2 font-sans text-sm font-medium text-stone-400">{data.total}</span>}
        </h2>
        {view === "lost" && <p className="mt-1 text-sm text-stone-500">Seen one of these? Open it and tap <strong>I found this</strong>. The owner is told straight away.</p>}

        <div className="mt-4">
          {error ? (
            <ErrorNote message={error} onRetry={reload} />
          ) : loading && !data ? (
            <div className="grid grid-cols-2 gap-3 sm:gap-5 lg:grid-cols-4" aria-busy="true" aria-label="Loading items">
              {Array.from({ length: 8 }, (_, i) => <Skeleton key={i} className="h-60 sm:h-80" />)}
            </div>
          ) : data && data.items.length === 0 ? (
            anyFilter ? (
              <Empty icon={<SearchX className="size-6" aria-hidden />} title="Nothing matches">
                Try another word, or <button className="font-semibold text-brand-700 underline" onClick={clearAll}>clear the filters</button>.
              </Empty>
            ) : (
              <Empty icon={<PackageSearch className="size-6" aria-hidden />}
                title={view === "lost" ? "No one is looking for anything right now" : "No items have been reported yet"}>
                {view === "lost" ? "Lost something? Report it and we'll tell you if it turns up." : "Be the first to report something."}
                {can("items.report") && (
                  <div className="mt-4"><Button onClick={() => startReport()}><Plus className="size-4" aria-hidden />Report an item</Button></div>
                )}
              </Empty>
            )
          ) : (
            <div className={`grid grid-cols-2 gap-3 sm:gap-5 lg:grid-cols-4 ${loading ? "opacity-60" : ""}`}>
              {data?.items.map((item) => <ItemCard key={item.id} item={item} onOpen={openItem} />)}
            </div>
          )}
          {data && <Pagination page={data.page} pages={data.pages} total={data.total} onPage={(p) => update({ page: String(p) })} />}
        </div>
      </>)}

      <ItemDetails itemId={itemId} onClose={() => update({ item: null })}
        onClaim={(i) => { update({ item: null }); setClaiming(i); }}
        onFound={(i) => { update({ item: null }); startReport(i); }} />
      <ReportModal open={reportOpen} onClose={() => setReportOpen(false)} onDone={reload} initialKind={reportKind ?? view} match={match} skipChoose={!!reportKind} />
      <ClaimModal item={claiming} onClose={() => setClaiming(null)} onDone={reload} />
    </div>
  );
}
