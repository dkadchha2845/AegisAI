/**
 * The navigation map — organised around what a person wants to *do*, not
 * around the system's internal modules.
 *
 * One definition, consumed by the sidebar and the command palette. A citizen
 * never has to translate "should I open Analyzer or Fraud Intel?" — they think
 * "I got a suspicious message" or "someone is calling me right now", and the
 * destinations are named for exactly those intents. The three research modules
 * (RSSIE / FIGAE / CFSRP) still power everything underneath; they are simply
 * never surfaced as places a person has to navigate between.
 *
 * **Gated by permission, not by role name.** These used to be filtered by a
 * `minRole` compared against a rank, which cannot express the two roles the
 * ladder could not: a citizen who may investigate but not read the graph, and a
 * researcher who may read metrics and no case at all. Each item now names the
 * capability the page behind it actually needs, and the answer comes from the
 * server's own grant list on `/api/auth/me`.
 *
 * It is still UX, not the boundary — don't show someone a door that 403s. The
 * route gate in `App.tsx` and the `require_permission` on the API behind it are
 * the two independent checks that matter.
 *
 * **One glyph per destination.** The icons come from `brand/icons.tsx` rather
 * than the icon library. Three pairs here used to share a picture — Analyze and
 * Investigate were both `ScanSearch`, Learn and Model card were both
 * `BookOpen`, Profile and Administration were both `UserCircle` — which makes
 * the icon column decoration and forces the reader back onto the labels.
 */

import {
  IconAdmin,
  IconAnalyze,
  IconAnalyzer,
  IconConsole,
  IconDashboard,
  IconEmergency,
  IconGraph,
  IconGuardian,
  IconHome,
  IconInvestigate,
  IconLearn,
  IconLive,
  IconModel,
  IconProfile,
  IconReports,
  IconResearch,
} from "@/components/brand/icons";
import type { AegisIcon } from "@/components/brand/icons";
import type { PermissionCode } from "@/lib/api";

export interface NavItem {
  to: string;
  label: string;
  icon: AegisIcon;
  /** One-line description shown in the sidebar and the command palette. */
  blurb: string;
  /** Longer copy for cards / palette detail. */
  detail: string;
  /** Every code must be held for this destination to appear. Absent means
   *  everyone, including a signed-out visitor. */
  needs?: PermissionCode[];
}

export interface NavGroup {
  id: string;
  /** Shown above the group when the sidebar is expanded. */
  label: string;
  items: NavItem[];
}

/** Everything a person can do about their own safety. No permission on the
 *  first six: the citizen shield is open to a visitor with no account, which
 *  the sign-in screen says out loud. */
export const NAV: NavItem[] = [
  {
    to: "/home",
    label: "Home",
    icon: IconHome,
    blurb: "Start here",
    detail: "Choose what happened and we'll guide you from there.",
  },
  {
    to: "/analyze",
    label: "Analyze",
    icon: IconAnalyze,
    blurb: "Check a message, screenshot, or number",
    detail:
      "Paste a suspicious message, upload a screenshot, or verify a phone "
      + "number or UPI ID — and get a clear verdict with what to do next.",
  },
  {
    to: "/live",
    label: "Live Protection",
    icon: IconLive,
    blurb: "Guidance during a live call",
    detail:
      "Watching a call as it happens — it names the danger, warns you the "
      + "moment it turns, and tells you exactly what to say.",
  },
  {
    to: "/reports",
    label: "My Reports",
    icon: IconReports,
    blurb: "Your saved investigations",
    detail: "Every check you've saved, ready to reopen or file with the police.",
  },
  {
    to: "/learn",
    label: "Learn",
    icon: IconLearn,
    blurb: "How these scams work",
    detail: "Plain-language guides to the scams going around and how to stay safe.",
  },
  {
    to: "/emergency",
    label: "Emergency",
    icon: IconEmergency,
    blurb: "Get help right now",
    detail: "The helpline, the reporting portal, and a step-by-step for a scam in progress.",
  },
  {
    to: "/profile",
    label: "Profile",
    icon: IconProfile,
    blurb: "Account and settings",
    detail: "Your account, password, appearance, privacy and data-retention settings.",
  },
];

/** Everyone who is signed in has a dashboard; which one they land on is
 *  decided by `RoleDashboard` from their permissions. It belongs in the group
 *  everybody sees, not in the investigator group — putting it there labelled a
 *  citizen's own dashboard "Investigator tools". */
export const DASHBOARD: NavItem = {
  to: "/dashboard",
  label: "Dashboard",
  icon: IconDashboard,
  blurb: "Your cases and what needs attention",
  detail: "What you have investigated, what is going around, and what needs you.",
};

/** The investigator's console. Gated as a whole on `GRAPH_READ`, which is the
 *  capability that separates an investigator from a citizen: entity-level
 *  intelligence about specific accounts. */
export const ANALYST_NAV: NavItem[] = [
  {
    to: "/investigate",
    label: "Investigate",
    icon: IconInvestigate,
    blurb: "Submit evidence to the agent graph",
    detail: "Submit evidence and watch each agent node complete against the real API.",
    needs: ["INVESTIGATION_CREATE", "GRAPH_READ"],
  },
  {
    to: "/analyst/console",
    label: "Live console",
    icon: IconConsole,
    blurb: "Threat meter, twin, manipulation map",
    detail: "The full instrument view of a call in progress.",
    needs: ["LIVE_SESSION_USE", "GRAPH_READ"],
  },
  {
    to: "/intel",
    label: "Fraud intelligence",
    icon: IconGraph,
    blurb: "Knowledge graph and hotspots",
    detail: "The fraud graph, its clusters, and the geospatial analytics over them.",
    needs: ["GRAPH_READ"],
  },
  {
    to: "/guardian",
    label: "Guardian",
    icon: IconGuardian,
    blurb: "Intervention and circuit breaker",
    detail: "The intervention console — hold a payment, alert a registered contact.",
    needs: ["LIVE_SESSION_USE", "GRAPH_READ"],
  },
  {
    to: "/analyzer",
    label: "Analyzer",
    icon: IconAnalyzer,
    blurb: "Raw detector output",
    detail: "Line-by-line detector output with the driver weights behind each score.",
    needs: ["GRAPH_READ"],
  },
  {
    to: "/model",
    label: "Model card",
    icon: IconModel,
    blurb: "Architecture, training data, limits",
    detail: "Read from the running service, so it describes the model actually loaded.",
    needs: ["GRAPH_READ"],
  },
];

/** Research and administration — the two surfaces that are not investigation. */
export const OVERSIGHT_NAV: NavItem[] = [
  {
    to: "/research/dashboard",
    label: "Research",
    icon: IconResearch,
    blurb: "Datasets, model evaluation, fraud trends",
    detail:
      "Aggregated statistics and measured model performance. No case-level data "
      + "and no personally identifying information.",
    needs: ["RESEARCH_READ"],
  },
  {
    to: "/admin/dashboard",
    label: "Administration",
    icon: IconAdmin,
    blurb: "Organisations, users, roles, audit log",
    detail: "Tenants, access control, and the audit trail across the platform.",
    needs: ["USER_MANAGE"],
  },
];

function visible(items: NavItem[], held: readonly string[]): NavItem[] {
  return items.filter((i) => !i.needs || i.needs.every((c) => held.includes(c)));
}

/**
 * The sidebar's groups for the permissions the current identity holds.
 *
 * A signed-out visitor sees one group and never learns the others exist. A
 * citizen sees the same one — every destination in it is open to them, and
 * nothing in the other two is. An investigator sees two; an administrator or a
 * researcher sees the third.
 */
export function navGroups(held: readonly string[], authed: boolean): NavGroup[] {
  // Signed in, the dashboard leads; signed out there is no dashboard to lead
  // with and the first thing anyone wants is Home.
  const protect = authed ? [DASHBOARD, ...NAV] : NAV;
  const groups: NavGroup[] = [{ id: "protect", label: "Protection", items: protect }];
  if (!authed) return groups;

  const analyst = visible(ANALYST_NAV, held);
  if (analyst.length) {
    groups.push({ id: "analyst", label: "Investigator tools", items: analyst });
  }
  const oversight = visible(OVERSIGHT_NAV, held);
  if (oversight.length) {
    groups.push({ id: "oversight", label: "Oversight", items: oversight });
  }
  return groups;
}

/** Flat list for the command palette — every destination the user can reach. */
export function navAll(held: readonly string[], authed: boolean): NavItem[] {
  return navGroups(held, authed).flatMap((g) => g.items);
}
