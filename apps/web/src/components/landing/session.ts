/**
 * The recorded session, as the landing uses it.
 *
 * Every figure below is read out of `src/mock/stream.json` — the same
 * 104-second digital-arrest call the live console plays — and nothing in it
 * has been rounded, smoothed or improved. That is the whole point. Four
 * sections of this page report a threat number, and a landing page that
 * invents a plausible-looking risk score is doing the exact thing the product
 * exists to detect.
 *
 * The values are transcribed as literals rather than imported from the JSON
 * because the JSON is a 48-frame stream of full `StateFrame` snapshots — about
 * 200 kB — and the landing needs eleven numbers and seven sentences out of it.
 * Shipping the whole recording to render a marketing page would be the largest
 * asset on the critical path. The trade is that these can drift from the
 * recording, so each block names the frame it came from and
 * `scripts/check-landing-session.mjs` re-derives every one of them from
 * `stream.json` and fails the build if a single value has moved.
 */

/** The threat trajectory, frame by frame — the real curve, including the two
 *  places it goes *down*. A monotonic climb would have looked better and been
 *  a lie: the score dips at t=54 because a stage transition resets part of the
 *  stage term, and that is worth showing. */
export const TRAJECTORY = [
  { t: 0, stage: "GREETING", score: 6.3, level: "CALM" },
  { t: 9, stage: "AUTHORITY_CLAIM", score: 38.7, level: "WATCH" },
  { t: 18, stage: "FEAR_INDUCTION", score: 61.6, level: "ELEVATED" },
  { t: 31.5, stage: "FEAR_INDUCTION", score: 72.0, level: "HIGH" },
  { t: 36, stage: "ISOLATION", score: 88.0, level: "HIGH" },
  { t: 54, stage: "VERIFICATION_DEMAND", score: 81.0, level: "HIGH" },
  { t: 72, stage: "PAYMENT_SETUP", score: 88.0, level: "HIGH" },
  { t: 90, stage: "PAYMENT_EXECUTION", score: 97.0, level: "CRITICAL" },
] as const;

/** What the caller actually said, at the frames the page quotes. Hinglish,
 *  verbatim, because the product's strongest measured performance is on
 *  Hinglish and sanitising the transcript into English would misrepresent
 *  both the threat and the model.
 *
 *  Each line is *contiguous* in the recording — shortened only by stopping
 *  early or starting late, never by joining two fragments that were not
 *  adjacent. Two of these were originally stitched, which reads identically
 *  and is quietly a different sentence from the one the caller said;
 *  `scripts/check-landing-session.mjs` now refuses anything that is not a
 *  substring of the transcript. */
export const UTTERANCES = [
  { t: 9, stage: "AUTHORITY_CLAIM", text: "Sir main CBI Mumbai crime branch se sub-inspector Kulkarni bol raha hoon. Badge number 7742." },
  { t: 18, stage: "FEAR_INDUCTION", text: "Sir aapke Aadhaar number par ek parcel Mumbai airport par detain hua hai. Usme 140 gram MDMA aur teen fake passport mile hain." },
  { t: 36, stage: "ISOLATION", text: "Ye investigation confidential hai. Aap kisi ko batayenge to unko bhi accused list mein daalna padega." },
  { t: 72, stage: "PAYMENT_SETUP", text: "Ab RBI ke supervised verification account mein ye funds transfer karne honge. Wahan audit hoga, clean paisa 24 ghante mein wapas aa jayega." },
] as const;

/** The frame the live-call section renders: t = 36 s, stage ISOLATION. */
export const FRAME_36 = {
  t: "00:36",
  caller: "+1-838-224-7719",
  stage: "Isolation",
  score: 88,
  level: "HIGH",
  utterance:
    "Sir ruk jaiye. Ye investigation confidential hai. Aap kisi ko batayenge to "
    + "unko bhi accused list mein daalna padega. Aapke bete ka career kharab ho jayega.",
  /** `manipulation_map` at t=36. Compliance is 0 at this frame and is shown as
   *  0 — a bar chart that quietly drops its empty series is a bar chart that
   *  cannot be used to argue the victim had not yet complied. */
  tactics: [
    { label: "Fear", weight: 1.0 },
    { label: "Authority", weight: 0.56 },
    { label: "Isolation", weight: 0.28 },
    { label: "Urgency", weight: 0 },
    { label: "Compliance", weight: 0 },
  ],
  forecast: { next: "Verification demand", inSeconds: 18, paymentInSeconds: 54 },
  coach: {
    line: "I don't discuss anything without my family present.",
    after: "Then put the phone down and go to another person in the house.",
    why: "Isolation is the step before every transfer. Breaking it ends most scams on its own.",
  },
} as const;

/** `threat.drivers` at t=36 — what actually moved the number, with the
 *  contribution each one carries. This is the risk section's evidence panel. */
export const DRIVERS = [
  { label: "Stage: Isolation", contribution: 0.72, detail: "Classifier confidence 88%" },
  { label: "Victim stress", contribution: 0.16, detail: "Coercion index 64, flat" },
  { label: "Script match", contribution: 0.13, detail: "86% similar to a known isolation script" },
] as const;

/** `trust_passport` at t=36: four checks against a claimed identity, each with
 *  the document it is citing. This is the explainability section — the point
 *  being that every line names its source. */
export const PASSPORT = {
  claimed: "CBI Mumbai Crime Branch",
  trust: 3,
  checks: [
    { name: "Number format", detail: "International VoIP prefix, not an Indian landline", source: "TRAI numbering plan" },
    { name: "Official registry", detail: "No match in the published agency contact directory", source: "agency-directory.json" },
    { name: "Caller ID consistency", detail: "Claimed agency does not operate from this circle", source: "agency-directory.json" },
    { name: "Procedure check", detail: "No Indian agency conducts arrests over video call", source: "MHA advisory 2024/cyber/11" },
  ],
} as const;

/** `number_intel` at t=0 — the first check that fires, before a word of the
 *  script has been classified. */
export const NUMBER_INTEL = {
  number: "+1-838-224-7719",
  risk: 40,
  verdict: "FAIL",
  headline: "Originates outside India (+1) while claiming an Indian agency",
  source: "scam-playbooks.md",
} as const;

/** Pretty-print a stage constant without importing the console's whole stage
 *  module into the landing bundle. */
export const prettyStage = (s: string) =>
  s.charAt(0) + s.slice(1).toLowerCase().replace(/_/g, " ");
