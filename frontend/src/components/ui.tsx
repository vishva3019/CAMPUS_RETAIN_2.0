import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from "react";
import { ChevronLeft, ChevronRight, Loader2 } from "lucide-react";

export const inputCls =
  "w-full rounded-xl border border-stone-200 bg-white px-3.5 py-2.5 text-sm text-stone-900 placeholder:text-stone-400 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/30 dark:border-stone-700 dark:bg-stone-950 dark:text-stone-100";

export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="block text-sm font-medium text-stone-700 dark:text-stone-300">
      {label}
      <div className="mt-1">{children}</div>
      {hint && <span className="mt-1 block text-xs font-normal text-stone-500">{hint}</span>}
    </label>
  );
}

export const Input = (p: InputHTMLAttributes<HTMLInputElement>) => <input {...p} className={`${inputCls} ${p.className ?? ""}`} />;
export const Textarea = (p: TextareaHTMLAttributes<HTMLTextAreaElement>) => <textarea rows={3} {...p} className={`${inputCls} ${p.className ?? ""}`} />;
export const Select = (p: SelectHTMLAttributes<HTMLSelectElement>) => <select {...p} className={`${inputCls} ${p.className ?? ""}`} />;

type Variant = "primary" | "secondary" | "danger" | "success" | "ghost";
const variants: Record<Variant, string> = {
  primary: "bg-brand-600 text-white hover:bg-brand-700",
  secondary: "border border-stone-200 bg-white text-stone-700 hover:bg-stone-50 dark:border-stone-700 dark:bg-stone-900 dark:text-stone-200 dark:hover:bg-stone-800",
  danger: "bg-rose-600 text-white hover:bg-rose-700",
  success: "bg-emerald-600 text-white hover:bg-emerald-700",
  ghost: "text-stone-600 hover:bg-stone-100 dark:text-stone-300 dark:hover:bg-stone-800",
};

export function Button({ variant = "primary", busy, children, className, ...rest }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; busy?: boolean }) {
  return (
    <button {...rest} disabled={busy || rest.disabled}
      className={`inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-xl px-4 py-2.5 text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-60 ${variants[variant]} ${className ?? ""}`}>
      {busy && <Loader2 className="size-4 animate-spin" aria-hidden />}
      {children}
    </button>
  );
}

const statusTone: Record<string, string> = {
  Available: "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300",
  Pending: "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300",
  Claimed: "bg-sky-50 text-sky-700 dark:bg-sky-500/10 dark:text-sky-300",
  Returned: "bg-stone-100 text-stone-600 dark:bg-stone-800 dark:text-stone-300",
  Removed: "bg-rose-50 text-rose-700 dark:bg-rose-500/10 dark:text-rose-300",
  pending: "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300",
  approved: "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300",
  rejected: "bg-rose-50 text-rose-700 dark:bg-rose-500/10 dark:text-rose-300",
  collected: "bg-stone-100 text-stone-600 dark:bg-stone-800 dark:text-stone-300",
};

export const ITEM_LABELS: Record<string, string> = {
  Available: "Available", Pending: "Claim under review", Claimed: "Awaiting pickup", Returned: "Returned", Removed: "Removed",
};
export const LOST_LABELS: Record<string, string> = { Available: "Still missing", Returned: "Found", Removed: "Removed" };
export const CLAIM_LABELS: Record<string, string> = {
  pending: "Under review", approved: "Approved: ready to collect", rejected: "Not approved",
  withdrawn: "Withdrawn", collected: "Collected", closed: "Closed",
};

export function Badge({ status, label }: { status: string; label?: string }) {
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${statusTone[status] ?? "bg-stone-100 text-stone-600 dark:bg-stone-800 dark:text-stone-300"}`}>
      {label ?? status}
    </span>
  );
}

export function Pagination({ page, pages, total, onPage }: { page: number; pages: number; total: number; onPage: (p: number) => void }) {
  if (pages <= 1) return null;
  return (
    <nav className="mt-8 flex items-center justify-center gap-3 text-sm" aria-label="Pages">
      <Button variant="secondary" disabled={page <= 1} onClick={() => onPage(page - 1)} aria-label="Previous page"><ChevronLeft className="size-4" aria-hidden /></Button>
      <span className="text-stone-500">Page {page} of {pages} · {total}</span>
      <Button variant="secondary" disabled={page >= pages} onClick={() => onPage(page + 1)} aria-label="Next page"><ChevronRight className="size-4" aria-hidden /></Button>
    </nav>
  );
}

export function Empty({ icon, title, children }: { icon: ReactNode; title: string; children?: ReactNode }) {
  return (
    <div className="rounded-3xl border-2 border-dashed border-stone-200 px-6 py-16 text-center dark:border-stone-800">
      <div className="mx-auto mb-3 grid size-12 place-items-center rounded-2xl bg-stone-100 text-stone-400 dark:bg-stone-800">{icon}</div>
      <p className="font-semibold text-stone-700 dark:text-stone-200">{title}</p>
      {children && <div className="mt-1 text-sm text-stone-500">{children}</div>}
    </div>
  );
}

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded-2xl bg-stone-200/70 dark:bg-stone-800 ${className}`} />;
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <section className={`rounded-2xl border border-stone-200 bg-white dark:border-stone-800 dark:bg-stone-900 ${className}`}>{children}</section>;
}

export function ErrorNote({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-300">
      {message} {onRetry && <button className="ml-2 font-semibold underline" onClick={onRetry}>Try again</button>}
    </div>
  );
}
