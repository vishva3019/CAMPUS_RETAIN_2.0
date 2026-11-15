import { useState, type FormEvent } from "react";
import { Printer, QrCode } from "lucide-react";
import { api } from "../lib/api";
import { dateLabel } from "../lib/format";
import { useFetch } from "../lib/useFetch";
import type { ItemTag } from "../lib/types";
import { useToast } from "../components/Toast";
import { Badge, Button, Card, Empty, ErrorNote, Input, Skeleton } from "../components/ui";

export function Tags() {
  const toast = useToast();
  const { data, error, loading, reload } = useFetch<{ items: ItemTag[] }>("/api/v1/me/tags");
  const [busy, setBusy] = useState(false);
  async function add(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const label = String(new FormData(form).get("label") ?? "").trim();
    setBusy(true);
    try {
      await api.post("/api/v1/me/tags", { label });
      toast("Tag created. Print it and stick it on your item.");
      form.reset();
      reload();
    } catch (err) {
      toast((err as Error).message, "error");
    } finally {
      setBusy(false);
    }
  }
  async function toggle(t: ItemTag) {
    try {
      await api.post(`/api/v1/me/tags/${t.id}/toggle`);
      reload();
    } catch (err) {
      toast((err as Error).message, "error");
    }
  }
  return (
    <div className="mx-auto max-w-4xl">
      <h1 className="flex items-center gap-2 text-2xl font-bold"><QrCode className="size-6 text-brand-600" aria-hidden />My QR tags</h1>
      <p className="mt-1 text-sm text-stone-500">Stick a QR tag on your bottle, laptop or keys. Anyone who finds it can scan it and send you a message, without seeing your name or email.</p>
      <form onSubmit={add} className="mt-5 flex gap-2 print:hidden">
        <Input name="label" required maxLength={80} placeholder="What will you put it on? e.g. Blue water bottle" aria-label="Tag label" />
        <Button type="submit" busy={busy}>Create tag</Button>
      </form>
      <div className="mt-5">
        {error ? <ErrorNote message={error} onRetry={reload} /> : loading && !data ? <Skeleton className="h-40" /> :
          !data?.items.length ? <Empty icon={<QrCode className="size-6" aria-hidden />} title="No tags yet">Create one above, then print it.</Empty> : (
            <>
              <div className="mb-3 flex justify-end print:hidden"><Button variant="secondary" onClick={() => window.print()}><Printer className="size-4" aria-hidden />Print active tags</Button></div>
              <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
                {data.items.map((t) => (
                  <Card key={t.id} className={`p-4 text-center ${t.is_active ? "" : "opacity-60 print:hidden"}`}>
                    <img src={`/api/v1/me/tags/${t.id}/qr.svg`} alt={`QR tag for ${t.label}`} className="mx-auto size-36 rounded-lg bg-white p-1" />
                    <p className="mt-2 text-sm font-semibold">{t.label}</p>
                    <p className="text-[11px] text-stone-500">If found, scan me · Campus Retain</p>
                    <div className="mt-3 space-y-1 text-xs text-stone-500 print:hidden">
                      <Badge status={t.is_active ? "Available" : "Returned"} label={t.is_active ? "Active" : "Turned off"} />
                      <p>Scanned {t.scan_count} time{t.scan_count === 1 ? "" : "s"}{t.last_scanned_at ? `, last ${dateLabel(t.last_scanned_at)}` : ""}</p>
                      <button className="font-semibold text-brand-600 dark:text-brand-400" onClick={() => toggle(t)}>{t.is_active ? "Turn off" : "Turn on"}</button>
                    </div>
                  </Card>
                ))}
              </div>
            </>
          )}
      </div>
    </div>
  );
}
