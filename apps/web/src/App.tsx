/**
 * Routes.
 *
 * Home sits inside the shell so the top bar and ⌘K palette are available
 * everywhere — including on the landing page, where the fastest thing a
 * visitor can do is jump straight to the analyzer.
 *
 * The live console used to *be* this file. It is now one route among several,
 * unchanged in behaviour: still a pure render of one `StateFrame`, still
 * animating off discrete events rather than diffing frames.
 */

import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "@/components/layout/AppShell";
import { ThemeProvider } from "@/context/ThemeContext";
import { Home } from "@/pages/Home";
import { Dashboard } from "@/pages/Dashboard";
import { LiveConsole } from "@/pages/LiveConsole";
import { Analyzer } from "@/pages/Analyzer";
import { Guardian } from "@/pages/Guardian";
import { Knowledge } from "@/pages/Knowledge";
import { ModelCard } from "@/pages/ModelCard";
import "@/styles/global.css";
import "@/styles/console.css";
import "@/styles/app.css";

export default function App() {
  return (
    <ThemeProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<AppShell />}>
            <Route path="/" element={<Home />} />
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/console" element={<LiveConsole />} />
            <Route path="/guardian" element={<Guardian />} />
            <Route path="/analyzer" element={<Analyzer />} />
            <Route path="/knowledge" element={<Knowledge />} />
            <Route path="/model" element={<ModelCard />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </ThemeProvider>
  );
}
