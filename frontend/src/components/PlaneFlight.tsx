import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { CalendarDays, Lock, Mail, MapPin, PackageCheck, Phone } from "lucide-react";
import type { Finder, Kind } from "../lib/types";
import { dateLabel } from "../lib/format";
import { PlaneGlyph } from "./Brand";

const EASE = [0.22, 1, 0.36, 1] as const;

function Overlay({ children, onClick, label }: { children: React.ReactNode; onClick?: () => void; label: string }) {
  return createPortal(
    <motion.div role="dialog" aria-modal="true" aria-label={label} onClick={onClick}
      initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.25 }}
      className="fixed inset-0 z-[120] grid place-items-center overflow-hidden bg-[radial-gradient(ellipse_at_center,rgba(239,246,255,.92),rgba(224,231,255,.88))] backdrop-blur-sm dark:bg-[radial-gradient(ellipse_at_center,rgba(15,23,42,.92),rgba(2,6,23,.94))]">
      {children}
    </motion.div>,
    document.body,
  );
}

/**
 * After a report is submitted: the report sheet folds into a paper plane, which takes off
 * and flies out of the page (about 2.4 s; tap to skip; skipped for reduced motion).
 */
export function ReportFlight({ name, refCode, kind, onDone }: { name: string; refCode: string; kind: Kind; onDone: () => void }) {
  const reduce = useReducedMotion();
  const [phase, setPhase] = useState(0); // 0 sheet · 1 fold · 2 plane · 3 fly · 4 gone

  useEffect(() => {
    if (reduce) { onDone(); return; }
    const t = [[1, 550], [2, 1050], [3, 1500], [4, 2400]].map(([p, ms]) => window.setTimeout(() => setPhase(p), ms));
    return () => t.forEach(clearTimeout);
  }, [reduce, onDone]);

  useEffect(() => { if (phase === 4) onDone(); }, [phase, onDone]);
  if (reduce) return null;

  return (
    <AnimatePresence>
      {phase < 4 && (
        <Overlay onClick={onDone} label="Sending your report">
          <div className="relative grid place-items-center">
            {/* The dashed flight path, drawn as it takes off */}
            <svg className="pointer-events-none absolute left-1/2 top-1/2 h-[120vh] w-[120vw] -translate-x-[10%] -translate-y-[90%] overflow-visible" viewBox="0 0 1000 1000" preserveAspectRatio="none" aria-hidden>
              <motion.path d="M0 1000 C 250 900, 450 700, 1000 0" fill="none" stroke="#6366f1" strokeWidth="3" strokeDasharray="6 12" strokeLinecap="round" vectorEffect="non-scaling-stroke"
                initial={{ pathLength: 0, opacity: 0 }} animate={phase >= 3 ? { pathLength: 1, opacity: [0, 0.7, 0] } : {}} transition={{ duration: 0.95, ease: "easeIn" }} />
            </svg>

            {/* The report sheet, folding in */}
            <motion.div className="relative h-52 w-40 rounded-lg bg-white p-4 text-left shadow-2xl shadow-indigo-900/20 [transform-style:preserve-3d] dark:bg-stone-100"
              initial={{ scale: 0.6, opacity: 0, rotate: -6 }}
              animate={phase === 0 ? { scale: 1, opacity: 1, rotate: 0 } : phase === 1 ? { scale: 1, opacity: 1, rotate: 0 } : { scaleX: 0.08, scaleY: 0.5, opacity: 0, rotate: 0 }}
              transition={{ duration: phase >= 2 ? 0.35 : 0.45, ease: EASE }}>
              <p className="text-[10px] font-bold uppercase tracking-widest text-indigo-600">{kind === "found" ? "Found report" : "Lost report"}</p>
              <p className="mt-2 line-clamp-3 text-lg font-extrabold leading-tight text-stone-900">{name}</p>
              <p className="mt-2 font-mono text-xs text-stone-500">{refCode}</p>
              <div className="mt-4 space-y-1.5" aria-hidden>
                <span className="block h-1.5 w-full rounded bg-stone-200" /><span className="block h-1.5 w-4/5 rounded bg-stone-200" /><span className="block h-1.5 w-3/5 rounded bg-stone-200" />
              </div>
              {/* Top corners fold to the centre line, like the first folds of a paper plane */}
              <motion.span aria-hidden className="absolute left-0 top-0 h-20 w-20 origin-top-left bg-gradient-to-br from-indigo-100 to-white shadow-md [clip-path:polygon(0_0,100%_0,100%_100%)]"
                initial={{ scale: 0, opacity: 0 }} animate={phase >= 1 ? { scale: 1, opacity: 1 } : {}} transition={{ duration: 0.35, ease: EASE }} />
              <motion.span aria-hidden className="absolute right-0 top-0 h-20 w-20 origin-top-right bg-gradient-to-bl from-indigo-100 to-white shadow-md [clip-path:polygon(0_0,100%_0,0_100%)]"
                initial={{ scale: 0, opacity: 0 }} animate={phase >= 1 ? { scale: 1, opacity: 1 } : {}} transition={{ duration: 0.35, delay: 0.12, ease: EASE }} />
            </motion.div>

            {/* The plane, which then flies off the page */}
            <motion.div className="absolute grid size-28 place-items-center rounded-[2rem] bg-gradient-to-br from-sky-400 to-indigo-600 shadow-2xl shadow-indigo-900/30"
              initial={{ scale: 0, opacity: 0, rotate: -30 }}
              animate={phase < 2 ? { scale: 0, opacity: 0 }
                : phase === 2 ? { scale: 1, opacity: 1, rotate: [-30, 6, -4, 0], x: 0, y: 0 }
                : { scale: 0.5, opacity: [1, 1, 0], rotate: 18, x: "70vw", y: "-75vh" }}
              transition={phase === 3 ? { duration: 0.9, ease: [0.5, 0, 0.75, 0] } : { duration: 0.45, ease: EASE }}>
              <PlaneGlyph className="size-14" />
            </motion.div>

            <motion.p className="absolute top-full mt-10 whitespace-nowrap text-base font-bold text-indigo-900 dark:text-indigo-100"
              key={phase >= 2 ? "off" : "on"} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3 }}>
              {phase >= 3 ? "Report sent! ✈️" : phase >= 1 ? "Folding your report…" : "Report ready"}
            </motion.p>
          </div>
        </Overlay>
      )}
    </AnimatePresence>
  );
}

function Row({ icon: Icon, label, value, href }: { icon: typeof MapPin; label: string; value: string | null | undefined; href?: string }) {
  if (!value) return null;
  return (
    <div className="flex items-start gap-3">
      <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-indigo-50 text-indigo-600 dark:bg-indigo-500/15 dark:text-indigo-300"><Icon className="size-4" aria-hidden /></span>
      <span className="min-w-0"><span className="block text-xs font-medium text-stone-500">{label}</span>{href ? <a href={href} className="block break-all font-semibold text-indigo-700 underline-offset-2 hover:underline dark:text-indigo-300">{value}</a>
        : <span className="block font-semibold text-stone-900 dark:text-stone-100">{value}</span>}</span>
    </div>
  );
}

/**
 * After a claim is sent: a paper plane flies in from off the page, lands, and unfolds into a
 * letter showing who reported the item (name, role, department), where and when it was found
 * and where to pick it up. Contact details are never shown.
 */
export function ClaimFlight({ finder, itemName, onDone, approved = false }: { finder: Finder; itemName: string; onDone: () => void; approved?: boolean }) {
  const reduce = useReducedMotion();
  const [open, setOpen] = useState(!!reduce);
  const [shown, setShown] = useState(true);

  useEffect(() => {
    if (reduce) return;
    const t = window.setTimeout(() => setOpen(true), 1350);
    return () => clearTimeout(t);
  }, [reduce]);
  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === "Escape" && setShown(false);
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, []);

  const initial = finder.name.charAt(0).toUpperCase();
  const fold = (from: number, origin: string, delay: number) => ({
    style: { transformOrigin: origin, backfaceVisibility: "hidden" as const },
    initial: reduce ? false : { rotateX: from, opacity: 0 },
    animate: { rotateX: 0, opacity: 1 },
    transition: { duration: 0.55, delay, ease: EASE },
  });

  return (
    <AnimatePresence onExitComplete={onDone}>
      {shown && (
        <Overlay label={`Reported by ${finder.name}`} onClick={() => open || setOpen(true)}>
          {/* Flying in */}
          {!reduce && (
            <motion.div aria-hidden className="absolute grid size-24 place-items-center rounded-[1.75rem] bg-gradient-to-br from-sky-400 to-indigo-600 shadow-2xl shadow-indigo-900/30"
              initial={{ x: "-70vw", y: "60vh", rotate: -35, scale: 0.6 }}
              animate={open ? { scale: 0, opacity: 0, rotate: 0 } : { x: ["-70vw", "-18vw", "12vw", "0vw"], y: ["60vh", "-8vh", "6vh", "0vh"], rotate: [-35, -10, 15, 0], scale: [0.6, 1, 1.05, 1] }}
              transition={open ? { duration: 0.3 } : { duration: 1.2, ease: "easeInOut", times: [0, 0.45, 0.8, 1] }}>
              <PlaneGlyph className="size-12" />
            </motion.div>
          )}

          {/* The unfolded letter */}
          {open && (
            <motion.div onClick={(e) => e.stopPropagation()} exit={{ opacity: 0, scale: 0.95 }}
              className="relative mx-4 w-full max-w-sm [perspective:1200px]">
              <motion.div {...fold(-95, "50% 100%", 0)} className="rounded-t-3xl border border-b-0 border-indigo-100 bg-white px-6 pb-4 pt-6 text-center dark:border-stone-700 dark:bg-stone-900">
                <p className="text-xs font-bold uppercase tracking-widest text-indigo-600 dark:text-indigo-300">{approved ? "Claim approved" : "Claim sent"} for {itemName}</p>
                <p className="mt-3 text-sm font-medium text-stone-500">Found &amp; reported by</p>
                <div className="mt-2 flex items-center justify-center gap-3">
                  <span className="grid size-12 place-items-center rounded-full bg-gradient-to-br from-sky-400 to-indigo-600 text-xl font-extrabold text-white" aria-hidden>{initial}</span>
                  <span className="text-left">
                    <span className="block text-xl font-extrabold text-stone-900 dark:text-white">{finder.name}</span>
                    {(finder.role || finder.department) && (
                      <span className="block text-sm text-stone-500">{[finder.role, finder.department].filter(Boolean).join(" · ")}</span>
                    )}
                  </span>
                </div>
              </motion.div>
              <motion.div initial={reduce ? false : { scaleY: 0.2, opacity: 0 }} animate={{ scaleY: 1, opacity: 1 }} transition={{ duration: 0.4, ease: EASE }}
                className="space-y-3 border-x border-dashed border-y border-indigo-100 bg-white px-6 py-4 dark:border-stone-700 dark:bg-stone-900">
                <Row icon={MapPin} label="Found at" value={finder.found_at} />
                <Row icon={CalendarDays} label="Found on" value={dateLabel(finder.found_on ?? finder.reported_at)} />
                <Row icon={PackageCheck} label={approved ? "Pick up from" : "Pick up from (after approval)"} value={finder.pickup ?? finder.college ?? null} />
                {approved && <Row icon={Mail} label="Email" value={finder.email} href={finder.email ? `mailto:${finder.email}` : undefined} />}
                {approved && <Row icon={Phone} label="Phone" value={finder.phone} href={finder.phone ? `tel:${finder.phone}` : undefined} />}
              </motion.div>
              <motion.div {...fold(95, "50% 0%", 0.12)} className="rounded-b-3xl border border-t-0 border-indigo-100 bg-white px-6 pb-6 pt-4 shadow-2xl shadow-indigo-900/20 dark:border-stone-700 dark:bg-stone-900">
                <p className="flex items-start gap-2 text-xs text-stone-500"><Lock className="mt-0.5 size-3.5 shrink-0" aria-hidden />
                  <span>{approved
                    ? <>Staff approved your claim, so {finder.name.split(" ")[0]} shared these details. Say thanks! Collect the item with your pickup code. Ref <span className="whitespace-nowrap font-mono">{finder.ref}</span>.</>
                    : <>Contact details stay private until staff approve your claim. Then you'll see them here, with a pickup code. Ref <span className="whitespace-nowrap font-mono">{finder.ref}</span>.</>}</span></p>
                <button onClick={() => setShown(false)} autoFocus
                  className="mt-4 w-full rounded-xl bg-gradient-to-r from-sky-500 to-indigo-600 py-3 text-sm font-bold text-white shadow-lg shadow-indigo-900/20 transition hover:brightness-110 active:scale-[0.99]">
                  Continue
                </button>
              </motion.div>
            </motion.div>
          )}
        </Overlay>
      )}
    </AnimatePresence>
  );
}
