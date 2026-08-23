/**
 * Presentation metadata for the eight stages.
 *
 * The colour ramp walks the threat scale in canonical stage order, so a
 * transcript reads as a temperature gradient down the page — you can see the
 * call escalating without reading a word of it. This is display only; the
 * authoritative threat weights live in `ml/aegis/taxonomy.py` and reach the
 * UI through the contract.
 */

export const STAGE_ORDER = [
  "GREETING",
  "AUTHORITY_CLAIM",
  "FEAR_INDUCTION",
  "ISOLATION",
  "VERIFICATION_DEMAND",
  "PAYMENT_SETUP",
  "PAYMENT_EXECUTION",
  "BENIGN",
] as const;

export const STAGE_COLOR: Record<string, string> = {
  GREETING: "var(--calm)",
  AUTHORITY_CLAIM: "var(--watch)",
  FEAR_INDUCTION: "var(--elevated)",
  ISOLATION: "var(--high)",
  VERIFICATION_DEMAND: "var(--high)",
  PAYMENT_SETUP: "var(--critical)",
  PAYMENT_EXECUTION: "var(--critical)",
  BENIGN: "var(--ink-faint)",
};

export const STAGE_BLURB: Record<string, string> = {
  GREETING: "Opening contact. Unremarkable by design — it exists to buy time.",
  AUTHORITY_CLAIM: "Borrowing an institution's credibility. Badge numbers and case IDs offered unprompted.",
  FEAR_INDUCTION: "A manufactured crisis, severe and immediate, to replace thinking with panic.",
  ISOLATION: "Cutting off anyone who could break the spell. The most diagnostic stage in the arc.",
  VERIFICATION_DEMAND: "Extracting credentials the real institution would already hold.",
  PAYMENT_SETUP: "Reframing the transfer as safe, refundable, or official.",
  PAYMENT_EXECUTION: "Walking the victim through it keystroke by keystroke.",
  BENIGN: "Legitimate conversation. The hard-negative class, deliberately broad.",
};

export const pretty = (stage: string) =>
  stage
    .split("_")
    .map((w) => w.charAt(0) + w.slice(1).toLowerCase())
    .join(" ");

export const stageColor = (stage: string) => STAGE_COLOR[stage] ?? "var(--ink-faint)";

/** Cities the Module 2 gazetteer knows, offered in the Shield's city picker so
 *  "fraud near you" can resolve to a real hotspot. Mirrors intel/geo.py::CITIES. */
export const CITY_OPTIONS = [
  "Bengaluru", "Mysuru", "Mangaluru", "Hyderabad", "Warangal", "Chennai",
  "Coimbatore", "Madurai", "Mumbai", "Pune", "Nagpur", "Delhi", "Gurugram",
  "Noida", "Lucknow", "Jaipur", "Ahmedabad", "Surat", "Kolkata", "Patna",
  "Bhopal", "Kochi", "Visakhapatnam", "Bhubaneswar",
] as const;
