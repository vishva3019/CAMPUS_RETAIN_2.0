import { useEffect, useState } from "react";
import { NavLink, Outlet } from "react-router";
import { Bell, CreditCard, Globe2, History, LayoutDashboard, LogOut, Monitor, Moon, PackageSearch, QrCode, ScanLine, ShieldCheck, Sun, User } from "lucide-react";
import { STAFF_PERMS, useSession } from "../lib/session";
import { Assistant } from "./Assistant";
import { BrandMark } from "./Brand";
import { applyTheme, storedTheme, type ThemeChoice } from "../lib/theme";

const THEMES: { value: ThemeChoice; icon: typeof Sun; label: string }[] = [
  { value: "light", icon: Sun, label: "Light" },
  { value: "dark", icon: Moon, label: "Dark" },
  { value: "system", icon: Monitor, label: "System" },
];

function ThemeToggle() {
  const [choice, setChoice] = useState<ThemeChoice>(storedTheme);
  useEffect(() => {
    applyTheme(choice);
    if (choice !== "system") return;
    const mq = window.matchMedia?.("(prefers-color-scheme: dark)");
    const on = () => applyTheme("system");
    mq?.addEventListener?.("change", on);
    return () => mq?.removeEventListener?.("change", on);
  }, [choice]);
  const current = THEMES.find((t) => t.value === choice)!;
  const next = THEMES[(THEMES.indexOf(current) + 1) % THEMES.length];
  return (
    <button onClick={() => setChoice(next.value)} title={`Theme: ${current.label}. Switch to ${next.label}.`}
      aria-label={`Theme: ${current.label}. Switch to ${next.label}.`}
      className="rounded-full p-2 text-stone-500 hover:bg-stone-100 dark:text-stone-400 dark:hover:bg-stone-800">
      <current.icon className="size-5" aria-hidden />
    </button>
  );
}

export function Layout() {
  const { session, can } = useSession();
  const { college, user } = session;
  const isStaff = STAFF_PERMS.some(can);
  const member = !!college;
  // Main menu stays short; staff tools live in the Admin page's tool row.
  const links = [
    member && { to: "/", label: "Items", icon: PackageSearch, end: true },
    member && { to: "/activity", label: "My activity", short: "Activity", icon: User },
    member && { to: "/tags", label: "My QR tags", short: "Tags", icon: QrCode },
    member && college?.network && can("claims.submit") && { to: "/network", label: "Other colleges", short: "Network", icon: Globe2 },
    isStaff && { to: "/admin", label: "Admin", icon: LayoutDashboard },
    !isStaff && member && can("collection.verify") && { to: "/desk", label: "Pickup desk", short: "Desk", icon: ScanLine },
    can("platform.manage") && { to: "/platform", label: "Colleges", icon: ShieldCheck },
    can("platform.manage") && { to: "/platform/plans", label: "Plans", icon: CreditCard },
    can("platform.manage") && { to: "/platform/activity", label: "Activity log", short: "Log", icon: History },
  ].filter(Boolean) as { to: string; label: string; short?: string; icon: typeof Sun; end?: boolean }[];

  return (
    <div className="min-h-screen overflow-x-clip bg-ivory text-stone-900 dark:bg-stone-950 dark:text-stone-100">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[200] focus:rounded-lg focus:bg-white focus:px-4 focus:py-2">Skip to content</a>
      <header className="sticky top-0 z-40 border-b border-stone-200/80 bg-ivory/85 backdrop-blur-lg dark:border-stone-800 dark:bg-stone-950/80">
        <div className="mx-auto flex h-16 max-w-7xl items-center gap-3 px-4 sm:px-6">
          <NavLink to={college ? "/" : "/platform"} className="flex min-w-0 items-center gap-2.5">
            <BrandMark className="size-9 shrink-0 drop-shadow-sm" />
            <span className="min-w-0">
              <span className="block font-display text-[17px] font-extrabold leading-tight tracking-tight">Campus <span className="text-brand-700 dark:text-brand-400">Retain</span></span>
              <span className="block truncate text-[11px] font-medium text-stone-500">{college ? college.name : "Platform"}</span>
            </span>
          </NavLink>
          <nav className="ml-4 hidden items-center gap-1 xl:flex" aria-label="Main">
            {links.map((l) => (
              <NavLink key={l.to} to={l.to} end={l.end}
                className={({ isActive }) => `rounded-lg px-3 py-2 text-sm font-semibold ${isActive ? "bg-brand-50 text-brand-700 dark:bg-brand-500/10 dark:text-brand-300" : "text-stone-600 hover:bg-stone-100 dark:text-stone-300 dark:hover:bg-stone-800"}`}>
                {l.label}
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-1">
            {college && (
              <NavLink to="/notifications" className="relative rounded-full p-2 text-stone-500 hover:bg-stone-100 dark:text-stone-400 dark:hover:bg-stone-800"
                aria-label={session.unread ? `Notifications, ${session.unread} unread` : "Notifications"}>
                <Bell className="size-5" aria-hidden />
                {session.unread > 0 && (
                  <span className="absolute right-0.5 top-0.5 grid min-w-[18px] place-items-center rounded-full bg-rose-500 px-1 text-[10px] font-bold leading-[18px] text-white">{session.unread > 99 ? "99+" : session.unread}</span>
                )}
              </NavLink>
            )}
            <ThemeToggle />
            <span className="mx-1 hidden max-w-[180px] truncate text-xs text-stone-500 md:inline" title={user.role_label}>{user.email}</span>
            <a href="/logout" className="rounded-full p-2 text-stone-500 hover:bg-stone-100 hover:text-rose-600 dark:text-stone-400 dark:hover:bg-stone-800" aria-label="Log out" title="Log out">
              <LogOut className="size-5" aria-hidden />
            </a>
          </div>
        </div>
      </header>

      <main id="main" className="mx-auto max-w-7xl px-4 pb-28 pt-6 sm:px-6 xl:pb-12">
        <Outlet />
      </main>

      {member && <Assistant />}

      {/* Bottom tab bar on phones and tablets */}
      {links.length > 1 && (
        <nav aria-label="Main" className="fixed inset-x-0 bottom-0 z-40 border-t border-stone-200 bg-white/95 backdrop-blur pb-[env(safe-area-inset-bottom)] dark:border-stone-800 dark:bg-stone-950/95 xl:hidden">
          <div className="mx-auto flex max-w-lg justify-around">
            {links.slice(0, 5).map((l) => (
              <NavLink key={l.to} to={l.to} end={l.end}
                className={({ isActive }) => `flex min-w-0 flex-1 flex-col items-center gap-0.5 px-1 py-2 text-[10px] font-semibold ${isActive ? "text-brand-600 dark:text-brand-400" : "text-stone-500"}`}>
                <l.icon className="size-5" aria-hidden />
                <span className="truncate max-w-full">{l.short ?? l.label}</span>
              </NavLink>
            ))}
          </div>
        </nav>
      )}
    </div>
  );
}
