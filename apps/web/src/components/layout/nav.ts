/**
 * The navigation map — organised around what a citizen wants to *do*, not
 * around the system's internal modules.
 *
 * One definition, consumed by the sidebar and the command palette. A citizen
 * never has to translate "should I open Analyzer or Fraud Intel?" — they think
 * "I got a suspicious message" or "someone is calling me right now", and the
 * destinations are named for exactly those intents. The three research modules
 * (RSSIE / FIGAE / CFSRP) still power everything underneath; they are simply
 * never surfaced as places a person has to navigate between.
 *
 * The analyst-facing surfaces (the raw fraud graph, the audit analyzer, the
 * live-ops dashboard, the model card) still exist and are reachable from the
 * Profile page — they are just no longer primary navigation.
 */

import type { LucideIcon } from "lucide-react";
import {
  Activity,
  BookOpen,
  FolderArchive,
  Home as HomeIcon,
  ScanSearch,
  Siren,
  UserCircle,
} from "lucide-react";

export interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  /** One-line description shown in the sidebar and the command palette. */
  blurb: string;
  /** Longer copy for cards / palette detail. */
  detail: string;
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
    blurb: "Account and tools",
    detail: "Your account, plus the analyst tools behind the citizen experience.",
  },
];
