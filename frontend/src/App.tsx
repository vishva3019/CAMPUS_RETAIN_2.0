import { lazy, Suspense } from "react";
import { BrowserRouter, Route, Routes } from "react-router";
import { ToastProvider } from "./components/Toast";
import { Onboarding } from "./onboarding/Onboarding";
import { SignIn } from "./onboarding/SignIn";

const MemberApp = lazy(() => import("./MemberApp"));

const loading = <div className="min-h-screen grid place-items-center text-sm text-stone-500" role="status">Loading…</div>;

export function App() {
  // The site root (/) shows the welcome screen; everything else lives under /app.
  if (!window.location.pathname.startsWith("/app")) return <Onboarding start="welcome" />;
  return (
    <BrowserRouter basename="/app">
      <ToastProvider>
        <Routes>
          {/* Public: no account needed */}
          <Route path="welcome" element={<Onboarding start="welcome" />} />
          <Route path="join" element={<Onboarding start="college" />} />
          <Route path="signin" element={<SignIn />} />
          <Route path="*" element={<Suspense fallback={loading}><MemberApp /></Suspense>} />
        </Routes>
      </ToastProvider>
    </BrowserRouter>
  );
}
