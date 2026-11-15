import { useEffect, useRef, useState, type FormEvent } from "react";
import { useNavigate } from "react-router";
import { AnimatePresence, motion } from "motion/react";
import { ArrowUp, Bot, ChevronRight, ImageOff, RotateCcw, X } from "lucide-react";
import { api } from "../lib/api";
import { dateLabel } from "../lib/format";
import { useSession } from "../lib/session";
import type { Item } from "../lib/types";
import { ITEM_LABELS } from "./ui";

interface Msg { role: "user" | "assistant"; content: string; items?: Item[]; mode?: "ai" | "basic" }

const STORE = "cr-assistant";
const SUGGESTIONS = ["I lost my black backpack near the library", "How do I claim an item?", "Where is my claim?", "I found something. What do I do?"];

function load(): Msg[] {
  try { return JSON.parse(sessionStorage.getItem(STORE) || "[]"); } catch { return []; }
}

/** Campus Retain AI: a chat assistant whose answers come only from this college's real
 * reports and the student's own claims. Conversation lives in this browser tab only. */
export function Assistant() {
  const { session } = useSession();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [msgs, setMsgs] = useState<Msg[]>(load);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const college = session.college;
  const ai = !!session.config.ai_enabled;

  useEffect(() => { try { sessionStorage.setItem(STORE, JSON.stringify(msgs.slice(-20))); } catch { /* private mode */ } }, [msgs]);
  useEffect(() => { if (open) { endRef.current?.scrollIntoView({ block: "end" }); setTimeout(() => inputRef.current?.focus(), 150); } }, [open, msgs, busy]);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  async function send(content: string) {
    const clean = content.trim();
    if (!clean || busy) return;
    const next: Msg[] = [...msgs, { role: "user", content: clean }];
    setMsgs(next);
    setText("");
    setBusy(true);
    setError(null);
    try {
      const r = await api.post<{ reply: string; items: Item[]; mode: "ai" | "basic" }>("/api/v1/assistant", {
        messages: next.slice(-10).map(({ role, content }) => ({ role, content })),
      });
      setMsgs((m) => [...m, { role: "assistant", content: r.reply, items: r.items, mode: r.mode }]);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    send(text);
  }

  function openItem(i: Item) {
    setOpen(false);
    navigate(`/?item=${i.id}`);
  }

  if (!college) return null;
  return (
    <>
      <AnimatePresence>
        {!open && (
          <motion.button initial={{ scale: 0.6, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0.6, opacity: 0 }}
            whileHover={{ y: -2 }} whileTap={{ scale: 0.95 }} onClick={() => setOpen(true)}
            aria-label="Open Campus Retain AI assistant"
            className="fixed bottom-24 right-4 z-40 grid size-14 place-items-center rounded-full bg-brand-700 text-ivory shadow-xl shadow-brand-900/30 ring-4 ring-white/70 xl:bottom-6 xl:right-6 dark:ring-stone-900/70">
            <Bot className="size-7" aria-hidden />
            <span className="absolute right-0.5 top-0.5 size-3.5 rounded-full border-2 border-white bg-emerald-400 dark:border-stone-900" aria-hidden />
          </motion.button>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {open && (
          <motion.section role="dialog" aria-modal="false" aria-label="Campus Retain AI assistant"
            initial={{ opacity: 0, y: 24, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 24, scale: 0.98 }}
            transition={{ type: "spring", damping: 26, stiffness: 300 }}
            className="fixed inset-x-0 bottom-0 z-50 flex h-[85dvh] flex-col overflow-hidden rounded-t-3xl border border-stone-200 bg-white shadow-2xl sm:inset-x-auto sm:bottom-6 sm:right-6 sm:h-[600px] sm:max-h-[calc(100dvh-3rem)] sm:w-[400px] sm:rounded-3xl dark:border-stone-700 dark:bg-stone-900">
            <header className="flex items-center gap-3 border-b border-stone-100 bg-brand-800 px-4 py-3 text-ivory dark:border-stone-800">
              <span className="grid size-9 place-items-center rounded-full bg-ivory/15"><Bot className="size-5" aria-hidden /></span>
              <div className="min-w-0 flex-1">
                <p className="font-display text-base font-semibold leading-tight">Campus Retain AI</p>
                <p className="truncate text-xs text-ivory/75">{ai ? "Answers from" : "Basic help for"} {college.display_name}'s real reports</p>
              </div>
              {msgs.length > 0 && (
                <button onClick={() => { setMsgs([]); setError(null); }} className="rounded-full p-2 text-ivory/80 hover:bg-ivory/10 hover:text-ivory" aria-label="Start a new conversation" title="New conversation">
                  <RotateCcw className="size-4" aria-hidden />
                </button>
              )}
              <button onClick={() => setOpen(false)} className="rounded-full p-2 text-ivory/80 hover:bg-ivory/10 hover:text-ivory" aria-label="Close assistant">
                <X className="size-5" aria-hidden />
              </button>
            </header>

            <div className="flex-1 space-y-3 overflow-y-auto bg-ivory/60 px-4 py-4 dark:bg-stone-950/40" aria-live="polite">
              <Bubble role="assistant">
                Hi{session.user.full_name ? ` ${session.user.full_name.split(" ")[0]}` : ""}! Tell me what you lost and I'll look through what's been handed in at {college.display_name}. I can also explain how reporting, claiming and pickup work, or check your claims.
              </Bubble>
              {msgs.length === 0 && (
                <div className="flex flex-wrap gap-2 pt-1">
                  {SUGGESTIONS.map((s) => (
                    <button key={s} onClick={() => send(s)} className="rounded-full border border-stone-200 bg-white px-3 py-1.5 text-left text-sm text-stone-700 hover:border-brand-500 hover:text-brand-800 dark:border-stone-700 dark:bg-stone-900 dark:text-stone-200">{s}</button>
                  ))}
                </div>
              )}
              {msgs.map((m, i) => (
                <div key={i}>
                  <Bubble role={m.role}>{m.content}</Bubble>
                  {!!m.items?.length && (
                    <ul className="mt-2 space-y-2">
                      {m.items.map((it) => (
                        <li key={it.id}>
                          <button onClick={() => openItem(it)} className="flex w-full items-center gap-3 rounded-2xl border border-stone-200 bg-white p-2 text-left transition hover:border-brand-500 dark:border-stone-700 dark:bg-stone-900">
                            {it.photos[0] ? <img src={it.photos[0]} alt="" className="size-12 shrink-0 rounded-xl object-cover" loading="lazy" />
                              : <span className="grid size-12 shrink-0 place-items-center rounded-xl bg-stone-100 text-stone-400 dark:bg-stone-800"><ImageOff className="size-5" aria-label="No photo" /></span>}
                            <span className="min-w-0 flex-1">
                              <span className="block truncate text-sm font-semibold text-stone-900 dark:text-stone-100">{it.name}</span>
                              <span className="block truncate text-xs text-stone-500">{it.location} · {dateLabel(it.occurred_on ?? it.reported_at)} · {ITEM_LABELS[it.status]}</span>
                            </span>
                            <ChevronRight className="size-4 shrink-0 text-stone-400" aria-hidden />
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              ))}
              {busy && (
                <div className="flex w-16 items-center justify-center gap-1 rounded-2xl rounded-bl-md bg-white px-3 py-3 dark:bg-stone-800" role="status" aria-label="Assistant is typing">
                  {[0, 1, 2].map((d) => <motion.span key={d} className="size-1.5 rounded-full bg-stone-400" animate={{ opacity: [0.3, 1, 0.3] }} transition={{ duration: 1, repeat: Infinity, delay: d * 0.15 }} />)}
                </div>
              )}
              {error && <p role="alert" className="rounded-xl bg-rose-50 px-3 py-2 text-sm text-rose-700 dark:bg-rose-500/10 dark:text-rose-300">{error}</p>}
              <div ref={endRef} />
            </div>

            <form onSubmit={submit} className="border-t border-stone-100 bg-white p-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] dark:border-stone-800 dark:bg-stone-900">
              <div className="flex items-end gap-2 rounded-2xl border border-stone-200 bg-white px-3 py-1.5 focus-within:border-brand-600 focus-within:ring-2 focus-within:ring-brand-500/20 dark:border-stone-700 dark:bg-stone-950">
                <label htmlFor="assistant-input" className="sr-only">Message</label>
                <textarea id="assistant-input" ref={inputRef} value={text} onChange={(e) => setText(e.target.value)} rows={1} maxLength={1000}
                  onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(text); } }}
                  placeholder="Describe what you lost, or ask a question"
                  className="max-h-28 min-h-[40px] flex-1 resize-none bg-transparent py-2 focus-visible:outline-none text-[15px] text-stone-900 placeholder:text-stone-400 outline-none dark:text-stone-100" />
                <button type="submit" disabled={!text.trim() || busy} aria-label="Send"
                  className="mb-1 grid size-9 shrink-0 place-items-center rounded-full bg-brand-700 text-ivory transition hover:bg-brand-800 disabled:opacity-40">
                  <ArrowUp className="size-4" aria-hidden />
                </button>
              </div>
              <p className="mt-1.5 text-center text-[11px] text-stone-400">The assistant can make mistakes. Staff decide every claim.</p>
            </form>
          </motion.section>
        )}
      </AnimatePresence>
    </>
  );
}

function Bubble({ role, children }: { role: "user" | "assistant"; children: React.ReactNode }) {
  return role === "user" ? (
    <div className="ml-auto w-fit max-w-[85%] whitespace-pre-line rounded-2xl rounded-br-md bg-brand-700 px-3.5 py-2.5 text-[15px] text-ivory">{children}</div>
  ) : (
    <div className="w-fit max-w-[90%] whitespace-pre-line rounded-2xl rounded-bl-md bg-white px-3.5 py-2.5 text-[15px] text-stone-800 shadow-sm dark:bg-stone-800 dark:text-stone-100">{children}</div>
  );
}
