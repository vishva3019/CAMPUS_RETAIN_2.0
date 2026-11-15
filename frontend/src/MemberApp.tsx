import { useCallback, useState } from "react";
import { WelcomeSplash } from "./components/WelcomeSplash";
import type { ReactNode } from "react";
import { Navigate, Route, Routes } from "react-router";
import { Layout } from "./components/Layout";
import { Empty } from "./components/ui";
import { SessionProvider, STAFF_PERMS, useSession } from "./lib/session";
import { Activity } from "./pages/Activity";
import { Notifications } from "./pages/Notifications";
import { AnalyticsPage } from "./pages/Analytics";
import { AuditLog } from "./pages/AuditLog";
import { Events } from "./pages/Events";
import { Network } from "./pages/Network";
import { Plans } from "./pages/Plans";
import { Settings } from "./pages/Settings";
import { Tags } from "./pages/Tags";
import { Admin } from "./pages/Admin";
import { Browse } from "./pages/Browse";
import { CollectionPoints } from "./pages/CollectionPoints";
import { Desk } from "./pages/Desk";
import { Platform } from "./pages/Platform";
import { ShieldOff } from "lucide-react";


function Guard({ ok, children }: { ok: boolean; children: ReactNode }) {
  return ok ? <>{children}</> : <Empty icon={<ShieldOff className="size-6" aria-hidden />} title="You don't have access to this page" />;
}

function AppRoutes() {
  const { session, can } = useSession();
  const member = !!session.college;
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={member ? <Browse /> : <Navigate to="/platform" replace />} />
        <Route path="activity" element={<Guard ok={member}><Activity /></Guard>} />
        <Route path="notifications" element={<Guard ok={member}><Notifications /></Guard>} />
        <Route path="admin" element={<Guard ok={member && STAFF_PERMS.some(can)}><Admin /></Guard>} />
        <Route path="admin/collection-points" element={<Guard ok={member && can("college.settings")}><CollectionPoints /></Guard>} />
        <Route path="desk" element={<Guard ok={member && can("collection.verify")}><Desk /></Guard>} />
        <Route path="tags" element={<Guard ok={member}><Tags /></Guard>} />
        <Route path="events" element={<Guard ok={member}><Events /></Guard>} />
        <Route path="network" element={<Guard ok={member && can("claims.submit")}><Network /></Guard>} />
        <Route path="admin/settings" element={<Guard ok={member && can("college.settings")}><Settings /></Guard>} />
        <Route path="admin/analytics" element={<Guard ok={member && can("analytics.view")}><AnalyticsPage /></Guard>} />
        <Route path="admin/activity" element={<Guard ok={member && can("audit.view")}><AuditLog /></Guard>} />
        <Route path="platform" element={<Guard ok={can("platform.manage")}><Platform /></Guard>} />
        <Route path="platform/plans" element={<Guard ok={can("platform.manage")}><Plans /></Guard>} />
        <Route path="platform/activity" element={<Guard ok={can("platform.manage") && can("audit.view")}><AuditLog platform /></Guard>} />
        <Route path="*" element={<Empty icon={<ShieldOff className="size-6" aria-hidden />} title="Page not found" />} />
      </Route>
    </Routes>
  );
}

/** Everything behind sign-in. Loaded on demand, so the public welcome and sign-in
 * screens stay small and fast. */
function Greeting() {
  const { session } = useSession();
  const [show, setShow] = useState(!!session.greet);
  const done = useCallback(() => setShow(false), []);
  return show ? <WelcomeSplash session={session} onDone={done} /> : null;
}

export default function MemberApp() {
  return (
    <SessionProvider>
      <AppRoutes />
      <Greeting />
    </SessionProvider>
  );
}
