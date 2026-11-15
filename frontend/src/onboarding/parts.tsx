/** Building blocks for the onboarding screens: the animated shell, progress, college
 * cards, the fixed-domain email box, password field and the 6-digit code input. */
import { useEffect, useId, useRef, useState, type ClipboardEvent, type KeyboardEvent, type ReactNode } from "react";
import { motion, useReducedMotion } from "motion/react";
import { Check, Eye, EyeOff, Loader2 } from "lucide-react";
import { initials, passwordStrength, type OnboardCollege } from "./lib";

// ---------------------------------------------------------------- brand + shell

import { BrandMark } from "../components/Brand";
export { BrandMark };

function Backdrop() {
  const reduce = useReducedMotion();
  const drift = (x: number, y: number) => (reduce ? undefined : { x: [0, x, 0], y: [0, y, 0] });
  return (
    <div className="pointer-events-none fixed inset-0 overflow-hidden" aria-hidden>
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,_#ffffff_0%,_#f3f6fb_55%,_#e6edf7_100%)]" />
      <motion.div className="absolute -left-40 -top-40 size-[34rem] rounded-full bg-brand-200/45 blur-3xl"
        animate={drift(60, 40)} transition={{ duration: 22, repeat: Infinity, ease: "easeInOut" }} />
      <motion.div className="absolute -right-48 top-1/3 size-[30rem] rounded-full bg-cyan-200/40 blur-3xl"
        animate={drift(-50, 60)} transition={{ duration: 26, repeat: Infinity, ease: "easeInOut" }} />
      <motion.div className="absolute -bottom-56 left-1/4 size-[28rem] rounded-full bg-brand-100/60 blur-3xl"
        animate={drift(40, -40)} transition={{ duration: 30, repeat: Infinity, ease: "easeInOut" }} />
    </div>
  );
}

export function AuthShell({ children, top }: { children: ReactNode; top?: ReactNode }) {
  return (
    <div className="relative min-h-dvh overflow-x-hidden bg-ivory text-stone-800 [color-scheme:light]">
      <Backdrop />
      <div className="relative z-10 mx-auto flex min-h-dvh w-full max-w-5xl flex-col px-4 pb-10 pt-5 sm:px-6">
        <header className="flex items-center justify-between gap-3">
          <a href="/" className="flex items-center gap-2.5 rounded-lg font-semibold tracking-tight text-stone-900">
            <BrandMark />
            <span className="font-display text-[17px] font-extrabold">Campus <span className="text-brand-700">Retain</span></span>
          </a>
          {top}
        </header>
        <main className="flex flex-1 flex-col">{children}</main>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- progress

export const STEPS = ["Welcome", "Select College", "Student Details", "Verify Email", "Account Created"];

export function Progress({ step }: { step: number }) {
  return (
    <nav aria-label="Sign-up progress" className="mx-auto mt-6 w-full max-w-2xl">
      <p className="mb-2 text-center text-xs font-medium text-stone-500 sm:hidden">
        Step {step + 1} of {STEPS.length} · <span className="text-stone-700">{STEPS[step]}</span>
      </p>
      <ol className="flex items-center gap-2">
        {STEPS.map((label, i) => {
          const done = i < step, current = i === step;
          return (
            <li key={label} className="flex flex-1 items-center gap-2" aria-current={current ? "step" : undefined}>
              <span className={`grid size-7 shrink-0 place-items-center rounded-full text-[11px] font-semibold transition-colors duration-300 ${done ? "bg-brand-700 text-ivory" : current ? "bg-stone-900 text-ivory shadow-[0_0_0_4px_rgba(29,78,216,0.18)]" : "bg-white text-stone-500 ring-1 ring-stone-200"}`}>
                {done ? <Check className="size-3.5" aria-hidden /> : i + 1}
              </span>
              <span className={`hidden whitespace-nowrap text-xs font-medium lg:inline ${current ? "text-stone-900" : done ? "text-stone-600" : "text-stone-500"}`}>{label}</span>
              <span className="sr-only">{done ? " (done)" : current ? " (current)" : ""}</span>
              {i < STEPS.length - 1 && (
                <span className="relative h-px flex-1 overflow-hidden bg-stone-200">
                  <motion.span className="absolute inset-y-0 left-0 bg-brand-700" initial={false}
                    animate={{ width: done ? "100%" : "0%" }} transition={{ duration: 0.5, ease: "easeOut" }} />
                </span>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

// ---------------------------------------------------------------- panels and fields

export const panel = "rounded-3xl border border-stone-200 bg-white p-5 shadow-xl shadow-stone-900/[0.04] sm:p-8";

export const fieldCls =
  "w-full rounded-xl border border-stone-200 bg-white px-3.5 py-2.5 text-[15px] text-stone-900 placeholder:text-stone-400 outline-none transition focus:border-brand-600 focus:bg-white focus:ring-4 focus:ring-brand-500/20 aria-[invalid=true]:border-rose-500";

export function FieldShell({ id, label, error, hint, children }: { id: string; label: string; error?: string | null; hint?: ReactNode; children: ReactNode }) {
  return (
    <div>
      <label htmlFor={id} className="mb-1.5 block text-sm font-medium text-stone-700">{label}</label>
      {children}
      {error ? (
        <motion.p id={`${id}-error`} role="alert" initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }} className="mt-1.5 text-[13px] text-rose-700">{error}</motion.p>
      ) : hint ? <p id={`${id}-hint`} className="mt-1.5 text-[13px] text-stone-500">{hint}</p> : null}
    </div>
  );
}

export function PrimaryButton({ busy, children, className = "", ...rest }: React.ButtonHTMLAttributes<HTMLButtonElement> & { busy?: boolean }) {
  return (
    <motion.button whileHover={{ y: -1 }} whileTap={{ scale: 0.98 }} disabled={busy || rest.disabled} {...(rest as object)}
      className={`group relative inline-flex items-center justify-center gap-2 rounded-xl bg-brand-700 px-5 py-3 text-[15px] font-semibold text-ivory shadow-lg shadow-brand-900/20 ring-1 ring-inset ring-black/10 transition hover:bg-brand-800 disabled:cursor-not-allowed disabled:opacity-60 ${className}`}>
      {busy && <Loader2 className="size-4 animate-spin" aria-hidden />}
      {children}
    </motion.button>
  );
}

export function GhostButton({ children, className = "", ...rest }: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button {...rest} className={`inline-flex items-center justify-center gap-1.5 rounded-xl px-4 py-3 text-sm font-medium text-stone-600 transition hover:bg-stone-100 hover:text-stone-900 disabled:opacity-50 ${className}`}>
      {children}
    </button>
  );
}

export function Alert({ children, tone = "error" }: { children: ReactNode; tone?: "error" | "info" | "success" }) {
  const cls = tone === "error" ? "border-rose-200 bg-rose-50 text-rose-800"
    : tone === "success" ? "border-brand-200 bg-brand-50 text-brand-800" : "border-brand-200 bg-brand-50 text-brand-800";
  return (
    <motion.div role={tone === "error" ? "alert" : "status"} initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }}
      className={`rounded-xl border px-3.5 py-2.5 text-sm ${cls}`}>{children}</motion.div>
  );
}

/** Email box with the college's domain fixed after it: students type only the part before "@". */
export function CollegeEmailField({ college, value, onChange, error, onBlur, autoFocus, label = "College email address" }: {
  college: OnboardCollege; value: string; onChange: (v: string) => void; error?: string | null; onBlur?: () => void; autoFocus?: boolean; label?: string;
}) {
  const id = useId();
  const domain = college.domains[0];
  return (
    <FieldShell id={id} label={label} error={error} hint={<>Use your official <span className="text-stone-700">@{domain}</span> address.</>}>
      <div className={`flex items-stretch overflow-hidden rounded-xl border bg-white transition focus-within:border-brand-600 focus-within:ring-4 focus-within:ring-brand-500/20 ${error ? "border-rose-500" : "border-stone-200"}`}>
        <input id={id} type="text" inputMode="email" autoComplete="username" autoCapitalize="none" spellCheck={false} autoFocus={autoFocus}
          value={value} onChange={(e) => onChange(e.target.value)} onBlur={onBlur} placeholder="your.name"
          aria-invalid={!!error} aria-describedby={error ? `${id}-error` : `${id}-hint`}
          className="min-w-0 flex-1 bg-transparent px-3 py-2.5 sm:px-3.5 text-[15px] text-stone-900 placeholder:text-stone-400 outline-none" />
        <span className="flex max-w-[55%] select-none items-center border-l border-stone-200 bg-stone-50 px-2 text-xs font-medium text-stone-600 sm:max-w-none sm:px-3 sm:text-sm" title="Your college's email domain">
          @{domain}
        </span>
      </div>
    </FieldShell>
  );
}

export function PasswordField({ label, value, onChange, error, autoComplete, min, avoid = [], meter = false, onBlur }: {
  label: string; value: string; onChange: (v: string) => void; error?: string | null; autoComplete: string; min: number; avoid?: string[]; meter?: boolean; onBlur?: () => void;
}) {
  const id = useId();
  const [show, setShow] = useState(false);
  const s = passwordStrength(value, min, avoid);
  const colors = ["bg-rose-500", "bg-rose-500", "bg-amber-500", "bg-brand-600", "bg-brand-700"];
  return (
    <FieldShell id={id} label={label} error={error}>
      <div className="relative">
        <input id={id} type={show ? "text" : "password"} autoComplete={autoComplete} value={value} maxLength={128}
          onChange={(e) => onChange(e.target.value)} onBlur={onBlur} aria-invalid={!!error}
          aria-describedby={error ? `${id}-error` : meter ? `${id}-strength` : undefined} className={`${fieldCls} pr-12`} />
        <button type="button" onClick={() => setShow((v) => !v)} aria-label={show ? "Hide password" : "Show password"} aria-pressed={show}
          className="absolute inset-y-0 right-1 my-1 grid w-10 place-items-center rounded-lg text-stone-500 transition hover:bg-stone-100 hover:text-stone-900">
          {show ? <EyeOff className="size-4.5" aria-hidden /> : <Eye className="size-4.5" aria-hidden />}
        </button>
      </div>
      {meter && value && (
        <div id={`${id}-strength`} className="mt-2" aria-live="polite">
          <div className="flex gap-1.5" aria-hidden>
            {[1, 2, 3, 4].map((i) => (
              <span key={i} className="h-1 flex-1 overflow-hidden rounded-full bg-stone-200">
                <motion.span className={`block h-full ${colors[s.score]}`} initial={false} animate={{ width: s.score >= i ? "100%" : "0%" }} transition={{ duration: 0.3 }} />
              </span>
            ))}
          </div>
          <p className="mt-1.5 text-[13px] text-stone-500">
            Strength: <span className="font-medium text-stone-700">{s.label}</span>{s.tips[0] ? ` · ${s.tips[0]}` : ""}
          </p>
        </div>
      )}
    </FieldShell>
  );
}

// ---------------------------------------------------------------- college card

export function CollegeLogo({ college, size = "size-14" }: { college: OnboardCollege; size?: string }) {
  const [broken, setBroken] = useState(false);
  if (college.logo_url && !broken) {
    return <img src={college.logo_url} alt="" onError={() => setBroken(true)} className={`${size} shrink-0 rounded-2xl bg-white object-contain p-1.5 ring-1 ring-stone-200`} />;
  }
  return (
    <span className={`${size} grid shrink-0 place-items-center rounded-2xl font-bold tracking-tight text-white ring-1 ring-inset ring-black/10 ${size === "size-10" ? "text-xs" : size === "size-7" ? "text-[9px] rounded-full" : "text-base"}`}
      style={{ background: `linear-gradient(140deg, ${college.primary_color}, color-mix(in oklab, ${college.primary_color} 45%, #0b1020))` }} aria-hidden>
      {initials(college.name)}
    </span>
  );
}

export function CollegeCard({ college, selected, onSelect, index, compact = false }: {
  college: OnboardCollege; selected: boolean; onSelect: () => void; index: number; compact?: boolean;
}) {
  const reduce = useReducedMotion();
  const glow = college.primary_color;
  return (
    <motion.button type="button" onClick={onSelect} aria-pressed={selected}
      initial={{ opacity: 0, y: reduce ? 0 : 18 }} animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.08 * index, duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
      whileHover={reduce ? undefined : { y: -4 }} whileTap={{ scale: 0.985 }}
      className={`group relative w-full overflow-hidden rounded-2xl border text-left transition-[border-color,background-color,box-shadow] duration-300 ${compact ? "p-3.5" : "p-4 pr-10 sm:p-6"} ${selected ? "border-brand-600 bg-white" : "border-stone-200 bg-white hover:border-stone-300 hover:bg-stone-50"}`}
      style={{ boxShadow: selected ? `0 0 0 1px ${glow}, 0 16px 40px -16px ${glow}66` : undefined }}>
      <span className="pointer-events-none absolute -right-16 -top-16 size-40 rounded-full opacity-0 blur-2xl transition-opacity duration-500 group-hover:opacity-25"
        style={{ background: glow, opacity: selected ? 0.2 : undefined }} aria-hidden />
      <span className={`relative flex ${compact ? "items-center gap-3" : "items-center gap-4 sm:flex-col sm:items-start"}`}>
        <CollegeLogo college={college} size={compact ? "size-10" : "size-14"} />
        <span className="min-w-0">
          <span className={`block font-display font-semibold leading-snug text-stone-900 ${compact ? "text-sm" : "text-[17px]"}`}>{college.name}</span>
          {!compact && <span className="mt-1 block text-sm text-stone-500">{college.city ?? ""}</span>}
          <span className={`inline-block rounded-full bg-stone-100 font-medium text-stone-600 ring-1 ring-stone-200 ${compact ? "mt-1 px-2 py-0.5 text-[11px]" : "mt-3 px-2.5 py-1 text-xs"}`}>@{college.domains[0]}</span>
        </span>
      </span>
      {selected && (
        <motion.span initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ type: "spring", stiffness: 500, damping: 26 }}
          className="absolute right-3 top-3 grid size-7 place-items-center rounded-full bg-brand-700 text-ivory">
          <Check className="size-4" aria-hidden />
          <span className="sr-only">Selected</span>
        </motion.span>
      )}
    </motion.button>
  );
}

// ---------------------------------------------------------------- 6-digit code

export function OtpInput({ length = 6, value, onChange, onComplete, disabled, invalid, label }: {
  length?: number; value: string; onChange: (v: string) => void; onComplete?: (v: string) => void; disabled?: boolean; invalid?: boolean; label: string;
}) {
  const refs = useRef<(HTMLInputElement | null)[]>([]);
  const digits = Array.from({ length }, (_, i) => value[i] ?? "");

  useEffect(() => {
    refs.current[Math.min(value.length, length - 1)]?.focus();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function set(next: string, focus: number) {
    const clean = next.replace(/\D/g, "").slice(0, length);
    onChange(clean);
    refs.current[Math.min(focus, length - 1)]?.focus();
    if (clean.length === length) onComplete?.(clean);
  }
  function onInput(i: number, raw: string) {
    const d = raw.replace(/\D/g, "");
    if (!d) return;
    if (d.length > 1) return set(value.slice(0, i) + d, i + d.length);     // autofill or typing fast
    const arr = digits.slice();
    arr[i] = d;
    set(arr.join("").slice(0, Math.max(value.length, i + 1)), i + 1);
  }
  function onKey(i: number, e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Backspace") {
      e.preventDefault();
      const arr = digits.slice();
      if (arr[i]) { arr[i] = ""; set(arr.join(""), i); }
      else if (i > 0) { arr[i - 1] = ""; set(arr.join(""), i - 1); }
    } else if (e.key === "ArrowLeft" && i > 0) refs.current[i - 1]?.focus();
    else if (e.key === "ArrowRight" && i < length - 1) refs.current[i + 1]?.focus();
  }
  function onPaste(e: ClipboardEvent<HTMLInputElement>) {
    const d = e.clipboardData.getData("text").replace(/\D/g, "");
    if (!d) return;
    e.preventDefault();
    set(d, d.length);
  }
  return (
    <div role="group" aria-label={label} className="flex justify-center gap-2 sm:gap-3">
      {digits.map((d, i) => (
        <input key={i} ref={(el) => { refs.current[i] = el; }} value={d} disabled={disabled}
          inputMode="numeric" pattern="[0-9]*" autoComplete={i === 0 ? "one-time-code" : "off"} maxLength={length}
          aria-label={`Digit ${i + 1} of ${length}`} aria-invalid={invalid}
          onChange={(e) => onInput(i, e.target.value)} onKeyDown={(e) => onKey(i, e)} onPaste={onPaste}
          onFocus={(e) => e.currentTarget.select()}
          className={`size-12 rounded-xl border bg-white text-center text-xl font-semibold text-stone-900 outline-none transition focus:border-brand-600 focus:ring-4 focus:ring-brand-500/25 disabled:opacity-60 sm:size-14 sm:text-2xl ${invalid ? "border-rose-500" : d ? "border-stone-400" : "border-stone-200"}`} />
      ))}
    </div>
  );
}

/** Seconds left until `until` (a Date.now()-based timestamp), ticking once a second. */
export function useCountdown(until: number) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    setNow(Date.now());
    const t = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(t);
  }, [until]);
  return Math.max(0, Math.ceil((until - now) / 1000));
}

export function SuccessCheck() {
  const reduce = useReducedMotion();
  return (
    <motion.div initial={{ scale: reduce ? 1 : 0.6, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}
      transition={{ type: "spring", stiffness: 260, damping: 20 }} className="relative mx-auto grid size-20 place-items-center">
      <motion.span className="absolute inset-0 rounded-full bg-brand-600/20" animate={reduce ? undefined : { scale: [1, 1.35, 1], opacity: [0.6, 0, 0.6] }}
        transition={{ duration: 2.4, repeat: Infinity }} aria-hidden />
      <svg viewBox="0 0 52 52" className="relative size-20" aria-hidden>
        <circle cx="26" cy="26" r="24" fill="#1d4ed8" />
        <motion.path d="M15 27l7 7 15-16" fill="none" stroke="#ffffff" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round"
          initial={{ pathLength: reduce ? 1 : 0 }} animate={{ pathLength: 1 }} transition={{ delay: 0.25, duration: 0.5, ease: "easeOut" }} />
      </svg>
    </motion.div>
  );
}
