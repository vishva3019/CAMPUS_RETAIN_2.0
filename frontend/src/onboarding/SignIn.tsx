/** Sign in for returning students and college staff: pick the college, then the college
 * email (domain fixed) and password. Also handles one-time email confirmation for older
 * accounts and the forgot-password flow. */
import { useEffect, useId, useState, type FormEvent } from "react";
import { AnimatePresence, MotionConfig, motion } from "motion/react";
import { ArrowLeft, ArrowRight, KeyRound, LogIn, MailCheck } from "lucide-react";
import { api, ApiError } from "../lib/api";
import { composeEmail, emailError, loadBootstrap, localPart, type Bootstrap, type CodeSent, type OnboardCollege, type SignedIn } from "./lib";
import { CodeEntry } from "./Onboarding";
import { Alert, AuthShell, CollegeCard, CollegeEmailField, GhostButton, PasswordField, PrimaryButton, panel } from "./parts";

type Mode = "signin" | "verify" | "forgot" | "reset";

export function SignIn() {
  const params = new URLSearchParams(window.location.search);
  const [boot, setBoot] = useState<Bootstrap | null>(null);
  const [bootError, setBootError] = useState<string | null>(null);
  const [college, setCollege] = useState<OnboardCollege | null>(null);
  const [mode, setMode] = useState<Mode>("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(false);
  const [touched, setTouched] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [code, setCode] = useState<CodeSent | null>(null);
  const [newPw, setNewPw] = useState("");
  const [confirmPw, setConfirmPw] = useState("");
  const rememberId = useId();

  useEffect(() => {
    loadBootstrap().then((b) => {
      if (b.signed_in && b.home) return window.location.replace(b.home);
      setBoot(b);
      const wanted = params.get("college");
      setCollege(b.colleges.find((c) => c.slug === wanted) ?? (b.colleges.length === 1 ? b.colleges[0] : null));
    }).catch((e: Error) => setBootError(e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const full = college ? composeEmail(email, college.domains[0]) : "";
  const emailErr = college ? emailError(full, college) : null;

  function pick(c: OnboardCollege) {
    if (c.id !== college?.id) { setEmail(""); setTouched(false); }
    setCollege(c);
    setError(null);
  }

  function finish(res: SignedIn) {
    window.location.assign(res.home);
  }

  async function signIn(e: FormEvent) {
    e.preventDefault();
    setTouched(true);
    if (!college) return setError("Choose your college first.");
    if (emailErr) return;
    if (!password) return setError("Enter your password.");
    setBusy(true);
    setError(null);
    try {
      const res = await api.post<SignedIn | CodeSent>("/api/v1/auth/login", {
        college_id: college.id, email: full, password, remember, next: params.get("next") || undefined,
      });
      if (res.status === "signed_in") return finish(res);
      setCode(res);
      setMode("verify");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function sendReset(e: FormEvent) {
    e.preventDefault();
    setTouched(true);
    if (!college || emailErr) return;
    setBusy(true);
    setError(null);
    try {
      setCode(await api.post<CodeSent>("/api/v1/auth/forgot", { college_id: college.id, email: full }));
      setNewPw("");
      setConfirmPw("");
      setMode("reset");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function restart(msg: string) {
    setMode("signin");
    setCode(null);
    setNotice(null);
    setError(msg);
  }

  const heading: Record<Mode, { title: string; sub: string }> = {
    signin: { title: "Welcome back", sub: "Sign in to your Campus Retain account." },
    verify: { title: "Confirm your email", sub: "One quick step before you continue." },
    forgot: { title: "Reset your password", sub: "We'll email you a 6-digit code." },
    reset: { title: "Choose a new password", sub: "Enter the code we emailed you." },
  };

  return (
    <MotionConfig reducedMotion="user">
      <AuthShell top={<a href="/app/join" className="rounded-full px-3.5 py-2 text-sm font-medium text-stone-600 ring-1 ring-stone-200 transition hover:bg-stone-100 hover:text-stone-900">Create account</a>}>
        <div className="flex flex-1 flex-col items-center justify-center py-10">
          <div className="w-full max-w-md">
            <motion.div key={mode} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }} className="text-center">
              <h1 className="text-3xl font-extrabold tracking-tight text-stone-900">{heading[mode].title}</h1>
              <p className="mt-2 text-stone-500">{heading[mode].sub}</p>
            </motion.div>
            <div className={`${panel} mt-8`}>
              {bootError ? <Alert>{bootError}</Alert> : !boot ? (
                <div className="space-y-3" aria-busy="true" aria-label="Loading">
                  {[0, 1, 2].map((i) => <div key={i} className="h-12 animate-pulse rounded-xl bg-stone-100" />)}
                </div>
              ) : (
                <AnimatePresence mode="wait" initial={false}>
                  <motion.div key={mode} initial={{ opacity: 0, x: 24 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -24 }} transition={{ duration: 0.3 }}>
                    {(mode === "signin" || mode === "forgot") && (
                      <form onSubmit={mode === "signin" ? signIn : sendReset} noValidate className="space-y-5">
                        <fieldset>
                          <legend className="mb-2 text-sm font-medium text-stone-700">Your college</legend>
                          <div className="grid gap-2">
                            {boot.colleges.map((c, i) => <CollegeCard key={c.id} compact college={c} index={i} selected={college?.id === c.id} onSelect={() => pick(c)} />)}
                          </div>
                        </fieldset>
                        {college && (
                          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} className="space-y-5">
                            <CollegeEmailField college={college} value={email} onChange={(v) => setEmail(localPart(v, college))}
                              error={touched ? emailErr : null} onBlur={() => setTouched(true)} />
                            {mode === "signin" && (
                              <>
                                <div>
                                  <PasswordField label="Password" value={password} onChange={setPassword} autoComplete="current-password" min={boot.password_min} />
                                  <div className="mt-2 text-right">
                                    <button type="button" onClick={() => { setMode("forgot"); setError(null); }} className="py-2 text-sm font-medium text-brand-700 hover:text-brand-800">Forgot password?</button>
                                  </div>
                                </div>
                                <label htmlFor={rememberId} className="flex cursor-pointer items-start gap-3 text-sm text-stone-600">
                                  <input id={rememberId} type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)}
                                    className="mt-0.5 size-4 rounded border-stone-300 bg-stone-200 accent-brand-500" />
                                  <span>Keep me signed in for {boot.remember_days} days<span className="block text-xs text-stone-500">Only on your own device. Staff accounts always sign out after a few hours.</span></span>
                                </label>
                              </>
                            )}
                          </motion.div>
                        )}
                        {notice && <Alert tone="success">{notice}</Alert>}
                        {error && <Alert>{error}</Alert>}
                        <PrimaryButton type="submit" busy={busy} disabled={!college} className="w-full">
                          {mode === "signin" ? <><LogIn className="size-4" aria-hidden /> Sign in</> : <>Send reset code <ArrowRight className="size-4" aria-hidden /></>}
                        </PrimaryButton>
                        {mode === "forgot" && (
                          <GhostButton type="button" className="w-full" onClick={() => { setMode("signin"); setError(null); }}>
                            <ArrowLeft className="size-4" aria-hidden /> Back to sign in
                          </GhostButton>
                        )}
                      </form>
                    )}
                    {mode === "verify" && code && (
                      <CodeEntry code={code} onResent={setCode} onRestart={restart} submitLabel="Confirm and sign in"
                        onSubmit={async (otp) => finish(await api.post<SignedIn>("/api/v1/auth/verify-email", { otp }))}
                        title={
                          <div className="text-center">
                            <MailCheck className="mx-auto size-8 text-brand-700" aria-hidden />
                            <p className="mt-3 text-sm text-stone-500">Your account was created before email checks. We sent a code to <span className="break-all font-medium text-stone-700">{code.email}</span>.</p>
                          </div>
                        } />
                    )}
                    {mode === "reset" && code && (
                      <CodeEntry code={code} onResent={setCode} onRestart={restart} submitLabel="Update password"
                        requireExtraValid={() => (!newPw ? "Choose a new password." : newPw !== confirmPw ? "The passwords don't match." : null)}
                        onSubmit={async (otp) => {
                          try {
                            await api.post("/api/v1/auth/reset", { otp, password: newPw, confirm_password: confirmPw });
                          } catch (err) {
                            throw err instanceof ApiError ? err : new Error("Couldn't update your password.");
                          }
                          setMode("signin");
                          setPassword("");
                          setCode(null);
                          setError(null);
                          setNotice("Password updated. Sign in with your new password.");
                        }}
                        title={
                          <div className="text-center">
                            <KeyRound className="mx-auto size-8 text-brand-700" aria-hidden />
                            <p className="mt-3 text-sm text-stone-500">If <span className="break-all font-medium text-stone-700">{code.email}</span> has an account, a code is on its way.</p>
                          </div>
                        }
                        extra={
                          <>
                            <PasswordField label="New password" value={newPw} onChange={setNewPw} autoComplete="new-password" min={boot.password_min} meter avoid={[full.split("@")[0]]} />
                            <PasswordField label="Confirm new password" value={confirmPw} onChange={setConfirmPw} autoComplete="new-password" min={boot.password_min} />
                          </>
                        } />
                    )}
                  </motion.div>
                </AnimatePresence>
              )}
            </div>
            <p className="mt-6 text-center text-sm text-stone-500">
              New to Campus Retain? <a href="/app/join" className="inline-block py-2.5 font-medium text-brand-700 hover:text-brand-800">Create an account</a>
            </p>
            <p className="mt-2 text-center text-xs text-stone-500">
              College staff without a college email, or platform admins: <a href="/admin_login" className="inline-block py-2 underline hover:text-stone-800">staff sign-in</a>
            </p>
          </div>
        </div>
      </AuthShell>
    </MotionConfig>
  );
}
