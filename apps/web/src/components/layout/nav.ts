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
 * **Groups, and why the analyst tools moved.** These used to live only as a
 * list of links on the Profile page, which meant a signed-in analyst's primary
 * navigation showed them none of their own tools and the Dashboard route
 * duplicated the sidebar as a grid of cards to compensate. They are a second
 * *group* now, rendered only for the roles that can reach them, so one nav
 * answers "where can I go" for both audiences and the card grid is redundant.
 *
 * `minRole` mirrors the route gate in App.tsx, which mirrors the check the
 * backend already enforces. It is UX — don't show someone a door that 403s —
 * not the security boundary.
 */

import type { LucideIcon } from "lucide-react";
import {
  Activity,
  BookOpen,
  FolderArchive,
  Gauge,
  Home as HomeIcon,
  Network,
  ScanSearch,
  ShieldCheck,
  Siren,
  SlidersHorizontal,
  UserCircle,
  Radio,
} from "lucide-react";

export type NavRole = "viewer" | "analyst" | "admin" | "owner";

export interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  /** One-line description shown in the sidebar and the command palette. */
  blurb: string;
  /** Longer copy for cards / palette detail. */
  detail: string;
  /** Lowest role that may see this item. Absent means everyone. */
  minRole?: Exclude<NavRole, "viewer">;
}

export interface NavGroup {
  id: string;
  /** Shown above the group when the sidebar is expanded. */
  label: string;
  items: NavItem[];
}

export const NAV: NavItem[] = [
  {
    to: "/home",
    label: "Home",
    icon: HomeIcon,
    blurb: "Start here",
    detail: "Choose what happened and we'll guide you from there.",
  },
  {
    to: "/analyze",
    label: "Analyze",
    icon: ScanSearch,
    blurb: "Check a message, screenshot, or number",
    detail:
      "Paste a suspicious message, upload a screenshot, or verify a phone "
      + "number or UPI ID — and get a clear verdict with what to do next.",
  },
  {
    to: "/live",
    label: "Live Protection",
    icon: Activity,
    blurb: "Guidance during a live call",
    detail:
      "Watching a call as it happens — it names the danger, warns you the "
      + "moment it turns, and tells you exactly what to say.",
  },
  {
    to: "/reports",
    label: "My Reports",
    icon: FolderArchive,
    blurb: "Your saved investigations",
    detail: "Every check you've saved, ready to reopen or file with the police.",
  },
  {
    to: "/learn",
    label: "Learn",
    icon: BookOpen,
    blurb: "How these scams work",
    detail: "Plain-language guides to the scams going around and how to stay safe.",
  },
  {
    to: "/emergency",
    label: "Emergency",
    icon: Siren,
    blurb: "Get help right now",
    detail: "The helpline, the reporting portal, and a step-by-step for a scam in progress.",
  },
  {
    to: "/profile",
    label: "Profile",
    icon: UserCircle,
    blurb: "Account and settings",
    detail: "Your account, appearance, privacy and data-retention settings.",
  },
];

/** The analyst console. Same shape as NAV, gated by role. */
export const ANALYST_NAV: NavItem[] = [
  {
    to: "/dashboard",
    label: "Operations",
    icon: Gauge,
    blurb: "System state and live metrics",
    detail: "What every part of the build is doing, and what is running degraded.",
    minRole: "analyst",
  },
  {
    to: "/investigate",
    label: "Investigate",
    icon: ScanSearch,
    blurb: "Submit evidence to the agent graph",
    detail: "Submit evidence and watch each agent node complete against the real API.",
    minRole: "analyst",
  },
  {
    to: "/analyst/console",
    label: "Live console",
    icon: Radio,
    blurb: "Threat meter, twin, manipulation map",
    detail: "The full instrument view of a call in progress.",
    minRole: "analyst",
  },
  {
    to: "/intel",
    label: "Fraud intelligence",
    icon: Network,
    blurb: "Knowledge graph and hotspots",
    detail: "The fraud graph, its clusters, and the geospatial analytics over them.",
    minRole: "analyst",
  },
  {
    to: "/guardian",
    label: "Guardian",
    icon: ShieldCheck,
    blurb: "Intervention and circuit breaker",
    detail: "The intervention console — hold a payment, alert a registered contact.",
    minRole: "analyst",
  },
  {
    to: "/analyzer",
    label: "Analyzer",
    icon: SlidersHorizontal,
    blurb: "Raw detector output",
    detail: "Line-by-line detector output with the driver weights behind each score.",
    minRole: "analyst",
  },
  {
    to: "/model",
    label: "Model card",
    icon: BookOpen,
    blurb: "Architecture, training data, limits",
    detail: "Read from the running service, so it describes the model actually loaded.",
    minRole: "analyst",
  },
  {
    to: "/admin",
    label: "Administration",
    icon: UserCircle,
    blurb: "Organisations, users, audit log",
    detail: "Tenants, access control, and the audit trail across the platform.",
    minRole: "admin",
  },
];

const RANK: Record<NavRole, number> = { viewer: 0, analyst: 1, admin: 2, owner: 3 };

/**
 * The sidebar's groups for a given role. A viewer or a signed-out citizen sees
 * one group and never learns the second exists; an analyst sees both.
 */
export function navGroups(role: NavRole | undefined, authed: boolean): NavGroup[] {
  const groups: NavGroup[] = [{ id: "protect", label: "Protection", items: NAV }];
  const rank = RANK[role ?? "viewer"] ?? 0;
  if (!authed || rank < RANK.analyst) return groups;
  const items = ANALYST_NAV.filter((i) => rank >= RANK[i.minRole ?? "analyst"]);
  if (items.length) groups.push({ id: "analyst", label: "Analyst tools", items });
  return groups;
}

/** Flat list for the command palette — every destination the user can reach. */
export function navAll(role: NavRole | undefined, authed: boolean): NavItem[] {
  return navGroups(role, authed).flatMap((g) => g.items);
}
