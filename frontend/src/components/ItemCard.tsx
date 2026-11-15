import { motion } from "motion/react";
import { CalendarDays, ImageOff, MapPin } from "lucide-react";
import type { Item } from "../lib/types";
import { dateLabel } from "../lib/format";
import { Badge, ITEM_LABELS, LOST_LABELS } from "./ui";

interface Props { item: Item; onOpen: (i: Item) => void }

/** Card in the item grid. The whole card opens the details view. */
export function ItemCard({ item, onOpen }: Props) {
  const lost = item.kind === "lost";
  const when = item.occurred_on ?? item.reported_at;
  return (
    <motion.article layout initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
      className="group relative flex min-w-0 flex-col overflow-hidden rounded-2xl border border-stone-200 bg-white shadow-sm transition hover:-translate-y-0.5 hover:shadow-lg sm:rounded-3xl dark:border-stone-800 dark:bg-stone-900">
      <div className="relative aspect-[4/3] bg-stone-100 dark:bg-stone-800">
        {item.photos[0] ? (
          <img src={item.photos[0]} alt="" loading="lazy" decoding="async" className="size-full object-cover transition duration-500 group-hover:scale-[1.03]" />
        ) : (
          <div className="grid size-full place-items-center text-stone-400"><ImageOff className="size-9" aria-label="No photo" /></div>
        )}
        <span className="absolute left-2 top-2 sm:left-3 sm:top-3">
          {lost ? <Badge status={item.status === "Available" ? "Removed" : item.status} label={item.status === "Available" ? "Lost" : LOST_LABELS[item.status]} />
            : <Badge status={item.status} label={ITEM_LABELS[item.status]} />}
        </span>
        {item.photos.length > 1 && (
          <span className="absolute bottom-2 right-2 rounded-full bg-black/60 px-2 py-0.5 text-[11px] font-semibold text-white">{item.photos.length} photos</span>
        )}
      </div>
      <div className="flex flex-1 flex-col p-3 sm:p-5">
        {item.category && <span className="truncate text-[10px] font-bold uppercase tracking-wider text-brand-600 sm:text-[11px] dark:text-brand-400">{item.category}</span>}
        <h3 className="mt-1 line-clamp-2 text-[15px] font-bold leading-snug sm:text-lg">
          <button onClick={() => onOpen(item)} className="text-left after:absolute after:inset-0 after:content-[''] focus-visible:outline-none">
            {item.name}
          </button>
        </h3>
        <ul className="mt-2 space-y-1 text-xs text-stone-500">
          {item.location && <li className="flex items-center gap-1.5"><MapPin className="size-3.5 shrink-0" aria-hidden /><span className="truncate">{item.location}</span></li>}
          {when && <li className="flex items-center gap-1.5"><CalendarDays className="size-3.5 shrink-0" aria-hidden />{lost ? "Lost" : "Found"} {dateLabel(when)}</li>}
        </ul>
        <div className="mt-auto pt-3 sm:pt-4">
          <span className="block rounded-xl border border-stone-200 py-2 text-center text-xs font-semibold text-brand-700 transition group-hover:border-brand-600 group-hover:bg-brand-50 group-focus-within:ring-2 group-focus-within:ring-brand-600 sm:text-sm dark:border-stone-700 dark:text-brand-300 dark:group-hover:bg-brand-500/10">
            View details
          </span>
        </div>
      </div>
    </motion.article>
  );
}
