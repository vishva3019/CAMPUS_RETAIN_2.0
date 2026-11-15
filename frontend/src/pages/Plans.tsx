import { useState, type FormEvent } from "react";
import { CreditCard } from "lucide-react";
import { api } from "../lib/api";
import { dateLabel } from "../lib/format";
import { useFetch } from "../lib/useFetch";
import { useToast } from "../components/Toast";
import { Badge, Button, Card, ErrorNote, Input, Select, Skeleton } from "../components/ui";

interface PlanDef { key: string; label: string; summary: string; features: string[]; limits: Record<string, number | null> }
interface Row { id: number; name: string; status: string; reference: string | null; assigned_at: string | null;
  plan: { key: string; label: string; note: string | null; period_end: string | null; status: string | null } }
interface Data { colleges: Row[]; plans: PlanDef[]; statuses: string[]; features: Record<string, string> }

function AssignForm({ row, data, onDone }: { row: Row; data: Data; onDone: () => void }) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const body = Object.fromEntries(new FormData(e.currentTarget));
    setBusy(true);
    try {
      await api.post(`/api/v1/platform/colleges/${row.id}/plan`, body);
      toast(`${row.name} is now on ${data.plans.find((p) => p.key === body.plan)?.label}.`);
      onDone();
    } catch (err) {
      toast((err as Error).message, "error");
    } finally {
      setBusy(false);
    }
  }
  return (
    <form onSubmit={submit} className="grid gap-2 sm:grid-cols-[1fr_1fr_1fr_1.4fr_auto]">
      <Select name="plan" defaultValue={["free", "standard", "premium"].includes(row.plan.key) ? row.plan.key : "standard"} aria-label={`Plan for ${row.name}`}>
        {data.plans.map((p) => <option key={p.key} value={p.key}>{p.label}</option>)}
      </Select>
      <Select name="status" defaultValue="active" aria-label="Status">{data.statuses.map((s) => <option key={s}>{s}</option>)}</Select>
      <Input name="period_end" type="date" aria-label="Paid until" title="Paid until (leave empty for no end date)" />
      <Input name="reference" maxLength={120} placeholder="Invoice / UTR / reference" aria-label="Payment reference" />
      <Button type="submit" busy={busy}>Save</Button>
    </form>
  );
}

export function Plans() {
  const { data, error, loading, reload } = useFetch<Data>("/api/v1/platform/plans");
  return (
    <div>
      <h1 className="flex items-center gap-2 text-2xl font-bold"><CreditCard className="size-6 text-brand-600" aria-hidden />Plans</h1>
      <p className="mt-1 text-sm text-stone-500">Plans are assigned by hand: record the invoice or payment reference with each change. Colleges with no plan stay on Pilot (everything on). When a plan's end date passes, the college drops to Free until you renew it.</p>
      {error ? <div className="mt-5"><ErrorNote message={error} onRetry={reload} /></div> : loading && !data ? <Skeleton className="mt-5 h-64" /> : data && (
        <>
          <div className="mt-5 grid gap-3 md:grid-cols-3">
            {data.plans.map((p) => (
              <Card key={p.key} className="p-4">
                <h2 className="font-semibold">{p.label}</h2>
                <p className="mt-1 text-sm text-stone-600 dark:text-stone-400">{p.summary}</p>
                <p className="mt-2 text-xs text-stone-500">Collection points: {p.limits.collection_points ?? "unlimited"}</p>
              </Card>
            ))}
          </div>
          <Card className="mt-6 divide-y divide-stone-100 dark:divide-stone-800">
            {data.colleges.map((row) => (
              <div key={row.id} className="space-y-3 p-4 sm:p-5">
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="font-semibold">{row.name}</h3>
                  <Badge status={row.plan.key === "free" ? "Returned" : row.plan.key === "pilot" ? "Pending" : "Available"} label={row.plan.label} />
                  <span className="text-xs text-stone-500">
                    {row.plan.period_end ? `until ${dateLabel(row.plan.period_end)}` : row.plan.key !== "pilot" ? "no end date" : ""}
                    {row.reference ? ` · ref ${row.reference}` : ""}{row.assigned_at ? ` · set ${dateLabel(row.assigned_at)}` : ""}
                  </span>
                </div>
                {row.plan.note && <p className="text-xs text-amber-700 dark:text-amber-400">{row.plan.note}</p>}
                <AssignForm row={row} data={data} onDone={reload} />
              </div>
            ))}
          </Card>
        </>
      )}
    </div>
  );
}
