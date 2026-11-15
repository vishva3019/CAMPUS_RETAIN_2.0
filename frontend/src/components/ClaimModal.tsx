import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router";
import { CheckCircle2 } from "lucide-react";
import { api } from "../lib/api";
import { useSession } from "../lib/session";
import type { Finder, Item } from "../lib/types";
import { ClaimFlight } from "./PlaneFlight";
import { Modal } from "./Modal";
import { Button, ErrorNote, Field, Input, Textarea } from "./ui";

interface Props { item: Pick<Item, "id" | "name"> | null; onClose: () => void; onDone: () => void; endpoint?: string; note?: string }

export function ClaimModal({ item, onClose, onDone, endpoint = "/api/claim", note }: Props) {
  const { session } = useSession();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);
  const [finder, setFinder] = useState<Finder | null>(null);

  useEffect(() => {
    setSent(false);
    setFinder(null);
    setError(null);
  }, [item]);

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!item) return;
    const f = new FormData(e.currentTarget);
    setBusy(true);
    setError(null);
    try {
      const r = await api.post<{ finder?: Finder }>(endpoint, { item_id: item.id, student_id: f.get("student_id"), phone: f.get("phone"), proof_description: f.get("proof") });
      setFinder(r?.finder ?? null);
      setSent(true);
      onDone();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
    {finder && item && <ClaimFlight finder={finder} itemName={item.name} onDone={() => setFinder(null)} />}
    <Modal open={!!item} onClose={onClose} title={sent ? "Claim sent" : `Claim: ${item?.name ?? ""}`}>
      {sent ? (
        <div className="py-4 text-center">
          <CheckCircle2 className="mx-auto size-14 text-brand-600" aria-hidden />
          <p className="mt-3 font-semibold text-stone-900 dark:text-stone-100">Your claim is under review</p>
          <p className="mt-1 text-stone-600 dark:text-stone-300">Staff will compare your proof with the details only they can see. You'll be notified when they decide. If it's approved, you'll get a pickup code.</p>
          <div className="mt-6 flex flex-col gap-2 sm:flex-row">
            <Link to="/activity" onClick={onClose} className="inline-flex flex-1 items-center justify-center rounded-xl border border-stone-200 px-4 py-2.5 text-sm font-semibold text-stone-700 hover:bg-stone-50 dark:border-stone-700 dark:text-stone-200">Track my claim</Link>
            <Button className="flex-1" onClick={onClose}>Done</Button>
          </div>
        </div>
      ) : (
        <form onSubmit={submit} className="space-y-4">
          <p className="text-sm text-stone-500">Claims are sent from <strong className="text-stone-700 dark:text-stone-200">{session.user.email}</strong>.</p>
          {note && <p className="rounded-xl bg-sky-50 p-3 text-sm text-sky-900 dark:bg-sky-500/10 dark:text-sky-200">{note}</p>}
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Student ID / USN"><Input name="student_id" required maxLength={50} autoComplete="off" defaultValue={session.user.student_id ?? ""} /></Field>
            <Field label="Phone (optional)"><Input name="phone" type="tel" maxLength={20} autoComplete="tel" /></Field>
          </div>
          <Field label="How can you prove it's yours?" hint="Describe something not shown in the listing: a mark, sticker, contents, lock-screen photo.">
            <Textarea name="proof" required maxLength={2000} rows={4} />
          </Field>
          {error && <ErrorNote message={error} />}
          <div className="sticky -bottom-6 -mx-6 -mb-6 mt-2 flex gap-3 border-t border-stone-100 bg-white/95 px-6 py-4 pb-[max(1rem,env(safe-area-inset-bottom))] backdrop-blur dark:border-stone-800 dark:bg-stone-900/95">
            <Button type="button" variant="secondary" className="flex-1" onClick={onClose}>Cancel</Button>
            <Button type="submit" className="flex-1" busy={busy}>Send claim</Button>
          </div>
        </form>
      )}
    </Modal>
    </>
  );
}
