import { useState, type FormEvent } from "react";
import { MapPin } from "lucide-react";
import { api } from "../lib/api";
import { useFetch } from "../lib/useFetch";
import { useSession } from "../lib/session";
import type { CollectionPoint } from "../lib/types";
import { useToast } from "../components/Toast";
import { Badge, Button, Card, Empty, ErrorNote, Field, Input, Select, Skeleton, Textarea } from "../components/ui";

export function CollectionPoints() {
  const { session } = useSession();
  const toast = useToast();
  const { data, error, loading, reload } = useFetch<{ items: CollectionPoint[]; campuses: { id: number; name: string }[] }>("/api/v1/admin/collection-points");
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  async function add(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const body = Object.fromEntries(new FormData(form));
    setBusy(true);
    setFormError(null);
    try {
      await api.post("/api/v1/admin/collection-points", body);
      toast(`Added ${body.name}.`);
      form.reset();
      reload();
    } catch (err) {
      setFormError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function toggle(p: CollectionPoint) {
    try {
      await api.post(`/api/v1/admin/collection-points/${p.id}/toggle`);
      toast(`${p.name} is now ${p.is_active ? "closed" : "open"} for new items.`);
      reload();
    } catch (err) {
      toast((err as Error).message, "error");
    }
  }

  return (
    <div className="mx-auto max-w-4xl">
      <h1 className="text-2xl font-bold">Collection points</h1>
      <p className="mt-1 text-sm text-stone-500">Places where found items are handed in and collected, like a security cabin. Students pick one when reporting, and approved claimants are told where to go.</p>
      <div className="mt-5 space-y-3">
        {error ? <ErrorNote message={error} onRetry={reload} /> : loading && !data ? <Skeleton className="h-24" /> :
          data && data.items.length === 0 ? (
            <Empty icon={<MapPin className="size-6" aria-hidden />} title="No collection points yet">Until you add one, students are pointed to {session.college?.support_office || "your lost-and-found office"}.</Empty>
          ) : data?.items.map((p) => (
            <Card key={p.id} className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:p-5">
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2"><h3 className="font-semibold">{p.name}</h3><Badge status={p.is_active ? "Available" : "Returned"} label={p.is_active ? "Open" : "Closed"} /></div>
                <p className="mt-0.5 text-xs text-stone-500">{p.campus ? `${p.campus} campus · ` : ""}{p.opening_hours || "No hours set"} · {p.items_held ?? 0} item{p.items_held === 1 ? "" : "s"} held</p>
                {p.description && <p className="mt-1 text-sm text-stone-600 dark:text-stone-400">{p.description}</p>}
              </div>
              <Button variant="secondary" onClick={() => toggle(p)}>{p.is_active ? "Close" : "Reopen"}</Button>
            </Card>
          ))}
      </div>
      <Card className="mt-8 p-5">
        <h2 className="font-semibold">Add a collection point</h2>
        <form onSubmit={add} className="mt-4 grid gap-4 sm:grid-cols-2">
          <Field label="Name"><Input name="name" required maxLength={120} placeholder="e.g. Main gate security cabin" /></Field>
          <Field label="Opening hours"><Input name="opening_hours" maxLength={160} placeholder="e.g. Mon–Sat, 9 am – 5 pm" /></Field>
          {!!data?.campuses.length && (
            <Field label="Campus"><Select name="campus_id" defaultValue=""><option value="">All campuses</option>{data.campuses.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</Select></Field>
          )}
          <div className="sm:col-span-2"><Field label="Directions (optional)"><Textarea name="description" maxLength={1000} rows={2} /></Field></div>
          {formError && <div className="sm:col-span-2"><ErrorNote message={formError} /></div>}
          <div className="sm:col-span-2"><Button type="submit" busy={busy}>Add collection point</Button></div>
        </form>
      </Card>
    </div>
  );
}
