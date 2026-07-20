/**
 * The navigation map. One definition, consumed by the sidebar, the command
 * palette, the dashboard grid, and the mobile menu.
 *
 * Four surfaces rendering the same routes from four hand-written lists is how
 * a nav item ends up in three of them. Each entry also carries the one-line
 * description the dashboard cards and the palette both show, so the
 * explanation of what a screen does lives next to the route it describes.
 */

import type { LucideIcon } from "lucide-react";
import {
  Activity,
  BookOpen,
  LayoutDashboard,
  ScanLine,
  ShieldCheck,
  Sparkles,
} from "lucide-react";

export interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  blurb: string;
  /** Longer copy for the dashboard card. */
  detail: string;
  group: "Monitor" | "Investigate" | "Understand";
}

export const NAV: NavItem[] = [
  {
    to: "/dashboard",
    label: "Dashboard",
    icon: LayoutDashboard,
    blurb: "System state and where to go next",
    detail:
      "What is loaded, what is degraded, and every capability in one place.",
    group: "Monitor",
  },
  {
    to: "/console",
    label: "Live console",
    icon: Activity,
    blurb: "Watch a call as it happens",
    detail:
      "Transcript, threat meter, the Digital Twin forecast, and the coach — "
      + "driven by a live session or the recorded demo stream.",
    group: "Monitor",
  },
  {
    to: "/guardian",
    label: "Guardian",
    icon: ShieldCheck,
    blurb: "Intervene while it matters",
    detail:
      "Acknowledge an alert, hold a payment, or release it. The circuit "
      + "breaker that makes the score do something.",
    group: "Monitor",
  },
  {
    to: "/analyzer",
    label: "Analyzer",
    icon: ScanLine,
    blurb: "Check a message, transcript, or UPI ID",
    detail:
      "Paste or upload anything suspicious — an SMS, a call transcript, a UPI "
      + "ID, a QR payload — and get a scored verdict with its reasoning.",
    group: "Investigate",
  },
  {
    to: "/knowledge",
    label: "Knowledge base",
    icon: BookOpen,
    blurb: "The sources behind every verdict",
    detail:
      "Search the curated advisory corpus the analyzer cites. Every citation "
      + "in a result resolves to a section here.",
    group: "Understand",
  },
  {
    to: "/model",
    label: "Model card",
    icon: Sparkles,
    blurb: "What the model is, and where it is weak",
    detail:
      "Architecture, training data, split methodology, and the limitations "
      + "listed as prominently as the capabilities.",
    group: "Understand",
  },
];

export const GROUPS = ["Monitor", "Investigate", "Understand"] as const;

export const byGroup = (group: string) => NAV.filter((item) => item.group === group);
