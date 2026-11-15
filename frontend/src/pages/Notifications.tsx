import { useEffect, useState } from "react";
import { useNavigate } from "react-router";
import { BellRing, CheckCheck, ChevronRight, Inbox } from "lucide-react";
import { api, qs } from "../lib/api";
import { currentSubscription, disablePush, enablePush, pushSupported } from "../lib/push";
import { appLink, dateTimeLabel } from "../lib/format";
import { useFetch } from "../lib/useFetch";
import { useSession } from "../lib/session";
import type { Notification, Page } from "../lib/types";
import { useToast } from "../components/Toast";
import { Button, Card, Empty, ErrorNote, Pagination, Skeleton } from "../components/ui";

function PushToggle() {
  const toast = useToast();
  const [state, setState] = useState<"unknown" | "on" | "off" | "unavailable">("unknown");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    api.get<{ enabled: boolean }>("/api/v1/push/key").then(async (k) => {
      if (!k.enabled || !pushSupported()) return setState("unavailable");
      setState((await currentSubscription()) ? "on" : "off");
    }).catch(() => setState("unavailable"));
  }, []);
  if (state === "unavailable" || state === "unknown") return null;
  async function toggle() {
    setBusy(true);
    try {
      if (state === "on") { await disablePush(); setState("off"); toast("Notifications turned off on this device."); }
      else { const err = await enablePush(); if (err) toast(err, "error"); else { setState("on"); toast("You'll get notifications on this device."); } }
    } catch (e) { toast((e as Error).message || "Couldn't change notifications.", "error"); }
    finally { setBusy(false); }
  }
  return (
    <Card className="mb-4 flex flex-wrap items-center gap-3 p-4">
      <BellRing className="size-5 text-brand-600" aria-hidden />
      <p className="flex-1 text-sm">{state === "on" ? "Notifications are on for this device." : "Get a notification on this device when your claim is approved or someone finds your item."}</p>
      <Button variant={state === "on" ? "secondary" : "primary"} busy={busy} onClick={toggle}>{state === "on" ? "Turn off" : "Turn on"}</Button>
    </Card>
  );
}

/** Notification centre: only events that matter (matches, claim decisions, pickup codes
 * and reminders, returns). Unread stays unread until opened or marked read. */
export function Notifications() {
  const { session, setUnread } = useSession();
  const navigate = useNavigate();
  const [page, setPage] = useState(1);
  const { data, error, loading, reload, setData } = useFetch<Page<Notification> & { unread: number }>(`/api/v1/notifications${qs({ page })}`);
  const [busy, setBusy] = useState(false);

  async function markRead(ids?: number[]) {
    const r = await api.post<{ unread: number }>("/api/v1/notifications/read", ids ? { ids } : {});
    setUnread(r.unread);
    setData((d) => d && { ...d, unread: r.unread, items: d.items.map((n) => (!ids || ids.includes(n.id) ? { ...n, read: true } : n)) });
  }

  async function open(n: Notification) {
    const to = appLink(n.link);
    if (!n.read) await markRead([n.id]).catch(() => {});
    if (to) navigate(to);
  }

  async function markAll() {
    setBusy(true);
    try { await markRead(); } finally { setBusy(false); }
  }

  return (
    <div className="mx-auto max-w-3xl">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">Notifications</h1>
          <p className="mt-1 text-sm text-stone-500">{session.unread ? `${session.unread} unread` : "Updates about your claims and reports."}</p>
        </div>
        {!!data?.unread && <Button variant="secondary" busy={busy} onClick={markAll}><CheckCheck className="size-4" aria-hidden />Mark all as read</Button>}
      </div>
      <div className="mt-5">
        <PushToggle />
        {error ? <ErrorNote message={error} onRetry={reload} /> : loading && !data ? <Skeleton className="h-48" /> :
          !data?.items.length ? (
            <Empty icon={<Inbox className="size-6" aria-hidden />} title="You're all caught up!">We'll let you know when something happens with your claims or reports.</Empty>
          ) : (<>
            <Card className="divide-y divide-stone-100 overflow-hidden dark:divide-stone-800">
              {data.items.map((n) => {
                const to = appLink(n.link);
                return (
                  <button key={n.id} onClick={() => open(n)} disabled={!to && n.read}
                    className={`flex w-full gap-3 px-4 py-4 text-left transition sm:px-5 ${n.read ? "hover:bg-stone-50 dark:hover:bg-stone-800/50" : "bg-brand-50/70 hover:bg-brand-50 dark:bg-brand-500/5"} disabled:cursor-default`}>
                    <span className={`mt-1.5 size-2.5 shrink-0 rounded-full ${n.read ? "bg-transparent" : "bg-brand-600"}`} />
                    <span className="min-w-0 flex-1">
                      <span className="flex flex-wrap items-baseline justify-between gap-x-3">
                        <span className={n.read ? "font-medium text-stone-700 dark:text-stone-300" : "font-semibold text-stone-900 dark:text-stone-100"}>{n.title}</span>
                        <span className="text-xs text-stone-400">{dateTimeLabel(n.created_at)}</span>
                      </span>
                      {n.body && <span className="mt-0.5 block text-sm text-stone-600 dark:text-stone-400">{n.body}</span>}
                      <span className="sr-only">{n.read ? "Read" : "Unread"}</span>
                    </span>
                    {to && <ChevronRight className="mt-1 size-4 shrink-0 text-stone-400" aria-hidden />}
                  </button>
                );
              })}
            </Card>
            <Pagination page={data.page} pages={data.pages} total={data.total} onPage={setPage} />
          </>)}
      </div>
    </div>
  );
}
