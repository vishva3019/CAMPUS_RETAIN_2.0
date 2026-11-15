/** The public sign-up journey: Welcome -> Select College -> Student Details -> Verify Email
 * -> Account Created. Every step talks to the real /api/v1/auth endpoints. */
import { useEffect, useId, useMemo, useRef, useState, type FormEvent } from "react";
import { AnimatePresence, MotionConfig, motion, useReducedMotion } from "motion/react";
import { ArrowLeft, ArrowRight, BadgeCheck, Building2, KeyRound, Lock, Mail, PackageSearch, ShieldCheck } from "lucide-react";
import { api, ApiError } from "../lib/api";
import {
  composeEmail, emailError, loadBootstrap, localPart, mmss, nameError, passwordStrength, studentIdError,
  type Bootstrap, type CodeSent, type OnboardCollege, type SignedIn,
} from "./lib";
import {
  Alert, AuthShell, CollegeCard, CollegeEmailField, CollegeLogo, FieldShell, GhostButton, OtpInput, PasswordField,
  PrimaryButton, Progress, SuccessCheck, fieldCls, panel, useCountdown,
} from "./parts";

type Step = "welcome" | "college" | "details" | "verify" | "done";
const ORDER: Step[] = ["welcome", "college", "details", "verify", "done"];
const STORE = "cr-onboarding";

interface Details {
  full_name: string; email: string; student_id: string; department: string; year_of_study: string;
  password: string; confirm_password: string;
}
const EMPTY: Details = { full_name: "", email: "", student_id: "", department: "", year_of_study: "", password: "", confirm_password: "" };

/** Progress survives a refresh within the tab (never the passwords). */
function readStore(): { step?: Step; collegeId?: number; details?: Partial<Details>; code?: CodeSent } {
  try { return JSON.parse(sessionStorage.getItem(STORE) || "{}"); } catch { return {}; }
}
function writeStore(v: object) {
  try { sessionStorage.setItem(STORE, JSON.stringify(v)); } catch { /* private mode */ }
}

const slide = {
  initial: (dir: number) => ({ opacity: 0, x: dir * 40, filter: "blur(6px)" }),
  animate: { opacity: 1, x: 0, filter: "blur(0px)" },
  exit: (dir: number) => ({ opacity: 0, x: dir * -40, filter: "blur(6px)" }),
};

export function Onboarding({ start = "welcome" }: { start?: "welcome" | "college" }) {
  const [boot, setBoot] = useState<Bootstrap | null>(null);
  const [bootError, setBootError] = useState<string | null>(null);
  const saved = useMemo(readStore, []);
  const [step, setStep] = useState<Step>(() => (saved.step && saved.step !== "done" && saved.step !== "welcome" ? saved.step : start));
  const [dir, setDir] = useState(1);
  const [college, setCollege] = useState<OnboardCollege | null>(null);
  const [details, setDetails] = useState<Details>({ ...EMPTY, ...saved.details, password: "", confirm_password: "" });
  const [code, setCode] = useState<CodeSent | null>(saved.code ?? null);
  const [done, setDone] = useState<SignedIn | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    loadBootstrap().then((b) => {
      if (b.signed_in && b.home) return window.location.replace(b.home);
      setBoot(b);
      const c = b.colleges.find((x) => x.id === saved.collegeId) ?? null;
      setCollege(c);
      if (!c && step !== "welcome") setStep("college");
      if (step === "verify" && !saved.code) setStep(c ? "details" : "college");
    }).catch((e: Error) => setBootError(e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (step === "done") sessionStorage.removeItem(STORE);
    else writeStore({ step, collegeId: college?.id, details: { ...details, password: undefined, confirm_password: undefined }, code });
  }, [step, college, details, code]);

  function go(next: Step) {
    setDir(ORDER.indexOf(next) >= ORDER.indexOf(step) ? 1 : -1);
    setStep(next);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  const index = ORDER.indexOf(step);
  return (
    <MotionConfig reducedMotion="user">
      <AuthShell top={step !== "done" && (
        <a href="/app/signin" className="rounded-full px-3.5 py-2 text-sm font-medium text-stone-600 ring-1 ring-stone-200 transition hover:bg-stone-100 hover:text-stone-900">Sign in</a>
      )}>
        {step !== "welcome" && <Progress step={index} />}
        <div className="flex flex-1 flex-col justify-center py-8">
          {bootError ? (
            <div className={`${panel} mx-auto max-w-md text-center`}>
              <Alert>{bootError}</Alert>
              <PrimaryButton className="mt-5" onClick={() => location.reload()}>Try again</PrimaryButton>
            </div>
          ) : (
            <AnimatePresence mode="wait" custom={dir} initial={false}>
              <motion.section key={step} custom={dir} variants={slide} initial="initial" animate="animate" exit="exit"
                transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }} className="w-full">
                {step === "welcome" && <Welcome colleges={boot?.colleges ?? []} onStart={() => go("college")} />}
                {step === "college" && (
                  <CollegeStep colleges={boot?.colleges} selected={college}
                    onPick={(c) => {
                      if (c.id !== college?.id) setDetails((d) => ({ ...d, email: "" }));
                      setCollege(c);
                      window.setTimeout(() => go("details"), 420);
                    }} />
                )}
                {step === "details" && boot && college && (
                  <DetailsStep boot={boot} college={college} details={details} setDetails={setDetails} notice={notice}
                    onBack={() => { setNotice(null); go("college"); }}
                    onSent={(c) => { setNotice(null); setCode(c); go("verify"); }} />
                )}
                {step === "verify" && college && code && (
                  <VerifyStep college={college} code={code} setCode={setCode}
                    onBack={() => go("details")}
                    onRestart={(msg) => { setNotice(msg); setCode(null); go("details"); }}
                    onVerified={(s) => { setDone(s); go("done"); }} />
                )}
                {step === "done" && done && college && <DoneStep result={done} college={college} />}
              </motion.section>
            </AnimatePresence>
          )}
        </div>
      </AuthShell>
    </MotionConfig>
  );
}

// ---------------------------------------------------------------- 1. welcome

function Welcome({ colleges, onStart }: { colleges: OnboardCollege[]; onStart: () => void }) {
  const reduce = useReducedMotion();
  const rise = (delay: number) => ({ initial: { opacity: 0, y: reduce ? 0 : 16 }, animate: { opacity: 1, y: 0 }, transition: { delay, duration: 0.7, ease: [0.22, 1, 0.36, 1] as const } });
  const features = [
    { icon: PackageSearch, title: "Report & search", text: "Post what you found or lost in seconds." },
    { icon: ShieldCheck, title: "Claim with proof", text: "Staff check ownership before any handover." },
    { icon: KeyRound, title: "Collect with a code", text: "A one-time pickup code at your college desk." },
  ];
  return (
    <div className="mx-auto max-w-3xl text-center">
      {colleges.length > 0 && (
        <motion.p {...rise(0.05)} className="mx-auto inline-flex items-center gap-2 rounded-full border border-stone-200 bg-white px-3.5 py-1.5 text-xs font-medium text-stone-600">
          <span className="size-1.5 rounded-full bg-brand-600" aria-hidden />
          For students of {colleges.map((c) => c.short_name || c.name).join(", ").replace(/, ([^,]*)$/, " & $1")}
        </motion.p>
      )}
      <motion.h1 {...rise(0.15)} className="mt-6 text-balance text-4xl font-extrabold tracking-tight text-stone-900 sm:text-6xl">
        Welcome to{" "}
        <span className="text-brand-700">Campus Retain</span>
      </motion.h1>
      <motion.p {...rise(0.28)} className="mx-auto mt-5 max-w-xl text-balance text-lg font-medium text-stone-700 sm:text-xl">
        One Platform. Multiple Colleges. One Connected Campus Community.
      </motion.p>
      <motion.p {...rise(0.38)} className="mx-auto mt-4 max-w-xl text-pretty text-[15px] leading-relaxed text-stone-500 sm:text-base">
        Lost something on campus? Found something that belongs to someone else? We're here to reconnect people with their belongings.
      </motion.p>
      <motion.div {...rise(0.5)} className="mt-9 flex flex-col items-center gap-4">
        <span className="relative">
          <motion.span className="absolute -inset-2 rounded-2xl bg-brand-600/20 blur-xl" aria-hidden
            animate={reduce ? undefined : { opacity: [0.35, 0.7, 0.35] }} transition={{ duration: 3.2, repeat: Infinity }} />
          <PrimaryButton onClick={onStart} className="relative px-8 py-3.5 text-base" autoFocus>
            Get Started <ArrowRight className="size-4.5 transition-transform group-hover:translate-x-0.5" aria-hidden />
          </PrimaryButton>
        </span>
        <a href="/app/signin" className="inline-block py-2.5 text-sm text-stone-500 transition hover:text-stone-900">
          Already have an account? <span className="font-medium text-brand-700">Sign in</span>
        </a>
      </motion.div>
      <motion.ul {...rise(0.65)} className="mx-auto mt-14 grid max-w-3xl gap-3 text-left sm:grid-cols-3">
        {features.map((f) => (
          <li key={f.title} className="rounded-2xl border border-stone-200 bg-white p-4">
            <f.icon className="size-5 text-brand-700" aria-hidden />
            <p className="mt-3 text-sm font-semibold text-stone-900">{f.title}</p>
            <p className="mt-1 text-[13px] leading-relaxed text-stone-500">{f.text}</p>
          </li>
        ))}
      </motion.ul>
      {colleges.length > 0 && (
        <motion.div {...rise(0.72)} className="mt-10">
          <p className="text-xs font-semibold uppercase tracking-wider text-stone-500">Open to students of</p>
          <ul className="mt-3 flex flex-wrap justify-center gap-2">
            {colleges.map((c) => (
              <li key={c.id} className="flex items-center gap-2 rounded-full border border-stone-200 bg-white/80 py-1 pl-1 pr-3 text-sm font-medium text-stone-700">
                <CollegeLogo college={c} size="size-7" />{c.name}
              </li>
            ))}
          </ul>
        </motion.div>
      )}
      <motion.p {...rise(0.8)} className="mx-auto mt-8 flex max-w-md items-start justify-center gap-2 text-left text-[13px] text-stone-500 sm:items-center sm:text-center">
        <Lock className="mt-0.5 size-4 shrink-0 text-brand-700 sm:mt-0" aria-hidden />
        Only verified college emails can join. Your contact details are never shown to other students.
      </motion.p>
      <motion.p {...rise(0.9)} className="mt-6 text-sm font-medium tracking-wide text-stone-500">
        Your campus. Your community. Your belongings.
      </motion.p>
    </div>
  );
}

// ---------------------------------------------------------------- 2. college

function CollegeStep({ colleges, selected, onPick }: { colleges?: OnboardCollege[]; selected: OnboardCollege | null; onPick: (c: OnboardCollege) => void }) {
  return (
    <div className="mx-auto max-w-4xl">
      <div className="text-center">
        <h1 className="text-3xl font-extrabold tracking-tight text-stone-900 sm:text-4xl">Which college do you belong to?</h1>
        <p className="mt-3 text-stone-500">Select your institution to continue.</p>
      </div>
      {!colleges ? (
        <div className="mt-10 grid gap-4 sm:grid-cols-3" aria-busy="true" aria-label="Loading colleges">
          {[0, 1, 2].map((i) => <div key={i} className="h-48 animate-pulse rounded-2xl bg-stone-100" />)}
        </div>
      ) : colleges.length === 0 ? (
        <div className={`${panel} mx-auto mt-10 max-w-md text-center`}>
          <Building2 className="mx-auto size-8 text-stone-500" aria-hidden />
          <p className="mt-3 font-medium text-stone-900">No colleges are open for sign-up yet</p>
          <p className="mt-1 text-sm text-stone-500">Please check back soon.</p>
        </div>
      ) : (
        <div className={`mt-10 grid gap-4 ${colleges.length >= 3 ? "sm:grid-cols-3" : "sm:grid-cols-2"}`}>
          {colleges.map((c, i) => <CollegeCard key={c.id} college={c} index={i} selected={selected?.id === c.id} onSelect={() => onPick(c)} />)}
        </div>
      )}
      <p className="mt-8 text-center text-sm text-stone-500">
        Already registered? <a href="/app/signin" className="inline-block py-2.5 font-medium text-brand-700 hover:text-brand-800">Sign in</a>
      </p>
    </div>
  );
}

// ---------------------------------------------------------------- 3. details

type FieldKey = keyof Details;
const PARTS: { title: string; fields: FieldKey[] }[] = [
  { title: "About you", fields: ["full_name", "email"] },
  { title: "Your course", fields: ["student_id", "department", "year_of_study"] },
  { title: "Secure your account", fields: ["password", "confirm_password"] },
];

function DetailsStep({ boot, college, details, setDetails, onBack, onSent, notice }: {
  boot: Bootstrap; college: OnboardCollege; details: Details; setDetails: (fn: (d: Details) => Details) => void;
  onBack: () => void; onSent: (c: CodeSent) => void; notice: string | null;
}) {
  const [part, setPart] = useState(0);
  const [dir, setDir] = useState(1);
  const [touched, setTouched] = useState<Partial<Record<FieldKey, boolean>>>({});
  const [serverErr, setServerErr] = useState<{ field?: FieldKey; message: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [departments, setDepartments] = useState<string[]>([]);
  const deptList = useId(), nameId = useId(), sidId = useId(), deptId = useId();
  const fullEmail = composeEmail(details.email, college.domains[0]);

  useEffect(() => {
    api.get<{ items: string[] }>(`/api/v1/auth/colleges/${college.id}/departments`).then((r) => setDepartments(r.items)).catch(() => setDepartments([]));
  }, [college.id]);

  const errors: Record<FieldKey, string | null> = {
    full_name: nameError(details.full_name),
    email: emailError(fullEmail, college),
    student_id: studentIdError(details.student_id),
    department: details.department.trim().length < 2 ? "Enter your department." : null,
    year_of_study: details.year_of_study ? null : "Choose your current year of study.",
    password: passwordStrength(details.password, boot.password_min, [fullEmail.split("@")[0], details.student_id]).score < 2
      ? (details.password.length < boot.password_min ? `Use at least ${boot.password_min} characters for your password.` : "Choose a stronger password.")
      : null,
    confirm_password: !details.confirm_password ? "Type your password again." : details.confirm_password !== details.password ? "The passwords don't match." : null,
  };
  const show = (k: FieldKey) => (serverErr?.field === k ? serverErr.message : touched[k] ? errors[k] : null);
  const set = (k: FieldKey) => (v: string) => {
    setDetails((d) => ({ ...d, [k]: v }));
    if (serverErr?.field === k) setServerErr(null);
  };
  const blur = (k: FieldKey) => () => setTouched((t) => ({ ...t, [k]: true }));

  function move(to: number) {
    setDir(to > part ? 1 : -1);
    setPart(to);
  }

  async function next(e: FormEvent) {
    e.preventDefault();
    const fields = PARTS[part].fields;
    setTouched((t) => ({ ...t, ...Object.fromEntries(fields.map((f) => [f, true])) }));
    if (fields.some((f) => errors[f])) return;
    if (part < PARTS.length - 1) return move(part + 1);
    setBusy(true);
    setServerErr(null);
    try {
      const res = await api.post<CodeSent>("/api/v1/auth/register", { ...details, email: fullEmail, college_id: college.id });
      onSent(res);
    } catch (err) {
      const field = err instanceof ApiError ? (err.field as FieldKey | undefined) : undefined;
      const message = (err as Error).message;
      const at = PARTS.findIndex((p) => field && p.fields.includes(field));
      setServerErr({ field: field ?? undefined, message });
      if (at >= 0 && at !== part) move(at);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-lg">
      <div className="text-center">
        <h1 className="text-3xl font-extrabold tracking-tight text-stone-900 sm:text-4xl">Let's get you started</h1>
        <p className="mt-3 text-stone-500">Create your Campus Retain account.</p>
      </div>
      <form onSubmit={next} noValidate className={`${panel} mt-8`}>
        <div className="flex items-center gap-3 rounded-2xl border border-stone-200 bg-white p-3">
          <CollegeLogo college={college} size="size-10" />
          <div className="min-w-0 flex-1">
            <p className="text-xs text-stone-500">College</p>
            <p className="text-sm font-semibold leading-snug text-stone-900">{college.name}</p>
          </div>
          <button type="button" onClick={onBack} className="rounded-lg px-2.5 py-1.5 text-xs font-medium text-brand-700 hover:bg-stone-100">Change</button>
        </div>

        <div className="mt-6 flex items-center justify-between">
          <h2 className="font-sans text-sm font-semibold text-stone-900">{PARTS[part].title}</h2>
          <span className="text-xs text-stone-500">{part + 1} of {PARTS.length}</span>
        </div>
        <div className="mt-2 flex gap-1.5" aria-hidden>
          {PARTS.map((_, i) => <span key={i} className={`h-1 flex-1 rounded-full transition-colors duration-300 ${i <= part ? "bg-brand-400" : "bg-stone-200"}`} />)}
        </div>

        {notice && part === 0 && <div className="mt-5"><Alert tone="info">{notice}</Alert></div>}
        {serverErr && !serverErr.field && <div className="mt-5"><Alert>{serverErr.message}</Alert></div>}

        <div className="relative mt-5 overflow-hidden">
          <AnimatePresence mode="wait" custom={dir} initial={false}>
            <motion.div key={part} custom={dir} variants={slide} initial="initial" animate="animate" exit="exit" transition={{ duration: 0.3 }} className="space-y-4">
              {part === 0 && (
                <>
                  <FieldShell id={nameId} label="Full name" error={show("full_name")}>
                    <input id={nameId} className={fieldCls} autoComplete="name" autoFocus value={details.full_name} maxLength={120}
                      onChange={(e) => set("full_name")(e.target.value)} onBlur={blur("full_name")} aria-invalid={!!show("full_name")}
                      aria-describedby={show("full_name") ? `${nameId}-error` : undefined} placeholder="As on your college ID" />
                  </FieldShell>
                  <CollegeEmailField college={college} value={details.email} error={show("email")} onBlur={blur("email")}
                    onChange={(v) => set("email")(localPart(v, college))} />
                </>
              )}
              {part === 1 && (
                <>
                  <FieldShell id={sidId} label="Student ID / USN" error={show("student_id")}>
                    <input id={sidId} className={`${fieldCls} uppercase placeholder:normal-case`} autoFocus autoCapitalize="characters" spellCheck={false} value={details.student_id} maxLength={30}
                      onChange={(e) => set("student_id")(e.target.value)} onBlur={blur("student_id")} aria-invalid={!!show("student_id")}
                      aria-describedby={show("student_id") ? `${sidId}-error` : undefined} placeholder="e.g. 1MJ22CS001" />
                  </FieldShell>
                  <FieldShell id={deptId} label="Department" error={show("department")}
                    hint={departments.length ? "Pick from the list or type your department." : "For example: Computer Science and Engineering."}>
                    <input id={deptId} className={fieldCls} list={deptList} value={details.department} maxLength={120} autoComplete="off"
                      onChange={(e) => set("department")(e.target.value)} onBlur={blur("department")} aria-invalid={!!show("department")}
                      aria-describedby={show("department") ? `${deptId}-error` : `${deptId}-hint`} />
                    <datalist id={deptList}>{departments.map((d) => <option key={d} value={d} />)}</datalist>
                  </FieldShell>
                  <fieldset>
                    <legend className="mb-1.5 text-sm font-medium text-stone-700">Current year of study</legend>
                    <div className="grid grid-cols-3 gap-2 sm:grid-cols-5">
                      {boot.years.map((y) => {
                        const on = details.year_of_study === y.value;
                        return (
                          <label key={y.value} className={`relative cursor-pointer rounded-xl border px-2 py-2.5 text-center text-sm font-medium transition has-[:focus-visible]:ring-4 has-[:focus-visible]:ring-brand-500/30 ${on ? "border-brand-600 bg-brand-50 text-stone-900" : "border-stone-200 bg-white text-stone-600 hover:border-stone-300"}`}>
                            <input type="radio" name="year" value={y.value} checked={on} className="sr-only"
                              onChange={() => { set("year_of_study")(y.value); setTouched((t) => ({ ...t, year_of_study: true })); }} />
                            {y.label}
                          </label>
                        );
                      })}
                    </div>
                    {show("year_of_study") && <p role="alert" className="mt-1.5 text-[13px] text-rose-700">{show("year_of_study")}</p>}
                  </fieldset>
                </>
              )}
              {part === 2 && (
                <>
                  <PasswordField label="Password" value={details.password} onChange={set("password")} onBlur={blur("password")} error={show("password")}
                    autoComplete="new-password" min={boot.password_min} avoid={[fullEmail.split("@")[0], details.student_id]} meter />
                  <PasswordField label="Confirm password" value={details.confirm_password} onChange={set("confirm_password")} onBlur={blur("confirm_password")}
                    error={show("confirm_password")} autoComplete="new-password" min={boot.password_min} />
                  <p className="text-[13px] text-stone-500">
                    We'll send a 6-digit code to <span className="font-medium text-stone-700">{fullEmail}</span> to confirm it's you.
                  </p>
                </>
              )}
            </motion.div>
          </AnimatePresence>
        </div>

        <div className="mt-7 flex items-center justify-between gap-3">
          <GhostButton type="button" onClick={() => (part === 0 ? onBack() : move(part - 1))}>
            <ArrowLeft className="size-4" aria-hidden /> Back
          </GhostButton>
          <PrimaryButton type="submit" busy={busy}>
            {part < PARTS.length - 1 ? <>Continue <ArrowRight className="size-4" aria-hidden /></> : <>Create account <ArrowRight className="size-4" aria-hidden /></>}
          </PrimaryButton>
        </div>
      </form>
    </div>
  );
}

// ---------------------------------------------------------------- 4. verify

export function CodeEntry({ code, onSubmit, onResent, onRestart, title, extra, submitLabel = "Verify email", requireExtraValid }: {
  code: CodeSent;
  onSubmit: (otp: string) => Promise<void>;
  onResent: (c: CodeSent) => void;
  onRestart: (msg: string) => void;
  title?: React.ReactNode;
  extra?: React.ReactNode;
  submitLabel?: string;
  requireExtraValid?: () => string | null;
}) {
  const [otp, setOtp] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [expired, setExpired] = useState(false);
  const [busy, setBusy] = useState(false);
  const [info, setInfo] = useState<string | null>(null);
  const [shake, setShake] = useState(0);
  const sentAt = useRef(Date.now());
  const [resendUntil, setResendUntil] = useState(() => Date.now() + code.resend_in * 1000);
  const [expiresAt, setExpiresAt] = useState(() => Date.now() + code.expires_in * 1000);
  const resendLeft = useCountdown(resendUntil);
  const expiresLeft = useCountdown(expiresAt);

  useEffect(() => {
    sentAt.current = Date.now();
    setResendUntil(Date.now() + code.resend_in * 1000);
    setExpiresAt(Date.now() + code.expires_in * 1000);
  }, [code]);

  async function submit(value = otp) {
    if (busy) return;
    const extraErr = requireExtraValid?.();
    if (extraErr) return setError(extraErr);
    if (value.length !== 6) return setError("Enter all 6 digits.");
    setBusy(true);
    setError(null);
    setInfo(null);
    try {
      await onSubmit(value);
    } catch (err) {
      const e = err as ApiError;
      if (e.restart) return onRestart(e.message);
      setError(e.message);
      setExpired(!!e.expired);
      setShake((n) => n + 1);
      setOtp("");
    } finally {
      setBusy(false);
    }
  }

  async function resend() {
    setError(null);
    setInfo(null);
    try {
      const res = await api.post<CodeSent>("/api/v1/auth/resend");
      setExpired(false);
      setOtp("");
      setInfo("A new code is on its way. Older codes no longer work.");
      onResent(res);
    } catch (err) {
      const e = err as ApiError;
      if (e.restart) return onRestart(e.message);
      if (e.resend_in) setResendUntil(Date.now() + e.resend_in * 1000);
      setError(e.message);
    }
  }

  return (
    <form onSubmit={(e) => { e.preventDefault(); submit(); }} noValidate>
      {title}
      <motion.div key={shake} animate={shake ? { x: [0, -10, 10, -6, 6, 0] } : undefined} transition={{ duration: 0.4 }} className="mt-6">
        <OtpInput value={otp} onChange={(v) => { setOtp(v); setError(null); }} onComplete={extra ? undefined : (v) => submit(v)}
          disabled={busy} invalid={!!error} label="6-digit verification code" />
      </motion.div>
      <p className="mt-3 text-center text-[13px] text-stone-500" aria-live="polite">
        {expiresLeft > 0 && !expired ? <>Code expires in <span className="tabular-nums text-stone-700">{mmss(expiresLeft)}</span></> : "This code has expired. Ask for a new one below."}
      </p>
      {extra && <div className="mt-6 space-y-4">{extra}</div>}
      {error && <div className="mt-4"><Alert>{error}</Alert></div>}
      {info && <div className="mt-4"><Alert tone="success">{info}</Alert></div>}
      <PrimaryButton type="submit" busy={busy} className="mt-6 w-full">{submitLabel}</PrimaryButton>
      <div className="mt-4 text-center text-sm text-stone-500">
        Didn't get it? Check spam, or{" "}
        {resendLeft > 0 ? (
          <span>resend in <span className="tabular-nums text-stone-700">{mmss(resendLeft)}</span></span>
        ) : (
          <button type="button" onClick={resend} className="font-medium text-brand-700 hover:text-brand-800">send a new code</button>
        )}
      </div>
    </form>
  );
}

function VerifyStep({ college, code, setCode, onBack, onRestart, onVerified }: {
  college: OnboardCollege; code: CodeSent; setCode: (c: CodeSent) => void; onBack: () => void; onRestart: (msg: string) => void; onVerified: (s: SignedIn) => void;
}) {
  return (
    <div className="mx-auto max-w-md">
      <div className={panel}>
        <CodeEntry code={code} onResent={setCode} onRestart={onRestart}
          onSubmit={async (otp) => onVerified(await api.post<SignedIn>("/api/v1/auth/register/verify", { otp }))}
          title={
            <div className="text-center">
              <span className="mx-auto grid size-14 place-items-center rounded-2xl bg-brand-50 text-brand-700 ring-1 ring-brand-200">
                <Mail className="size-6" aria-hidden />
              </span>
              <h1 className="mt-5 text-2xl font-extrabold tracking-tight text-stone-900">Check your college inbox</h1>
              <p className="mt-2 text-sm text-stone-500">
                We sent a 6-digit code to <span className="break-all font-medium text-stone-700">{code.email}</span>.
                It confirms you're a student at {college.short_name || college.name}.
              </p>
            </div>
          } />
        <div className="mt-4 text-center">
          <GhostButton type="button" onClick={onBack} className="!py-2"><ArrowLeft className="size-4" aria-hidden /> Change my details</GhostButton>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- 5. done

function DoneStep({ result, college }: { result: SignedIn; college: OnboardCollege }) {
  const rows = [
    { label: "Name", value: result.user.full_name },
    { label: "College", value: result.college?.name ?? college.name },
    { label: "Verified email", value: result.user.email, verified: true },
  ];
  return (
    <div className="mx-auto max-w-md text-center">
      <SuccessCheck />
      <motion.h1 initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.35 }}
        className="mt-6 text-3xl font-extrabold tracking-tight text-stone-900 sm:text-4xl">You're officially connected!</motion.h1>
      <motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.5 }} className="mt-3 text-stone-500">
        Welcome to Campus Retain. Your campus community is ready.
      </motion.p>
      <motion.dl initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.6 }} className={`${panel} mt-8 divide-y divide-white/10 !p-0 text-left`}>
        {rows.map((r) => (
          <div key={r.label} className="flex items-center justify-between gap-4 px-5 py-3.5">
            <dt className="text-sm text-stone-500">{r.label}</dt>
            <dd className="flex min-w-0 items-center gap-1.5 text-sm font-medium text-stone-900">
              <span className="truncate">{r.value}</span>
              {r.verified && <BadgeCheck className="size-4 shrink-0 text-brand-600" aria-label="Verified" />}
            </dd>
          </div>
        ))}
        <div className="flex items-center gap-2 px-5 py-3.5 text-sm text-brand-800">
          <ShieldCheck className="size-4" aria-hidden /> Registration complete
        </div>
      </motion.dl>
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.75 }}>
        <PrimaryButton className="mt-8 w-full sm:w-auto sm:px-10" autoFocus onClick={() => window.location.assign(result.home)}>
          Enter My Campus <ArrowRight className="size-4" aria-hidden />
        </PrimaryButton>
      </motion.div>
    </div>
  );
}
