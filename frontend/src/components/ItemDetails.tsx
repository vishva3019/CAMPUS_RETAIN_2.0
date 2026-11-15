import { useEffect, useState } from "react";
import { Link } from "react-router";
import { CalendarDays, Clock, Hash, ImageOff, MapPin, ShieldCheck, Tag, Warehouse } from "lucide-react";
import { dateLabel } from "../lib/format";
import { useFetch } from "../lib/useFetch";
import type { Item } from "../lib/types";
import { Modal } from "./Modal";
import { Badge, Button, CLAIM_LABELS, ErrorNote, ITEM_LABELS, LOST_LABELS, Skeleton } from "./ui";

interface Props {
  itemId: number | null;
  onClose: () => void;
  onClaim: (item: Item) => void;
  onFound: (item: Item) => void;
}

/** What a student sees about one item: only public fields. The private detail, the
 * reporter's contact details and staff notes are never sent to students. */
export function ItemDetails({ itemId, onClose, onClaim, onFound }: Props) {
  const { data: item, error, reload } = useFetch<Item>(itemId ? `/api/v1/items/${itemId}` : null);
  const [photo, setPhoto] = useState(0);
  useEffect(() => setPhoto(0), [itemId]);
  const shown = item && item.id === itemId ? item : null;
  const lost = shown?.kind === "lost";

  return (
    <Modal open={!!itemId} onClose={onClose} title={shown?.name ?? "Item details"} wide>
      {error ? <ErrorNote message={error} onRetry={reload} /> : !shown ? (
        <div className="space-y-3"><Skeleton className="aspect-[4/3] w-full" /><Skeleton className="h-6 w-2/3" /><Skeleton className="h-4 w-1/2" /></div>
      ) : (
        <div className="space-y-5">
          <div>
            <div className="relative aspect-[4/3] overflow-hidden rounded-2xl bg-stone-100 dark:bg-stone-800">
              {shown.photos[photo] ? (
                <img src={shown.photos[photo]} alt={`${shown.name}, photo ${photo + 1}`} className="size-full object-contain" />
              ) : (
                <div className="grid size-full place-items-center text-stone-400"><ImageOff className="size-12" aria-label="No photo" /></div>
              )}
              <span className="absolute left-3 top-3">
                <Badge status={lost ? (shown.status === "Available" ? "Removed" : shown.status) : shown.status}
                  label={lost ? (shown.status === "Available" ? "Lost" : LOST_LABELS[shown.status]) : ITEM_LABELS[shown.status]} />
              </span>
            </div>
            {shown.photos.length > 1 && (
              <div className="mt-2 flex gap-2">
                {shown.photos.map((src, i) => (
                  <button key={src} onClick={() => setPhoto(i)} aria-label={`Show photo ${i + 1}`} aria-pressed={photo === i}
                    className={`size-16 overflow-hidden rounded-xl ring-2 ${photo === i ? "ring-brand-600" : "ring-transparent"}`}>
                    <img src={src} alt="" className="size-full object-cover" loading="lazy" />
                  </button>
                ))}
              </div>
            )}
          </div>

          <dl className="grid gap-x-6 gap-y-3 text-sm sm:grid-cols-2">
            {shown.category && <Row icon={Tag} label="Category">{shown.category}</Row>}
            <Row icon={Hash} label="Reference">{shown.ref}</Row>
            {shown.occurred_on && <Row icon={CalendarDays} label={lost ? "Lost on" : "Found on"}>{dateLabel(shown.occurred_on)}</Row>}
            {shown.reported_at && <Row icon={Clock} label="Reported">{dateLabel(shown.reported_at)}</Row>}
            {shown.location && <Row icon={MapPin} label={lost ? "Last seen" : "Found at"}>{shown.location}{shown.campus ? ` · ${shown.campus}` : ""}</Row>}
            {!lost && shown.collection_point && (
              <Row icon={Warehouse} label="Held at">{shown.collection_point.name}{shown.collection_point.opening_hours ? ` (${shown.collection_point.opening_hours})` : ""}</Row>
            )}
          </dl>

          {shown.description && (
            <div>
              <h3 className="text-sm font-semibold text-stone-500">Description</h3>
              <p className="mt-1 whitespace-pre-line text-[15px] text-stone-800 dark:text-stone-200">{shown.description}</p>
            </div>
          )}

          {shown.my_claim && (
            <div className="rounded-xl bg-brand-50 px-4 py-3 text-sm text-brand-900 dark:bg-brand-500/10 dark:text-brand-200">
              You claimed this on {dateLabel(shown.my_claim.timestamp)}: <strong>{CLAIM_LABELS[shown.my_claim.status]}</strong>.{" "}
              <Link to={`/activity?claim=${shown.my_claim.id}`} className="font-semibold underline" onClick={onClose}>Track it in My activity</Link>
            </div>
          )}

          <p className="flex items-start gap-2 text-xs text-stone-500">
            <ShieldCheck className="mt-0.5 size-4 shrink-0" aria-hidden />
            {lost ? "The owner's contact details stay private. If you have it, tell us and they're notified straight away."
              : "Private identifying details are only seen by staff, who use them to check claims. The finder's contact details are shared with the owner only after staff approve the claim."}
          </p>

          <div className="sticky -bottom-6 -mx-6 -mb-6 flex gap-3 border-t border-stone-100 bg-white/95 px-6 py-4 pb-[max(1rem,env(safe-area-inset-bottom))] backdrop-blur dark:border-stone-800 dark:bg-stone-900/95">
            <Button variant="secondary" className="flex-1" onClick={onClose}>Close</Button>
            {shown.can_claim ? (
              <Button className="flex-1" onClick={() => onClaim(shown)}>This is mine</Button>
            ) : shown.can_report_found ? (
              <Button className="flex-1" onClick={() => onFound(shown)}>I found this</Button>
            ) : (
              <span className="flex flex-1 items-center justify-center px-3 text-center text-sm font-medium text-stone-500">
                {shown.is_mine ? "You reported this" : lost ? LOST_LABELS[shown.status] ?? "Closed" : ITEM_LABELS[shown.status]}
              </span>
            )}
          </div>
        </div>
      )}
    </Modal>
  );
}

function Row({ icon: Icon, label, children }: { icon: typeof Tag; label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-2.5">
      <Icon className="mt-0.5 size-4 shrink-0 text-stone-400" aria-hidden />
      <div className="min-w-0">
        <dt className="text-xs text-stone-500">{label}</dt>
        <dd className="font-medium text-stone-800 dark:text-stone-200">{children}</dd>
      </div>
    </div>
  );
}
