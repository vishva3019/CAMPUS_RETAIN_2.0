import { useEffect, useState, type FormEvent } from "react";
import { Settings as SettingsIcon } from "lucide-react";
import { api } from "../lib/api";
import { useFetch } from "../lib/useFetch";
import { useSession } from "../lib/session";
import { useToast } from "../components/Toast";
import { Button, Card, ErrorNote, Field, Input, Skeleton, Textarea } from "../components/ui";

interface S { support_office: string | null; pickup_instructions: string | null; contact_email: string | null; inter_college_matching: boolean }

export function Settings() {
  const { session, refresh, has } = useSession();
  const toast = useToast();
  const { data, error, reload } = useFetch<S>("/api/v1/admin/settings");
  const [network, setNetwork] = useState(false);
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (data) setNetwork(data.inter_college_matching); }, [data]);

  async function save(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.currentTarget));
    setBusy(true);
    try {
      await api.post("/api/v1/admin/settings", { ...f, inter_college_matching: network });
      toast("Settings saved.");
      refresh();
    } catch (err) {
      toast((err as Error).message, "error");
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="flex items-center gap-2 text-2xl font-bold"><SettingsIcon className="size-6 text-brand-600" aria-hidden />College settings</h1>
      <p className="mt-1 text-sm text-stone-500">{session.college?.name}</p>
      {error ? <div className="mt-5"><ErrorNote message={error} onRetry={reload} /></div> : !data ? <Skeleton className="mt-5 h-64" /> : (
        <form onSubmit={save} className="mt-5 space-y-5">
          <Card className="space-y-4 p-5">
            <h2 className="font-semibold">Lost-and-found office</h2>
            <Field label="Office name and place"><Input name="support_office" maxLength={160} defaultValue={data.support_office ?? ""} placeholder="e.g. Student Services, Block A" /></Field>
            <Field label="Contact email" hint="Gets an email for every found item and claim."><Input name="contact_email" type="email" maxLength={160} defaultValue={data.contact_email ?? ""} /></Field>
            <Field label="Pickup instructions" hint="Sent with every approved claim."><Textarea name="pickup_instructions" maxLength={2000} defaultValue={data.pickup_instructions ?? ""} /></Field>
          </Card>
          <Card className={`p-5 ${has("network") ? "" : "hidden"}`}>
            <label className="flex items-start gap-3">
              <input type="checkbox" checked={network} onChange={(e) => setNetwork(e.target.checked)} className="mt-1 size-4 accent-brand-600" />
              <span>
                <span className="font-semibold">Join the inter-college network</span>
                <span className="mt-1 block text-sm text-stone-500">Your students can search found items at other colleges in the network, and theirs can search yours. Other colleges only see each item's name, category, date and your college's name: no photos, places, descriptions or who reported it. Their claims come to your staff like any other claim.</span>
              </span>
            </label>
          </Card>
          <Button type="submit" busy={busy}>Save settings</Button>
        </form>
      )}
    </div>
  );
}
