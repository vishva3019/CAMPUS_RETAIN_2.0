import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router";
import { ArrowLeft, CheckCircle2, HandHeart, ImagePlus, Lock, MapPin, PackageSearch, Pencil, Sparkles, X } from "lucide-react";
import { api, qs } from "../lib/api";
import { useSession } from "../lib/session";
import type { CollectionPoint, CollegeEvent, Item, Kind } from "../lib/types";
import { dateLabel } from "../lib/format";
import { Modal } from "./Modal";
import { ReportFlight } from "./PlaneFlight";
import { Button, ErrorNote, Field, Input, Select, Textarea } from "./ui";

interface Props { open: boolean; onClose: () => void; onDone: () => void; initialKind: Kind; match?: Item | null; skipChoose?: boolean }
type Step = "choose" | "details" | "review" | "done";
interface Values {
  name: string; category: string; occurred_on: string; location: string; description: string;
  secret_detail: string; collection_point_id: string; event_id: string; campus_id: string;
}
interface Result { id: number; ref: string; owners_alerted: number; suggestions: Item[] }

const empty = (match?: Item | null): Values => ({
  name: match?.name ?? "", category: match?.category ?? "Other", occurred_on: "", location: "", description: "",
  secret_detail: "", collection_point_id: "", event_id: "", campus_id: "",
});

/** Report a found or lost item: choose, fill in, review, done. */
export function ReportModal({ open, onClose, onDone, initialKind, match, skipChoose }: Props) {
  const { session } = useSession();
  const [step, setStep] = useState<Step>("choose");
  const [kind, setKind] = useState<Kind>(initialKind);
  const [v, setV] = useState<Values>(empty(match));
  const [files, setFiles] = useState<File[]>([]);
  const [previews, setPreviews] = useState<string[]>([]);
  const [points, setPoints] = useState<CollectionPoint[]>([]);
  const [events, setEvents] = useState<CollegeEvent[]>([]);
  const [coords, setCoords] = useState<{ lat: number; lng: number } | null>(null);
  const [locating, setLocating] = useState(false);
  const [busy, setBusy] = useState(false);
  const [aiBusy, setAiBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [touched, setTouched] = useState(false);
  const [dupes, setDupes] = useState<Item[]>([]);
  const [result, setResult] = useState<Result | null>(null);
  const [flying, setFlying] = useState(false);
  const landed = useCallback(() => setFlying(false), []);
  const { max_photos, max_image_mb, categories } = session.config;
  const now = new Date();
  const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
  const found = kind === "found";
  const campuses = session.college?.campuses ?? [];

  useEffect(() => {
    if (!open) return;
    setStep(match || skipChoose ? "details" : "choose");
    setKind(match ? "found" : initialKind);
    setV(empty(match));
    setFiles([]);
    setCoords(null);
    setError(null);
    setTouched(false);
    setDupes([]);
    setResult(null);
    setFlying(false);
    api.get<{ items: CollegeEvent[] }>("/api/v1/events").then((d) => {
      const open = d.items.filter((e) => e.is_open);
      setEvents(open);
      if (open.length === 1) setV((x) => ({ ...x, event_id: String(open[0].id) }));
    }).catch(() => setEvents([]));
    api.get<{ items: CollectionPoint[] }>("/api/v1/collection-points").then((d) => setPoints(d.items)).catch(() => setPoints([]));
  }, [open, initialKind, match, skipChoose]);

  useEffect(() => {
    const urls = files.map((f) => URL.createObjectURL(f));
    setPreviews(urls);
    return () => urls.forEach(URL.revokeObjectURL);
  }, [files]);

  const set = (k: keyof Values) => (e: { target: { value: string } }) => setV((x) => ({ ...x, [k]: e.target.value }));
  const missing = { name: v.name.trim().length < 2, location: v.location.trim().length < 2 };

  function addFiles(list: FileList | null) {
    if (!list) return;
    const picked = [...files, ...Array.from(list)];
    const tooBig = picked.find((f) => f.size > max_image_mb * 1024 * 1024);
    if (tooBig) return setError(`"${tooBig.name}" is larger than ${max_image_mb} MB.`);
    if (picked.length > max_photos) return setError(`You can add up to ${max_photos} photos.`);
    setError(null);
    setFiles(picked);
  }

  function locate() {
    if (!navigator.geolocation) return setError("This browser can't share a location.");
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      (p) => { setCoords({ lat: p.coords.latitude, lng: p.coords.longitude }); setLocating(false); },
      () => { setError("Location wasn't shared. You can still describe the place in words."); setLocating(false); },
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 60000 },
    );
  }

  async function suggestFromPhoto() {
    if (!files[0]) return;
    const body = new FormData();
    body.set("image", files[0]);
    setAiBusy(true);
    setError(null);
    try {
      const s = await api.post<{ name: string; category: string; description: string }>("/api/v1/ai/describe", body);
      setV((x) => ({ ...x, name: s.name || x.name, category: s.category || x.category, description: s.description || x.description }));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setAiBusy(false);
    }
  }

  async function checkDupes() {
    if (match || v.name.trim().length < 3) return setDupes([]);
    try {
      const r = await api.get<{ items: Item[] }>(`/api/v1/items/similar${qs({ kind, name: v.name, category: v.category, location: v.location, description: v.description })}`);
      setDupes(r.items);
    } catch {
      setDupes([]);
    }
  }

  function toReview(e: FormEvent) {
    e.preventDefault();
    setTouched(true);
    if (missing.name || missing.location) return;
    setError(null);
    setStep("review");
  }

  async function submit() {
    const form = new FormData();
    form.set("kind", kind);
    for (const [k, val] of Object.entries(v)) if (val && (found || !["secret_detail", "collection_point_id"].includes(k))) form.set(k, val);
    if (match) form.set("lost_item_id", String(match.id));
    if (coords && found) {
      form.set("latitude", coords.lat.toFixed(5));
      form.set("longitude", coords.lng.toFixed(5));
    }
    files.forEach((f) => form.append("images", f));
    setBusy(true);
    setError(null);
    try {
      setResult(await api.post<Result>("/api/report", form));
      setFlying(true);
      setStep("done");
      onDone();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const title = step === "choose" ? "What would you like to do?" : step === "done" ? "Report submitted"
    : match ? `Found: ${match.name}` : step === "review" ? "Check your report" : found ? "Report a found item" : "Report a lost item";
  const point = points.find((p) => String(p.id) === v.collection_point_id);
  const footer = "sticky -bottom-6 -mx-6 -mb-6 mt-2 flex gap-3 border-t border-stone-100 bg-white/95 px-6 py-4 pb-[max(1rem,env(safe-area-inset-bottom))] backdrop-blur dark:border-stone-800 dark:bg-stone-900/95";

  return (
    <>
    {flying && result && <ReportFlight name={v.name} refCode={result.ref} kind={kind} onDone={landed} />}
    <Modal open={open} onClose={onClose} title={title}>
      {step === "choose" && (
        <div className="grid gap-3 sm:grid-cols-2">
          {([["found", HandHeart, "I found something", "Help it get back to its owner. Takes under a minute."],
             ["lost", PackageSearch, "I lost something", "Tell people what to look out for. We'll alert you if it turns up."]] as const).map(([k, Icon, label, sub]) => (
            <button key={k} onClick={() => { setKind(k); setStep("details"); }}
              className="group flex items-start gap-3 rounded-2xl border-2 border-stone-200 p-4 text-left transition hover:border-brand-600 hover:bg-brand-50/60 active:scale-[0.99] dark:border-stone-700 dark:hover:bg-brand-500/10">
              <span className="grid size-11 shrink-0 place-items-center rounded-xl bg-brand-50 text-brand-700 group-hover:bg-brand-700 group-hover:text-ivory dark:bg-brand-500/10 dark:text-brand-300">
                <Icon className="size-5" aria-hidden />
              </span>
              <span><span className="block font-semibold text-stone-900 dark:text-stone-100">{label}</span><span className="mt-0.5 block text-sm text-stone-500">{sub}</span></span>
            </button>
          ))}
        </div>
      )}

      {step === "details" && (
        <form onSubmit={toReview} noValidate className="space-y-4">
          {match && <p className="rounded-xl bg-brand-50 p-3 text-sm text-brand-900 dark:bg-brand-500/10 dark:text-brand-200">The person who lost it is told as soon as you submit.</p>}
          <div>
            <span className="text-sm font-medium text-stone-700 dark:text-stone-300">Photo <span className="font-normal text-stone-500">(optional, up to {max_photos})</span></span>
            <div className="mt-2 flex flex-wrap gap-2">
              {previews.map((src, i) => (
                <div key={src} className="relative size-20 overflow-hidden rounded-xl">
                  <img src={src} alt={`Photo ${i + 1}`} className="size-full object-cover" />
                  <button type="button" aria-label={`Remove photo ${i + 1}`} onClick={() => setFiles(files.filter((_, j) => j !== i))}
                    className="absolute right-1 top-1 grid size-7 place-items-center rounded-full bg-black/60 text-white"><X className="size-4" aria-hidden /></button>
                </div>
              ))}
              {files.length < max_photos && (
                <label className="grid size-20 cursor-pointer place-items-center rounded-xl border-2 border-dashed border-stone-300 text-stone-400 hover:border-brand-500 hover:text-brand-600 dark:border-stone-700">
                  <ImagePlus className="size-6" aria-hidden />
                  <span className="sr-only">Add photos</span>
                  <input type="file" accept="image/jpeg,image/png,image/webp,image/gif" multiple className="sr-only" onChange={(e) => { addFiles(e.target.files); e.target.value = ""; }} />
                </label>
              )}
              {session.config.ai_enabled && files.length > 0 && (
                <Button type="button" variant="secondary" busy={aiBusy} onClick={suggestFromPhoto} className="self-center">
                  <Sparkles className="size-4" aria-hidden />Suggest details from photo
                </Button>
              )}
            </div>
          </div>
          <Field label="What is it?">
            <Input value={v.name} onChange={set("name")} onBlur={checkDupes} maxLength={120} placeholder="e.g. Black leather wallet" aria-invalid={touched && missing.name} />
          </Field>
          {touched && missing.name && <p role="alert" className="-mt-2 text-sm text-rose-600">Say what the item is.</p>}
          <div className="grid grid-cols-2 gap-3">
            <Field label="Category"><Select value={v.category} onChange={set("category")}>{categories.map((c) => <option key={c}>{c}</option>)}</Select></Field>
            <Field label={found ? "Date found" : "Date lost"}><Input type="date" value={v.occurred_on} onChange={set("occurred_on")} max={today} /></Field>
          </div>
          <Field label={found ? "Where did you find it?" : "Where did you last have it?"}>
            <Input value={v.location} onChange={set("location")} onBlur={checkDupes} maxLength={150} placeholder="e.g. Library, 2nd floor" aria-invalid={touched && missing.location} />
          </Field>
          {touched && missing.location && <p role="alert" className="-mt-2 text-sm text-rose-600">Add the place, even roughly.</p>}
          {found && (
            <div className="-mt-1 flex flex-wrap items-center gap-2 text-sm">
              {coords ? (<>
                <span className="inline-flex items-center gap-1.5 text-brand-700 dark:text-brand-400"><MapPin className="size-4" aria-hidden />Approximate location added (about 100 m)</span>
                <button type="button" className="py-2 text-xs font-semibold text-stone-500 underline" onClick={() => setCoords(null)}>Remove</button>
              </>) : (
                <Button type="button" variant="ghost" busy={locating} onClick={locate}><MapPin className="size-4" aria-hidden />Add my approximate location</Button>
              )}
            </div>
          )}
          {dupes.length > 0 && (
            <div role="status" className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-200">
              <p className="font-semibold">Already reported? {dupes.length === 1 ? "This looks" : "These look"} similar:</p>
              <ul className="mt-1 list-disc pl-5">{dupes.map((d) => <li key={d.id}>{d.name} · {d.location} · {dateLabel(d.reported_at)}{d.is_mine ? " (your report)" : ""}</li>)}</ul>
              <p className="mt-1 text-xs">If it's the same item, you don't need to report it again.</p>
            </div>
          )}
          <Field label="Description" hint={found ? "Colour, brand, condition. Everyone at your college can see this, so leave out anything only the owner would know." : "Colour, brand, anything distinctive. Everyone at your college can see this."}>
            <Textarea value={v.description} onChange={set("description")} maxLength={2000} />
          </Field>
          {found && points.length > 0 && (
            <Field label="Where did you hand it in?">
              <Select value={v.collection_point_id} onChange={set("collection_point_id")}>
                <option value="">Not handed in yet</option>
                {points.map((p) => <option key={p.id} value={p.id}>{p.name}{p.campus ? ` · ${p.campus}` : ""}</option>)}
              </Select>
            </Field>
          )}
          {found && (
            <Field label="Private detail (only staff see this)" hint="Something only the real owner would know, e.g. the lock-screen photo or what's inside. Staff use it to check claims.">
              <Textarea value={v.secret_detail} onChange={set("secret_detail")} maxLength={2000} rows={2} />
            </Field>
          )}
          {found && (
            <p className="rounded-xl bg-indigo-50 px-3 py-2.5 text-xs text-indigo-900 dark:bg-indigo-500/10 dark:text-indigo-200">
              When staff approve someone's claim, the owner sees your name, email and phone so they can thank you. Nobody sees them before that.
            </p>
          )}
          {(events.length > 0 || campuses.length > 1) && (
            <div className="grid grid-cols-2 gap-3">
              {events.length > 0 && (
                <Field label="Event (optional)">
                  <Select value={v.event_id} onChange={set("event_id")}><option value="">Not at an event</option>{events.map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}</Select>
                </Field>
              )}
              {campuses.length > 1 && (
                <Field label="Campus">
                  <Select value={v.campus_id} onChange={set("campus_id")}><option value="">Not sure</option>{campuses.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</Select>
                </Field>
              )}
            </div>
          )}
          {error && <ErrorNote message={error} />}
          <div className={footer}>
            <Button type="button" variant="secondary" className="flex-1" onClick={() => (match ? onClose() : setStep("choose"))}>
              {match ? "Cancel" : <><ArrowLeft className="size-4" aria-hidden />Back</>}
            </Button>
            <Button type="submit" className="flex-1">Review</Button>
          </div>
        </form>
      )}

      {step === "review" && (
        <div className="space-y-4">
          <p className="text-sm text-stone-500">This is what students at {session.college?.display_name} will see. Check it, then submit.</p>
          {previews.length > 0 && (
            <div className="flex gap-2">{previews.map((src, i) => <img key={src} src={src} alt={`Photo ${i + 1}`} className="size-20 rounded-xl object-cover" />)}</div>
          )}
          <dl className="divide-y divide-stone-100 rounded-2xl border border-stone-200 text-sm dark:divide-stone-800 dark:border-stone-700">
            {([["Type", found ? "Found item" : "Lost item"], ["Item", v.name], ["Category", v.category],
              [found ? "Date found" : "Date lost", v.occurred_on ? dateLabel(v.occurred_on) : "Not given"],
              ["Place", v.location + (coords && found ? " (approximate location added)" : "")],
              ["Description", v.description || "None"],
              ...(found ? [["Handed in at", point ? point.name : "Not handed in yet"]] : []),
              ...(events.length && v.event_id ? [["Event", events.find((e) => String(e.id) === v.event_id)?.name ?? ""]] : []),
            ] as [string, string][]).map(([k, val]) => (
              <div key={k} className="flex gap-4 px-4 py-2.5"><dt className="w-28 shrink-0 text-stone-500">{k}</dt><dd className="min-w-0 break-words font-medium">{val}</dd></div>
            ))}
            {found && (
              <div className="flex gap-4 bg-amber-50/60 px-4 py-2.5 dark:bg-amber-500/5">
                <dt className="flex w-28 shrink-0 items-center gap-1 text-stone-500"><Lock className="size-3.5" aria-hidden />Private</dt>
                <dd className="min-w-0 break-words">{v.secret_detail || <span className="text-stone-400">None. Adding one helps staff spot false claims.</span>}<span className="block text-xs text-stone-500">Only staff see this.</span></dd>
              </div>
            )}
          </dl>
          {error && <ErrorNote message={error} />}
          <div className={footer}>
            <Button variant="secondary" className="flex-1" onClick={() => setStep("details")}><Pencil className="size-4" aria-hidden />Edit</Button>
            <Button className="flex-1" busy={busy} onClick={submit}>{found ? "Submit found item" : "Post lost report"}</Button>
          </div>
        </div>
      )}

      {step === "done" && result && (
        <div className="text-center">
          <CheckCircle2 className="mx-auto size-14 text-brand-600" aria-hidden />
          <p className="mt-3 text-lg font-semibold text-stone-900 dark:text-stone-100">{found ? "Thanks for reporting it!" : "Your lost report is live"}</p>
          <p className="mt-1 text-sm text-stone-500">Reference <strong className="font-mono text-stone-800 dark:text-stone-200">{result.ref}</strong> · saved in My activity</p>
          <p className="mx-auto mt-4 max-w-sm text-sm text-stone-600 dark:text-stone-300">
            {found
              ? (match || result.owners_alerted > 0
                ? `We've told ${match ? "the person who lost it" : result.owners_alerted === 1 ? "a student who reported losing something similar" : `${result.owners_alerted} students who reported losing something similar`}.`
                : "If someone reports losing something similar, they'll be pointed to it.")
                + (point ? ` It's listed as held at ${point.name}.` : ` Please hand it in to ${points.length ? "a collection point" : session.college?.support_office || "the lost-and-found office"} soon.`)
              : "We'll notify you if someone reports finding something that matches."}
          </p>
          {!found && result.suggestions.length > 0 && (
            <div className="mt-5 rounded-2xl border border-brand-200 bg-brand-50/60 p-4 text-left dark:border-brand-500/30 dark:bg-brand-500/10">
              <p className="text-sm font-semibold text-brand-900 dark:text-brand-200">Already found? These look similar:</p>
              <ul className="mt-2 space-y-1.5 text-sm">
                {result.suggestions.map((s) => (
                  <li key={s.id}><Link to={`/?item=${s.id}`} onClick={onClose} className="font-semibold text-brand-800 underline dark:text-brand-300">{s.name}</Link>
                    <span className="text-stone-500"> · {s.location} · {dateLabel(s.reported_at)}</span></li>
                ))}
              </ul>
            </div>
          )}
          <div className="mt-6 flex flex-col gap-2 sm:flex-row">
            <Link to="/activity?tab=reports" onClick={onClose} className="inline-flex flex-1 items-center justify-center rounded-xl border border-stone-200 px-4 py-2.5 text-sm font-semibold text-stone-700 hover:bg-stone-50 dark:border-stone-700 dark:text-stone-200">View in My activity</Link>
            <Button className="flex-1" onClick={onClose}>Done</Button>
          </div>
        </div>
      )}
    </Modal>
    </>
  );
}
