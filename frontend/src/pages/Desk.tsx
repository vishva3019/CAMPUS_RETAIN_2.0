import { useState, type FormEvent } from "react";
import { useSearchParams } from "react-router";
import { ImageOff, PackageCheck, ScanLine, Search } from "lucide-react";
import { api, qs } from "../lib/api";
import { dateLabel, dateTimeLabel } from "../lib/format";
import { useFetch } from "../lib/useFetch";
import { useSession } from "../lib/session";
import type { DeskClaim, Page } from "../lib/types";
import { useToast } from "../components/Toast";
import { Button, Card, Empty, ErrorNote, Pagination, Skeleton, inputCls } from "../components/ui";
import { Modal } from "../components/Modal";

function VerifyForm({ claim, onDone }: { claim: DeskClaim; onDone: () => void }) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [idChecked, setIdChecked] = useState(false);

  function ask(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!/^\d{6}$/.test(code)) return setError("Enter the 6-digit code.");
    setError(null);
    setIdChecked(false);
    setConfirming(true);
  }

  async function handOver() {
    setBusy(true);
    try {
      await api.post(`/api/v1/desk/${claim.id}/verify`, { code });
      setConfirming(false);
      toast(`Handed over: ${claim.item.name} to ${claim.student_email}. Marked as returned.`);
      onDone();
    } catch (err) {
      setConfirming(false);
      setError((err as Error).message);
      setCode("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={ask} className="w-full sm:w-auto">
      <div className="flex gap-2">
        <input value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))} inputMode="numeric" autoComplete="off" placeholder="6-digit code"
          aria-label={`Pickup code for ${claim.item.name}`} className={`${inputCls} w-36 text-center font-mono tracking-[0.3em]`} />
        <Button type="submit" variant="success">Hand over</Button>
      </div>
      {error && <p role="alert" className="mt-2 max-w-xs text-xs text-rose-600 dark:text-rose-400">{error}</p>}
      <Modal open={confirming} onClose={() => setConfirming(false)} title="Confirm the handover">
        <div className="space-y-4 text-sm">
          <div className="flex gap-4 rounded-2xl bg-stone-50 p-3 dark:bg-stone-800">
            <Photo src={claim.item.photo} />
            <div>
              <p className="font-semibold">{claim.item.name}</p>
              <p className="text-stone-500">to {claim.student_email}{claim.student_id ? ` · ID ${claim.student_id}` : ""}</p>
            </div>
          </div>
          <label className="flex cursor-pointer items-start gap-3">
            <input type="checkbox" checked={idChecked} onChange={(e) => setIdChecked(e.target.checked)} className="mt-0.5 size-5 accent-brand-700" />
            <span>I've checked their college ID card{claim.student_id ? ` (ID ${claim.student_id})` : ""} and I'm giving them the item now.</span>
          </label>
          <p className="text-xs text-stone-500">The code is checked when you confirm. The item is then marked as returned and the handover is recorded under your name.</p>
          <div className="flex gap-3">
            <Button variant="secondary" className="flex-1" onClick={() => setConfirming(false)}>Cancel</Button>
            <Button variant="success" className="flex-1" busy={busy} disabled={!idChecked} onClick={handOver}>Confirm handover</Button>
          </div>
        </div>
      </Modal>
    </form>
  );
}

function Photo({ src }: { src: string | null }) {
  return src ? <img src={src} alt="" className="size-16 shrink-0 rounded-xl object-cover" />
    : <div className="grid size-16 shrink-0 place-items-center rounded-xl bg-stone-100 text-stone-400 dark:bg-stone-800"><ImageOff className="size-6" aria-label="No photo" /></div>;
}

export function Desk() {
  const { session } = useSession();
  const [params, setParams] = useSearchParams();
  const q = params.get("q") ?? "";
  const page = Number(params.get("page") ?? 1) || 1;
  const { data, error, loading, reload } = useFetch<Page<DeskClaim> & { recent: DeskClaim[] }>(`/api/v1/desk${qs({ q, page })}`);
  return (
    <div className="mx-auto max-w-4xl">
      <h1 className="flex items-center gap-2 text-2xl font-bold"><ScanLine className="size-6 text-brand-600" aria-hidden />Pickup desk</h1>
      <p className="mt-1 text-sm text-stone-500">
        Check the student's college ID card, then enter the 6-digit pickup code they show you (from their email or My activity). After {session.config.pickup_code_max_attempts} wrong codes, the student has to send themselves a new one from My activity.
      </p>
      <form role="search" className="relative mt-5" onSubmit={(e) => { e.preventDefault(); const v = String(new FormData(e.currentTarget).get("q") ?? "").trim(); setParams(v ? { q: v } : {}); }}>
        <Search className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-stone-400" aria-hidden />
        <input key={q} name="q" defaultValue={q} type="search" placeholder="Search item, student email or ID" aria-label="Search" className={`${inputCls} pl-10`} />
      </form>

      <h2 className="mt-6 font-semibold">Waiting for pickup {data && <span className="text-sm font-medium text-stone-400">{data.total}</span>}</h2>
      <div className="mt-3 space-y-3">
        {error ? <ErrorNote message={error} onRetry={reload} /> : loading && !data ? <Skeleton className="h-28" /> :
          data && data.items.length === 0 ? (
            <Empty icon={<PackageCheck className="size-6" aria-hidden />} title={q ? `Nothing waiting matches “${q}”` : "No approved items are waiting for pickup"} />
          ) : data?.items.map((c) => (
            <Card key={c.id} className="flex flex-col gap-4 p-4 sm:flex-row sm:items-center sm:p-5">
              <div className="flex min-w-0 flex-1 gap-4">
                <Photo src={c.item.photo} />
                <div className="min-w-0">
                  <h3 className="font-semibold">{c.item.name}</h3>
                  <p className="text-xs text-stone-500">{c.student_email}{c.student_id ? ` · ID ${c.student_id}` : ""}{c.phone ? ` · ${c.phone}` : ""}</p>
                  <p className="text-xs text-stone-500">Approved {dateLabel(c.reviewed_at)}{c.item.collection_point ? ` · at ${c.item.collection_point}` : ""}</p>
                  {!c.has_code && <p className="mt-1 text-xs text-amber-700 dark:text-amber-400">No code sent yet: ask the student to send one from My activity.</p>}
                  {c.wrong_attempts > 0 && <p className="mt-1 text-xs text-amber-700 dark:text-amber-400">{c.wrong_attempts} wrong code{c.wrong_attempts === 1 ? "" : "s"} entered</p>}
                </div>
              </div>
              <VerifyForm claim={c} onDone={reload} />
            </Card>
          ))}
        {data && <Pagination page={data.page} pages={data.pages} total={data.total} onPage={(p) => setParams({ ...(q ? { q } : {}), page: String(p) })} />}
      </div>

      <h2 className="mt-10 font-semibold">Recently handed over</h2>
      <Card className="mt-3 divide-y divide-stone-100 dark:divide-stone-800">
        {data?.recent.length ? data.recent.map((c) => (
          <div key={c.id} className="flex flex-col gap-1 px-4 py-3 text-sm sm:flex-row sm:justify-between sm:px-5">
            <span><strong>{c.item.name}</strong> to {c.student_email}</span>
            <span className="text-xs text-stone-500">{dateTimeLabel(c.collected_at)}{c.collected_by ? ` · by ${c.collected_by}` : ""}</span>
          </div>
        )) : <p className="px-5 py-6 text-sm text-stone-500">No handovers yet.</p>}
      </Card>
    </div>
  );
}
