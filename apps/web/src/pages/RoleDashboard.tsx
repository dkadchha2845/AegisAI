/**
 * `/dashboard` — one route, the right dashboard for whoever asked.
 *
 * §23 asks for four role dashboards and then says, in the same breath, "do not
 * create unnecessary duplicate dashboards … reuse components where possible".
 * Both are satisfied by making the *route* the constant and the *content* the
 * variable: `/dashboard` renders the citizen's view for a citizen and the
 * operations view for an investigator, and `/police/dashboard`,
 * `/research/dashboard` and `/admin/dashboard` are named entrances to the same
 * three components — so a bookmark, a link in an email and the post-sign-in
 * redirect all land somewhere that exists.
 *
 * The operations dashboard (`Dashboard.tsx`) and the administration console
 * (`AdminDashboard.tsx`) already existed and are reused unchanged. Only the
 * citizen and the researcher needed a surface of their own, because neither had
 * one and neither may see the two that existed.
 */

import { lazy, Suspense } from "react";
import { useAuth } from "@/context/AuthContext";

const Dashboard = lazy(() =>
  import("@/pages/Dashboard").then((m) => ({ default: m.Dashboard })),
);
const AdminDashboard = lazy(() =>
  import("@/pages/AdminDashboard").then((m) => ({ default: m.AdminDashboard })),
);
const CitizenDashboard = lazy(() =>
  import("@/pages/CitizenDashboard").then((m) => ({ default: m.CitizenDashboard })),
);
const ResearchDashboard = lazy(() =>
  import("@/pages/ResearchDashboard").then((m) => ({ default: m.ResearchDashboard })),
);

function Loading() {
  return (
    <div className="routeloading" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" /> Loading…
    </div>
  );
}

/**
 * Chosen by capability, not by role name.
 *
 * A list of role names here would have to be revisited every time a role is
 * added. "Can this identity read the organisation's case book" is the question
 * that actually decides which dashboard is useful to them, and it keeps
 * answering correctly for a role invented next month.
 */
export function RoleDashboard() {
  const auth = useAuth();
  if (auth.loading) return <Loading />;

  const view = auth.can("USER_MANAGE")
    ? "admin"
    : auth.can("INVESTIGATION_READ_ALL")
      ? "operations"
      : auth.can("RESEARCH_READ")
        ? "research"
        : "citizen";

  return (
    <Suspense fallback={<Loading />}>
      {view === "admin" && <AdminDashboard />}
      {view === "operations" && <Dashboard />}
      {view === "research" && <ResearchDashboard />}
      {view === "citizen" && <CitizenDashboard />}
    </Suspense>
  );
}
