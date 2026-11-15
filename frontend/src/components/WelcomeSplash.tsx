import { useEffect, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { Check, Search } from "lucide-react";
import type { Session } from "../lib/types";

/** Shown once after signing in (about 5 seconds, skippable): scattered lost items drift in,
 * a magnifying glass sweeps over them, they all fly home into a check mark, then
 * "Hello, <name>!" and the dashboard is revealed. */

const ITEMS: { d: string; x: number; y: number; r: number }[] = [
  { d: '<path d="M5 10a7 7 0 0 1 14 0v10H5z"/><path d="M9 6V4h6v2M8 14h8"/>', x: -34, y: -22, r: -14 },              // backpack
  { d: '<circle cx="8" cy="15" r="4"/><path d="M11 12l8-8M16 7l2 2M14 9l2 2"/>', x: 32, y: -26, r: 18 },             // keys
  { d: '<rect x="7" y="2" width="10" height="20" rx="2"/><path d="M11 18h2"/>', x: -38, y: 18, r: 10 },               // phone
  { d: '<path d="M10 2h4v4l2 3v12H8V9l2-3z"/>', x: 36, y: 20, r: -12 },                                                // bottle
  { d: '<rect x="3" y="6" width="18" height="14" rx="2"/><path d="M16 13h2M3 10h18"/>', x: -8, y: -36, r: 8 },        // wallet
  { d: '<rect x="3" y="5" width="18" height="14" rx="2"/><circle cx="9" cy="11" r="2"/><path d="M14 10h4M14 14h4M6 16h6"/>', x: 10, y: 34, r: -8 }, // ID card
];

export function firstName(s: Session) {
  const full = (s.user.full_name || "").trim();
  if (full) return full.split(/\s+/)[0];
  const local = s.user.email.split("@")[0].split(/[._\-+0-9]/).find(Boolean) || "there";
  return local.charAt(0).toUpperCase() + local.slice(1);
}

export function WelcomeSplash({ session, onDone }: { session: Session; onDone: () => void }) {
  const reduce = useReducedMotion();
  const [phase, setPhase] = useState(0);   // 0 drift in · 1 search · 2 found · 3 hello · 4 leave
  const name = firstName(session);
  const college = session.college?.display_name ?? "Campus Retain";

  useEffect(() => {
    const plan = reduce ? [[3, 0], [4, 1200]] : [[1, 1000], [2, 2100], [3, 2800], [4, 4600]];
    const timers = plan.map(([p, t]) => window.setTimeout(() => setPhase(p), t));
    const end = window.setTimeout(onDone, reduce ? 1500 : 5000);
    const skip = (e: KeyboardEvent) => (e.key === "Escape" || e.key === "Enter" || e.key === " ") && onDone();
    window.addEventListener("keydown", skip);
    return () => { timers.forEach(clearTimeout); clearTimeout(end); window.removeEventListener("keydown", skip); };
  }, [reduce, onDone]);

  const gathered = phase >= 2;
  return (
    <AnimatePresence>
      {phase < 4 && (
        <motion.div key="splash" role="dialog" aria-modal="true" aria-label={`Hello, ${name}. Welcome back.`}
          onClick={onDone} initial={{ opacity: 1 }} exit={{ opacity: 0, y: -40 }} transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
          className="fixed inset-0 z-[100] grid cursor-pointer place-items-center overflow-hidden bg-[radial-gradient(ellipse_at_top,#ffffff_0%,#eef3fb_45%,#dfe9f7_100%)] dark:bg-[radial-gradient(ellipse_at_top,#0f1a33_0%,#0a1224_60%,#060b17_100%)]">
          <span className="pointer-events-none absolute -left-32 -top-32 size-[30rem] rounded-full bg-brand-200/60 blur-3xl dark:bg-brand-600/20" aria-hidden />
          <span className="pointer-events-none absolute -bottom-40 -right-32 size-[30rem] rounded-full bg-cyan-200/50 blur-3xl dark:bg-cyan-500/10" aria-hidden />

          <div className="relative flex flex-col items-center px-6 text-center">
            {/* The scene: items scatter, get found, fly home */}
            <div className="relative grid size-56 place-items-center sm:size-64" aria-hidden>
              {!reduce && ITEMS.map((it, i) => (
                <motion.span key={i}
                  className="absolute grid size-12 place-items-center rounded-2xl border border-brand-100 bg-white text-brand-700 shadow-lg shadow-brand-900/10 dark:border-brand-500/20 dark:bg-stone-900 dark:text-brand-300 sm:size-14"
                  initial={{ opacity: 0, x: it.x * 14, y: it.y * 12, rotate: it.r * 2, scale: 0.6 }}
                  animate={gathered
                    ? { opacity: 0, x: 0, y: 0, rotate: 0, scale: 0.3 }
                    : { opacity: 1, x: it.x * 2.8, y: it.y * 2.8, rotate: it.r, scale: phase === 1 ? 1.08 : 1 }}
                  transition={gathered
                    ? { duration: 0.55, delay: i * 0.06, ease: [0.55, 0, 0.45, 1] }
                    : { duration: 0.9, delay: i * 0.07, ease: [0.22, 1, 0.36, 1] }}>
                  <svg viewBox="0 0 24 24" className="size-6 sm:size-7" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" dangerouslySetInnerHTML={{ __html: it.d }} />
                </motion.span>
              ))}

              {/* Magnifying glass sweeps over the items */}
              {!reduce && (
                <motion.span className="absolute grid size-20 place-items-center rounded-full border-4 border-brand-600 bg-white/40 text-brand-700 shadow-xl backdrop-blur-sm dark:bg-white/5 dark:text-brand-300"
                  initial={{ opacity: 0, x: -120, y: 60, scale: 0.6 }}
                  animate={phase === 1 ? { opacity: 1, x: [-110, 100, -40, 0], y: [60, -50, 40, 0], scale: 1 } : { opacity: 0, scale: 0.6, x: 0, y: 0 }}
                  transition={phase === 1 ? { duration: 1.1, ease: "easeInOut" } : { duration: 0.3 }}>
                  <Search className="size-8" aria-hidden />
                </motion.span>
              )}

              {/* Home: everything returned */}
              <motion.span className="absolute grid size-24 place-items-center rounded-[1.75rem] bg-brand-700 text-white shadow-2xl shadow-brand-900/30 sm:size-28"
                initial={{ scale: reduce ? 1 : 0, rotate: reduce ? 0 : -20 }}
                animate={gathered || reduce ? { scale: 1, rotate: 0 } : { scale: 0, rotate: -20 }}
                transition={{ type: "spring", stiffness: 260, damping: 16, delay: reduce ? 0 : 0.35 }}>
                <motion.span className="absolute inset-0 rounded-[1.75rem] bg-brand-500" aria-hidden
                  animate={gathered && !reduce ? { scale: [1, 1.5], opacity: [0.5, 0] } : { opacity: 0 }}
                  transition={{ duration: 1.1, delay: 0.6, repeat: 1 }} />
                <Check className="relative size-12 sm:size-14" strokeWidth={3} aria-hidden />
              </motion.span>
            </div>

            {/* Hello, name */}
            <motion.h1 className="mt-6 text-4xl font-extrabold tracking-tight text-stone-900 sm:text-6xl dark:text-white"
              initial={{ opacity: 0, y: 24 }} animate={phase >= 3 ? { opacity: 1, y: 0 } : { opacity: 0, y: 24 }}
              transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}>
              Hello, <span className="text-brand-700 dark:text-brand-400">{name}</span>!
              <motion.span className="ml-2 inline-block origin-[70%_70%]" aria-hidden
                animate={phase >= 3 && !reduce ? { rotate: [0, 18, -8, 18, 0] } : {}} transition={{ duration: 1.2, delay: 0.3 }}>👋</motion.span>
            </motion.h1>
            <motion.p className="mt-3 max-w-md text-base text-stone-600 sm:text-lg dark:text-stone-300"
              initial={{ opacity: 0, y: 14 }} animate={phase >= 3 ? { opacity: 1, y: 0 } : { opacity: 0, y: 14 }}
              transition={{ duration: 0.6, delay: 0.12, ease: [0.22, 1, 0.36, 1] }}>
              Welcome back to {college} Lost &amp; Found. Let's get things back where they belong.
            </motion.p>
            <motion.p className="mt-2 text-sm font-medium text-stone-500 sm:hidden" initial={{ opacity: 0 }} animate={{ opacity: phase >= 1 && phase < 3 ? 1 : 0 }}>
              Finding things for you…
            </motion.p>
          </div>

          {/* Progress + skip */}
          <div className="absolute inset-x-0 bottom-8 flex flex-col items-center gap-3">
            <div className="h-1 w-40 overflow-hidden rounded-full bg-brand-100 dark:bg-white/10" aria-hidden>
              <motion.div className="h-full bg-brand-600" initial={{ width: "0%" }} animate={{ width: "100%" }} transition={{ duration: reduce ? 1.4 : 4.8, ease: "linear" }} />
            </div>
            <button onClick={(e) => { e.stopPropagation(); onDone(); }} className="rounded-full px-4 py-2 text-sm font-semibold text-stone-500 hover:text-brand-700 dark:text-stone-400">
              Skip
            </button>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
