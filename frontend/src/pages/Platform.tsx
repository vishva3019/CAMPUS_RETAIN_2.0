import { useState, type FormEvent } from "react";
import { Building2 } from "lucide-react";
import { api } from "../lib/api";
import { dateLabel, plural } from "../lib/format";
import { useFetch } from "../lib/useFetch";
import type { College } from "../lib/types";
import { useToast } from "../components/Toast";
import { BarList } from "../components/charts";
import { Badge, Button, Card, Empty, ErrorNote, Field, Input, Skeleton, Textarea, inputCls } from "../components/ui";

type Data = { items: College[]; statuses: string[]; totals: { colleges: number; active: number; pending: number; accounts: number } };
const tone: Record<string, string> = { active: "Available", pending: "Pending", suspended: "Removed" };

function CollegeRow({ c, statuses, reload }: { c: College; statuses: string[]; reload: () => void }) {
  const toast = useToast();
  const [status, setStatus] = useState(c.status);
  const [busy, setBusy] = useState<string | null>(null);
  async function call(key: string, url: string, body: object, ok: string) {
    setBusy(key);
    try {
      await api.post(url, body);
      toast(ok);
      reload();
      return true;
    } catch (err) {
      toast((err as Error).message, "error");
      return false;
    } finally {
      setBusy(null);
    }
  }
  return (
    <div className="flex flex-col gap-4 p-4 sm:p-5 lg:flex-row lg:items-start">
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2"><h3 className="font-semibold">{c.name}</h3><Badge status={tone[c.status] ?? c.status} label={c.status} /></div>
        <p className="mt-0.5 text-xs text-stone-500">/c/{c.slug} · {c.domains.join(", ")}{c.city ? ` · ${c.city}` : ""} · added {dateLabel(c.created_at)}</p>
        <p className="mt-0.5 text-xs text-stone-500">{plural(c.accounts, "account")} · {plural(c.items, "item")} · {c.approved_or_returned} approved or returned</p>
        <p className="mt-0.5 text-xs text-stone-500">Admins: {c.admins.length ? c.admins.map((a) => a.email + (a.invited ? " (invited)" : "")).join(", ") : "none yet"}</p>
        <label className="mt-2 inline-flex cursor-pointer items-center gap-2 text-xs font-medium text-stone-600 dark:text-stone-300">
          <input type="checkbox" checked={c.listed_on_signup} disabled={busy === "l"} className="size-4 accent-brand-600"
            onChange={(e) => call("l", `/api/v1/platform/colleges/${c.id}/signup-listing`, { listed: e.target.checked },
              e.target.checked ? `${c.name} now appears on the sign-up screen.` : `${c.name} is hidden from the sign-up screen.`)} />
          Show on the public sign-up and sign-in screens{c.status !== "active" && c.listed_on_signup ? " (once active)" : ""}
        </label>
      </div>
      <div className="flex flex-col gap-2 sm:flex-row">
        <div className="flex gap-2">
          <select aria-label={`Status for ${c.name}`} value={status} onChange={(e) => setStatus(e.target.value)} className={`${inputCls} !w-36`}>
            {statuses.map((s) => <option key={s}>{s}</option>)}
          </select>
          <Button variant="secondary" disabled={status === c.status} busy={busy === "s"}
            onClick={() => call("s", `/api/v1/platform/colleges/${c.id}/status`, { status }, `${c.name} is now ${status}.`)}>Save</Button>
        </div>
        <form className="flex gap-2" onSubmit={async (e) => {
          e.preventDefault();
          const form = e.currentTarget;
          const email = String(new FormData(form).get("email") ?? "");
          if (await call("i", `/api/v1/platform/colleges/${c.id}/admins`, { email }, `Invited ${email}. They set a password with “Forgot password?”.`)) form.reset();
        }}>
          <input name="email" type="email" required placeholder="admin email" aria-label={`New admin email for ${c.name}`} className={`${inputCls} !w-52`} />
          <Button type="submit" busy={busy === "i"}>Invite</Button>
        </form>
      </div>
    </div>
  );
}

interface Stats { colleges: { college_id: number; name: string; found: number; recovered: number; recovery_rate: number | null }[]; totals: { found: number; recovered: number; recovery_rate: number | null; accounts: number } }

export function Platform() {
  const toast = useToast();
  const { data, error, loading, reload } = useFetch<Data>("/api/v1/platform/colleges");
  const stats = useFetch<Stats>("/api/v1/platform/stats").data;
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  async function add(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const body = Object.fromEntries(new FormData(form));
    setBusy(true);
    setFormError(null);
    try {
      await api.post("/api/v1/platform/colleges", body);
      toast(`${body.name} added as pending. Activate it when it's verified.`);
      form.reset();
      reload();
    } catch (err) {
      setFormError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const t = data?.totals;
  return (
    <div>
      <h1 className="text-2xl font-bold">Colleges</h1>
      <div className="mt-5 grid grid-cols-2 gap-3 md:grid-cols-4">
        {[["Colleges", t?.colleges], ["Active", t?.active], ["Awaiting approval", t?.pending], ["Accounts", t?.accounts]].map(([l, v]) => (
          <Card key={l as string} className="p-4"><div className="text-2xl font-bold">{(v as number | undefined) ?? "–"}</div><div className="text-xs font-medium text-stone-500">{l}</div></Card>
        ))}
      </div>
      {stats && stats.totals.found > 0 && (
        <Card className="mt-6 p-4 sm:p-5">
          <BarList title={`Found items and recovery by college · overall ${stats.totals.recovery_rate === null ? "–" : Math.round(stats.totals.recovery_rate * 100) + "%"} recovered`}
            rows={stats.colleges.filter((c) => c.found > 0).map((c) => ({ label: c.name, value: c.found, note: `${c.recovered} recovered${c.recovery_rate !== null ? ` (${Math.round(c.recovery_rate * 100)}%)` : ""}` }))} />
        </Card>
      )}
      <Card className="mt-6 divide-y divide-stone-100 dark:divide-stone-800">
        {error ? <div className="p-4"><ErrorNote message={error} onRetry={reload} /></div> : loading && !data ? <Skeleton className="m-4 h-24" /> :
          data && data.items.length === 0 ? <div className="p-4"><Empty icon={<Building2 className="size-6" aria-hidden />} title="No colleges yet">Add the first one below.</Empty></div> :
          data?.items.map((c) => <CollegeRow key={c.id} c={c} statuses={data.statuses} reload={reload} />)}
      </Card>
      <Card className="mt-6 p-5">
        <h2 className="font-semibold">Add a college</h2>
        <p className="mt-1 text-xs text-stone-500">New colleges start as <strong>pending</strong>. Students can register only after you set them to active.</p>
        <form onSubmit={add} className="mt-4 grid gap-4 md:grid-cols-2">
          <Field label="Name"><Input name="name" required maxLength={160} /></Field>
          <Field label="Slug (used in the URL)"><Input name="slug" required maxLength={60} pattern="[a-z0-9-]+" placeholder="e.g. mvj-ce" /></Field>
          <Field label="Short name"><Input name="short_name" maxLength={40} /></Field>
          <Field label="City"><Input name="city" maxLength={80} /></Field>
          <div className="md:col-span-2"><Field label="Student email domains (comma separated)"><Input name="domains" required placeholder="students.example.edu.in, example.edu.in" /></Field></div>
          <Field label="Lost-and-found contact email"><Input name="contact_email" type="email" maxLength={160} /></Field>
          <Field label="Lost-and-found office"><Input name="support_office" maxLength={160} placeholder="e.g. Student Services, Block A" /></Field>
          <div className="md:col-span-2"><Field label="Pickup instructions (sent when a claim is approved)"><Textarea name="pickup_instructions" maxLength={2000} rows={2} /></Field></div>
          {formError && <div className="md:col-span-2"><ErrorNote message={formError} /></div>}
          <div className="md:col-span-2"><Button type="submit" busy={busy}>Add college</Button></div>
        </form>
      </Card>
    </div>
  );
}
