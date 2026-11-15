import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import { AnimatePresence, motion } from "motion/react";
import { CheckCircle2, XCircle } from "lucide-react";

type Tone = "success" | "error";
interface ToastItem { id: number; message: string; tone: Tone }

const ToastContext = createContext<(message: string, tone?: Tone) => void>(() => {});
let nextId = 1;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const push = useCallback((message: string, tone: Tone = "success") => {
    const id = nextId++;
    setToasts((t) => [...t, { id, message, tone }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4500);
  }, []);
  return (
    <ToastContext.Provider value={push}>
      {children}
      <div className="fixed bottom-4 inset-x-4 sm:inset-x-auto sm:right-6 sm:bottom-6 z-[100] flex flex-col gap-2 items-stretch sm:items-end" aria-live="polite">
        <AnimatePresence>
          {toasts.map((t) => (
            <motion.div
              key={t.id}
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 8 }}
              role={t.tone === "error" ? "alert" : "status"}
              className={`flex items-start gap-2 rounded-xl px-4 py-3 text-sm font-medium shadow-lg sm:max-w-sm ${
                t.tone === "error" ? "bg-rose-600 text-white" : "bg-stone-900 text-white dark:bg-white dark:text-stone-900"
              }`}
            >
              {t.tone === "error" ? <XCircle className="size-5 shrink-0" aria-hidden /> : <CheckCircle2 className="size-5 shrink-0 text-emerald-400 dark:text-emerald-600" aria-hidden />}
              <span>{t.message}</span>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </ToastContext.Provider>
  );
}

export const useToast = () => useContext(ToastContext);
