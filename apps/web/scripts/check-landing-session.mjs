/**
 * The landing page quotes a recorded session. This proves it still does.
 *
 * `src/components/landing/session.ts` transcribes eleven numbers and seven
 * sentences out of `src/mock/stream.json` — the 104-second digital-arrest
 * recording the live console plays — as literals, because shipping the whole
 * 48-frame stream to render a marketing page would put the largest asset on
 * the site on its critical path.
 *
 * That trade has one cost: the literals can drift from the recording. A
 * landing page that claims a number came from a real session and then quietly
 * disagrees with it is exactly the failure the page spends twelve sections
 * arguing against, so it is worth a gate rather than a convention.
 *
 * This re-derives every transcribed value from `stream.json` and exits
 * non-zero on the first disagreement. It runs as part of `make typecheck`.
 *
 *   node scripts/check-landing-session.mjs
 */

import { readFile, writeFile, unlink } from "node:fs/promises";
import { fileURLToPath, pathToFileURL } from "node:url";
import { dirname, resolve } from "node:path";
import { tmpdir } from "node:os";

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, "..");

/** Load `session.ts` as a module.
 *
 *  It is TypeScript only in the two ways listed below, so stripping them is
 *  cheaper and far less brittle than adding a TypeScript loader to a script
 *  whose whole job is to be trivially runnable. If the file ever grows real
 *  type syntax, the import throws and this check fails loudly rather than
 *  silently passing. */
async function loadSession() {
  const src = await readFile(resolve(root, "src/components/landing/session.ts"), "utf8");
  const js = src
    .replaceAll(" as const", "")
    .replace("(s: string)", "(s)");
  const tmp = resolve(tmpdir(), `aegis-session-${process.pid}.mjs`);
  await writeFile(tmp, js);
  try {
    return await import(pathToFileURL(tmp).href);
  } finally {
    await unlink(tmp).catch(() => {});
  }
}

const problems = [];
/** Stable JSON: object key order is an artefact of how each side was
 *  authored, not a fact about the recording, and comparing raw
 *  `JSON.stringify` output makes `{fear, authority}` differ from
 *  `{authority, fear}` when the two agree about every value. */
const stable = (v) =>
  JSON.stringify(v, (_k, x) =>
    x && typeof x === "object" && !Array.isArray(x)
      ? Object.fromEntries(Object.keys(x).sort().map((k) => [k, x[k]]))
      : x,
  );
const check = (what, got, want) => {
  const a = stable(got);
  const b = stable(want);
  if (a !== b) problems.push(`${what}\n    landing: ${a}\n    recording: ${b}`);
};

const stream = JSON.parse(await readFile(resolve(root, "src/mock/stream.json"), "utf8"));
const frames = Object.values(stream).filter((f) => f && f.type === "state");
const at = (t) => {
  const f = frames.find((x) => x.t === t);
  if (!f) throw new Error(`stream.json has no state frame at t=${t}`);
  return f;
};

const S = await loadSession();

/* --- the trajectory ---------------------------------------------------- */
for (const point of S.TRAJECTORY) {
  const f = at(point.t);
  check(`TRAJECTORY t=${point.t} stage`, point.stage, f.stage.current);
  check(`TRAJECTORY t=${point.t} score`, point.score, f.threat.score);
  check(`TRAJECTORY t=${point.t} level`, point.level, f.threat.level);
}

/* --- the quoted utterances ---------------------------------------------
   The page shortens some of these for length, which is fine, and it must do
   it by *cutting from the ends* — never by joining two fragments that were
   not adjacent. Stitching reads identically and is quietly a different
   sentence from the one that was said, so the rule here is contiguity: the
   quote has to appear in the transcript, verbatim, as one run of text. */
const norm = (s) => s.replace(/[“”"]/g, "").replace(/\s+/g, " ").trim();
for (const u of S.UTTERANCES) {
  const f = at(u.t);
  const spoken = f.transcript.final[f.transcript.final.length - 1];
  check(`UTTERANCES t=${u.t} stage`, u.stage, spoken.stage);
  const quoted = norm(u.text).toLowerCase();
  if (!norm(spoken.text).toLowerCase().includes(quoted)) {
    problems.push(
      `UTTERANCES t=${u.t} is not one contiguous run of the transcript\n    landing: ${norm(u.text)}\n    recording: ${norm(spoken.text)}`,
    );
  }
}

/* --- the frame the live-call section renders ---------------------------- */
const f36 = at(36);
check("FRAME_36.caller", S.FRAME_36.caller, f36.call.caller_number);
check("FRAME_36.score", S.FRAME_36.score, f36.threat.score);
check("FRAME_36.level", S.FRAME_36.level, f36.threat.level);
check("FRAME_36.stage", S.FRAME_36.stage, S.prettyStage(f36.stage.current));
check("FRAME_36.utterance", norm(S.FRAME_36.utterance), norm(f36.transcript.final.at(-1).text));
check(
  "FRAME_36.tactics",
  Object.fromEntries(S.FRAME_36.tactics.map((t) => [t.label.toLowerCase(), t.weight])),
  f36.manipulation_map,
);
check("FRAME_36.forecast.next", S.FRAME_36.forecast.next, S.prettyStage(f36.forecast.next_stage));
check("FRAME_36.forecast.inSeconds", S.FRAME_36.forecast.inSeconds, f36.forecast.eta_s);
check(
  "FRAME_36.forecast.paymentInSeconds",
  S.FRAME_36.forecast.paymentInSeconds,
  f36.forecast.eta_to_payment_s,
);
check(
  "FRAME_36.coach",
  norm(`Say: "${S.FRAME_36.coach.line}" ${S.FRAME_36.coach.after}`),
  norm(f36.coach.line),
);
check("FRAME_36.coach.why", S.FRAME_36.coach.why, f36.coach.why);

/* --- the contributions and the passport --------------------------------- */
check("DRIVERS", S.DRIVERS, f36.threat.drivers);
check("PASSPORT.claimed", S.PASSPORT.claimed, f36.trust_passport.claimed_identity);
check("PASSPORT.trust", S.PASSPORT.trust, f36.trust_passport.final_trust_pct);
check(
  "PASSPORT.checks",
  S.PASSPORT.checks,
  f36.trust_passport.checks.map((c) => ({ name: c.name, detail: c.detail, source: c.source })),
);

/* --- the first check that fires ----------------------------------------- */
const f0 = at(0);
check("NUMBER_INTEL.number", S.NUMBER_INTEL.number, f0.number_intel.number);
check("NUMBER_INTEL.risk", S.NUMBER_INTEL.risk, f0.number_intel.risk);
check("NUMBER_INTEL.verdict", S.NUMBER_INTEL.verdict, f0.number_intel.verdict);
const firstCheck = f0.number_intel.checks[0];
check("NUMBER_INTEL.source", S.NUMBER_INTEL.source, firstCheck.source);
if (!norm(firstCheck.detail).toLowerCase().includes("originates outside india")) {
  problems.push(
    `NUMBER_INTEL.headline no longer matches the recording's first check\n    recording: ${firstCheck.detail}`,
  );
}

/* ------------------------------------------------------------------------ */
if (problems.length) {
  console.error(
    `\nsession.ts has drifted from mock/stream.json (${problems.length} value${problems.length === 1 ? "" : "s"}):\n`,
  );
  for (const p of problems) console.error(`  • ${p}\n`);
  console.error(
    "Either the recording changed and the landing must be re-transcribed, or\n" +
      "a value on the landing was edited by hand. Fix the landing, not this check.\n",
  );
  process.exit(1);
}

console.log(
  `landing session check: ${S.TRAJECTORY.length} trajectory points, ` +
    `${S.UTTERANCES.length} utterances, ${S.PASSPORT.checks.length} passport checks, ` +
    `${S.DRIVERS.length} contributions — all match mock/stream.json`,
);
