/**
 * Routes.
 *
 * The landing (`/`) and the login screen sit *outside* the AppShell — they are
 * full-bleed surfaces with their own chrome, not documents inside the console.
 * Everything else renders inside the shell so the top bar, sidebar, and ⌘K
 * palette are available across the product.
 *
 * Every page below the shell is lazy-loaded. The landing's critical path no
 * longer has to ship the three.js console, the GSAP-heavy analyzer, and the
 * intel graph up front — each route's payload arrives when it is first visited,
 * behind a Suspense fallback. The live console is still a pure render of one
 * `StateFrame`, animating off discrete events rather than diffing frames.
 */

import { lazy, Suspense, useEffect, type ReactNode } from "react";
import { BrowserRouter, Navigate, Outlet, Route, Routes, useLocation } from "react-router-dom";
import { AppShell } from "@/components/layout/AppShell";
import { ThemeProvider } from "@/context/ThemeContext";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import { Home } from "@/pages/Home";
import "@/styles/global.css";
import "@/styles/console.css";
import "@/styles/app.css";
import "@/styles/modules.css";

const Login = lazy(() => import("@/pages/Login").then((m) => ({ default: m.Login })));
const Dashboard = lazy(() => import("@/pages/Dashboard").then((m) => ({ default: m.Dashboard })));
const LiveConsole = lazy(() => import("@/pages/LiveConsole").then((m) => ({ default: m.LiveConsole })));
const Analyzer = lazy(() => import("@/pages/Analyzer").then((m) => ({ default: m.Analyzer })));
const Guardian = lazy(() => import("@/pages/Guardian").then((m) => ({ default: m.Guardian })));
const Intel = lazy(() => import("@/pages/Intel").then((m) => ({ default: m.Intel })));
const Shield = lazy(() => import("@/pages/Shield").then((m) => ({ default: m.Shield })));
const CaseBook = lazy(() => import("@/pages/CaseBook").then((m) => ({ default: m.CaseBook })));
const Knowledge = lazy(() => import("@/pages/Knowledge").then((m) => ({ default: m.Knowledge })));
const ModelCard = lazy(() => import("@/pages/ModelCard").then((m) => ({ default: m.ModelCard })));

/** Per-route document titles — the tab should say where you are, not repeat
 *  the tagline. Rendered inside BrowserRouter so useLocation is available. */
const TITLES: Record<string, string> = {
  "/": "KAVACH — AI for Digital Public Safety",
  "/login": "Sign in · KAVACH",
  "/dashboard": "Dashboard · KAVACH",
  "/console": "Live console · KAVACH",
  "/guardian": "Guardian · KAVACH",
  "/analyzer": "Analyzer · KAVACH",
  "/intel": "Fraud intel · KAVACH",
  "/shield": "Citizen shield · KAVACH",
  "/cases": "Case book · KAVACH",
  "/knowledge": "Knowledge base · KAVACH",
  "/model": "Model card · KAVACH",
};

function RouteTitle() {
  const { pathname } = useLocation();
  useEffect(() => {
    document.title = TITLES[pathname] ?? "KAVACH";
  }, [pathname]);
  return null;
}

function Loading() {
  return (
    <div className="routeloading">
      <span className="spinner" /> Loading…
    </div>
  );
}

/**
 * Route gate. The console (analyst tools) is reachable only after a deliberate
 * sign-in in this browser — even though the demo server runs open — so loading
 * the site lands on the public landing, and "Enter console" routes through
 * /login first. The citizen shield stays outside this gate: citizens have no
 * account, which the login screen says out loud.
 *
 * `authed` is a client fact (a token is held), not the server's open-mode
 * identity, so this never traps a real deployment either: enforce auth and the
 * same gate applies unchanged.
 */
function RequireAuth({ children }: { children?: ReactNode }) {
  const { authed, loading } = useAuth();
  const location = useLocation();
  if (loading) return <Loading />;
  if (!authed) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return <>{children ?? <Outlet />}</>;
}

export default function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <BrowserRouter>
          <RouteTitle />
          <Suspense fallback={<Loading />}>
            <Routes>
              <Route path="/" element={<Home />} />
              <Route path="/login" element={<Login />} />
              <Route element={<AppShell />}>
                {/* Public inside the shell — the citizen fraud shield needs no
                    account. */}
                <Route path="/shield" element={<Shield />} />
                {/* Gated — the analyst console requires a sign-in. */}
                <Route element={<RequireAuth />}>
                  <Route path="/dashboard" element={<Dashboard />} />
                  <Route path="/console" element={<LiveConsole />} />
                  <Route path="/guardian" element={<Guardian />} />
                  <Route path="/analyzer" element={<Analyzer />} />
                  <Route path="/intel" element={<Intel />} />
                  <Route path="/cases" element={<CaseBook />} />
                  <Route path="/knowledge" element={<Knowledge />} />
                  <Route path="/model" element={<ModelCard />} />
                </Route>
                <Route path="*" element={<Navigate to="/" replace />} />
              </Route>
            </Routes>
          </Suspense>
        </BrowserRouter>
      </AuthProvider>
    </ThemeProvider>
  );
}
