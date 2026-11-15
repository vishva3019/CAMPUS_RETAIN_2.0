import { useState, type FormEvent } from "react";
import { Link } from "react-router";
import { CalendarRange } from "lucide-react";
import { api } from "../lib/api";
import { dateLabel, plural } from "../lib/format";
import { useFetch } from "../lib/useFetch";
import { useSession } from "../lib/session";
import type { CollegeEvent } from "../lib/types";
import { useToast } from "../components/Toast";
import { Badge, Button, Card, Empty, ErrorNote, Field, Input, Select, Skeleton } from "../components/ui";

export function Events() {
  const { session, can, has } = useSession();
  const toast = useToast();
  const manage = can("college.settings") && has("events");
  const { data, error, loading, reload } = useFetch<{ items: CollegeEvent[] }>("/api/v1/events");
  const [busy, setBusy] = useState(false);
  const [showQr, setShowQr] = useState<number | null>(null);

  async function add(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const body = Object.fromEntries(new FormData(form));
    setBusy(true);
    try {
      await api.post("/api/v1/admin/events", body);
      toast(`${body.name} created. Share its QR code on posters so people can report and find items.`);
      form.reset();
      reload();
    } catch (err) {
      toast((err as Error).message, "error");
    } finally {
      setBusy(false);
    }
  }
  async function toggle(ev: CollegeEvent) {
    try { await api.post(`/api/v1/admin/events/${ev.id}/toggle`); reload(); } catch (err) { toast((err as Error).message, "error"); }
  }

  return (
    <div className="mx-auto max-w-4xl">
      <h1 className="flex items-center gap-2 text-2xl font-bold"><CalendarRange className="size-6 text-brand-600" aria-hidden />Events</h1>
      <p className="mt-1 text-sm text-stone-500">Fests, hackathons and sports meets get their own lost-and-found page. Reports made during an event can be tagged with it.</p>
      <div className="mt-5 space-y-3">
        {error ? <ErrorNote message={error} onRetry={reload} /> : loading && !data ? <Skeleton className="h-24" /> :
          !data?.items.length ? <Empty icon={<CalendarRange className="size-6" aria-hidden />} title="No events yet" /> :
          data.items.map((ev) => (
            <Card key={ev.id} className="p-4 sm:p-5">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2"><h3 className="font-semibold">{ev.name}</h3>
                    <Badge status={ev.is_open ? "Available" : "Returned"} label={!ev.is_active ? "Turned off" : ev.is_open ? "Taking reports" : "Closed"} /></div>
                  <p className="text-xs text-stone-500">{dateLabel(ev.starts_on)} – {dateLabel(ev.ends_on)}{ev.campus ? ` · ${ev.campus}` : ""} · {plural(ev.items, "item")}</p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Link to={`/?event=${ev.id}`} className="inline-flex items-center rounded-xl bg-brand-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-brand-700">See items</Link>
                  <Button variant="secondary" onClick={() => setShowQr(showQr === ev.id ? null : ev.id)}>{showQr === ev.id ? "Hide QR" : "QR code"}</Button>
                  {manage && <Button variant="ghost" onClick={() => toggle(ev)}>{ev.is_active ? "Turn off" : "Turn on"}</Button>}
                </div>
              </div>
              {showQr === ev.id && (
                <div className="mt-4 text-center">
                  <img src={`/api/v1/events/${ev.id}/qr.svg`} alt={`QR code for ${ev.name}`} className="mx-auto size-48 rounded-lg bg-white p-2" />
                  <p className="mt-1 text-xs text-stone-500">Opens this event's items for signed-in {session.college?.display_name} members.</p>
                </div>
              )}
            </Card>
          ))}
      </div>
      {manage && (
        <Card className="mt-8 p-5">
          <h2 className="font-semibold">Create an event</h2>
          <form onSubmit={add} className="mt-4 grid gap-4 sm:grid-cols-2">
            <div className="sm:col-span-2"><Field label="Name"><Input name="name" required maxLength={160} placeholder="e.g. TechFest 2026" /></Field></div>
            <Field label="Starts"><Input name="starts_on" type="date" required /></Field>
            <Field label="Ends"><Input name="ends_on" type="date" required /></Field>
            {!!session.college?.campuses.length && (
              <Field label="Campus"><Select name="campus_id" defaultValue=""><option value="">All campuses</option>{session.college.campuses.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</Select></Field>
            )}
            <div className="sm:col-span-2"><Button type="submit" busy={busy}>Create event</Button></div>
          </form>
        </Card>
      )}
    </div>
  );
}
