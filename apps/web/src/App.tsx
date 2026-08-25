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
const CitizenHome = lazy(() => import("@/pages/CitizenHome").then((m) => ({ default: m.CitizenHome })));
const Emergency = lazy(() => import("@/pages/Emergency").then((m) => ({ default: m.Emergency })));
const Profile = lazy(() => import("@/pages/Profile").then((m) => ({ default: m.Profile })));
const LiveProtection = lazy(() => import("@/pages/LiveProtection").then((m) => ({ default: m.LiveProtection })));
const Dashboard = lazy(() => import("@/pages/Dashboard").then((m) => ({ default: m.Dashboard })));
const LiveConsole = lazy(() => import("@/pages/LiveConsole").then((m) => ({ default: m.LiveConsole })));
const AdminDashboard = lazy(() => import("@/pages/AdminDashboard").then((m) => ({ default: m.AdminDashboard })));
const Analyzer = lazy(() => import("@/pages/Analyzer").then((m) => ({ default: m.Analyzer })));
const Guardian = lazy(() => import("@/pages/Guardian").then((m) => ({ default: m.Guardian })));
const Intel = lazy(() => import("@/pages/Intel").then((m) => ({ default: m.Intel })));
const Investigate = lazy(() => import("@/pages/Investigate").then((m) => ({ default: m.Investigate })));
const Shield = lazy(() => import("@/pages/Shield").then((m) => ({ default: m.Shield })));
const CaseBook = lazy(() => import("@/pages/CaseBook").then((m) => ({ default: m.CaseBook })));
const Knowledge = lazy(() => import("@/pages/Knowledge").then((m) => ({ default: m.Knowledge })));
const ModelCard = lazy(() => import("@/pages/ModelCard").then((m) => ({ default: m.ModelCard })));

/** Per-route document titles — the tab should say where you are, not repeat
 *  the tagline. Rendered inside BrowserRouter so useLocation is available. */
const TITLES: Record<string, string> = {
  "/": "AegisAI — Your shield against scam calls",
  "/login": "Sign in · AegisAI",
  // Citizen destinations
  "/home": "Home · AegisAI",
  "/analyze": "Analyze · AegisAI",
  "/live": "Live Protection · AegisAI",
  "/reports": "My Reports · AegisAI",
  "/learn": "Learn · AegisAI",
  "/emergency": "Emergency · AegisAI",
  "/profile": "Profile · AegisAI",
  // Analyst tools (reachable from Profile)
  "/admin": "Admin · AegisAI",
  "/dashboard": "Dashboard · AegisAI",
  "/analyst/console": "Live console (analyst) · AegisAI",
  "/investigate": "Investigate · AegisAI",
  "/intel": "Fraud intel · AegisAI",
  "/analyzer": "Analyzer (audit) · AegisAI",
  "/guardian": "Guardian · AegisAI",
  "/model": "Model card · AegisAI",
};

function RouteTitle() {
  const { pathname } = useLocation();
  useEffect(() => {
    document.title = TITLES[pathname] ?? "AegisAI";
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

/**
 * Role gate, layered on top of RequireAuth. The backend already enforces the
 * same `admin`+ requirement on every /api/auth/users and admin route, so this is
 * defence-in-depth and UX (don't show a citizen a 403), not the security
 * boundary itself. `owner` outranks `admin`, so both pass.
 */
const ROLE_RANK: Record<string, number> = { viewer: 0, analyst: 1, admin: 2, owner: 3 };
function RequireRole({ min }: { min: "analyst" | "admin" }) {
  const { authed, user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <Loading />;
  if (!authed) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  if ((ROLE_RANK[user?.role ?? "viewer"] ?? 0) < ROLE_RANK[min]) {
    return <Navigate to="/home" replace />;
  }
  return <Outlet />;
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
                {/* Citizen destinations — task-oriented, no account required.
                    The three research modules power these underneath; a person
                    never navigates between modules, only between things they
                    want to do. */}
                <Route path="/home" element={<CitizenHome />} />
                <Route path="/analyze" element={<Shield />} />
                <Route path="/live" element={<LiveProtection />} />
                <Route path="/reports" element={<CaseBook />} />
                <Route path="/learn" element={<Knowledge />} />
                <Route path="/emergency" element={<Emergency />} />
                <Route path="/profile" element={<Profile />} />

                {/* Old paths keep working — redirect to their citizen homes. */}
                <Route path="/shield" element={<Navigate to="/analyze" replace />} />
                <Route path="/console" element={<Navigate to="/analyst/console" replace />} />
                <Route path="/cases" element={<Navigate to="/reports" replace />} />
                <Route path="/knowledge" element={<Navigate to="/learn" replace />} />

                {/* Analyst tools — reachable from Profile, off the citizen nav,
                    and still behind a deliberate sign-in. */}
                <Route element={<RequireAuth />}>
                  <Route path="/dashboard" element={<Dashboard />} />
                  <Route path="/analyst/console" element={<LiveConsole />} />
                  <Route path="/investigate" element={<Investigate />} />
                  <Route path="/guardian" element={<Guardian />} />
                  <Route path="/analyzer" element={<Analyzer />} />
                  <Route path="/intel" element={<Intel />} />
                  <Route path="/model" element={<ModelCard />} />
                </Route>

                {/* Admin-only — the platform-operator dashboard. */}
                <Route element={<RequireRole min="admin" />}>
                  <Route path="/admin" element={<AdminDashboard />} />
                </Route>
                <Route path="*" element={<Navigate to="/home" replace />} />
              </Route>
            </Routes>
          </Suspense>
        </BrowserRouter>
      </AuthProvider>
    </ThemeProvider>
  );
}
