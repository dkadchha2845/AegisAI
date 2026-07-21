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

import { lazy, Suspense } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "@/components/layout/AppShell";
import { ThemeProvider } from "@/context/ThemeContext";
import { AuthProvider } from "@/context/AuthContext";
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

function Loading() {
  return (
    <div className="routeloading">
      <span className="spinner" /> Loading…
    </div>
  );
}

export default function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <BrowserRouter>
          <Suspense fallback={<Loading />}>
            <Routes>
              <Route path="/" element={<Home />} />
              <Route path="/login" element={<Login />} />
              <Route element={<AppShell />}>
                <Route path="/dashboard" element={<Dashboard />} />
                <Route path="/console" element={<LiveConsole />} />
                <Route path="/guardian" element={<Guardian />} />
                <Route path="/analyzer" element={<Analyzer />} />
                <Route path="/intel" element={<Intel />} />
                <Route path="/shield" element={<Shield />} />
                <Route path="/cases" element={<CaseBook />} />
                <Route path="/knowledge" element={<Knowledge />} />
                <Route path="/model" element={<ModelCard />} />
                <Route path="*" element={<Navigate to="/" replace />} />
              </Route>
            </Routes>
          </Suspense>
        </BrowserRouter>
      </AuthProvider>
    </ThemeProvider>
  );
}
