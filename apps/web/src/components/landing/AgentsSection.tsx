/**
 * The architecture, drawn as the registry has it.
 *
 * The core at the top, the four stages of the investigation graph beneath it,
 * and the one verdict they all feed. Each stage lists the agents registered in
 * it and what each one is for. A packet runs core → stage → verdict, one stage
 * at a time, and the stage it passes through lights up, so the diagram is read
 * in the order the system runs.
 *
 * **The agents on it are the agents the system has.** When `/api/health`
 * answers, the stages, the agent ids and their versions are read from its
 * registry report, and the line under the diagram says so. When it does not,
 * the same list is shown from this file — the registry as of 2026-10-21: eight
 * agents in four stages. An earlier version of this section claimed thirteen
 * specialists in tiers ("Correlate", "Geospatial") that are not registered
 * agents at all.
 *
 * **Why not one model with a big prompt.** Each agent answers one narrow
 * question it can be held to, carries a version, records its timing and its
 * own degradation. A single model asked to do all of it cannot tell you which
 * part of its answer failed.
 *
 * **Layout: measured, not drawn to scale.** The core, the stage cards and the
 * verdict are ordinary grid layout, as tall as their contents. The connectors
 * are computed from where those boxes actually are and recomputed when they
 * move, so a line always starts and ends on the box it belongs to. They draw
 * with `pathLength="1"` and a CSS transition, which survives re-measuring.
 *
 * Below 900px the four stages stack and the connectors go: a reading order
 * carries the same sequence.
 */

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { Gauge, MessagesSquare, ScanLine, Search, type LucideIcon } from "lucide-react";
import {
  gsap,
  ScrollTrigger,
  split,
  fontsReady,
  DUR,
  EASE,
  reduced,
  refreshSoon,
} from "@/lib/landing-motion";
import { useLiveHealth } from "@/components/landing/live";

interface StageInfo {
  label: string;
  icon: LucideIcon;
  job: string;
}

/** What each stage of the graph is for. Keyed by the registry's stage id. */
const STAGE_INFO: Record<string, StageInfo> = {
  extract: { label: "Extract", icon: ScanLine, job: "Decide what the evidence is before anything reads it." },
  investigate: { label: "Investigate", icon: Search, job: "Check what can be looked up about the source." },
  reason: { label: "Reason", icon: MessagesSquare, job: "Read the conversation — the caller and the victim separately." },
  judge: { label: "Judge", icon: Gauge, job: "Turn the findings into one number and a forecast." },
};

/** What each agent is for, in a line, from its own module docstring. Keyed by
 *  the registry's agent id. */
const AGENT_INFO: Record<string, { name: string; job: string }> = {
  input_classifier: { name: "Input classifier", job: "Types each item from its bytes, flags a label that lies, and decides what runs next." },
  number_spoofing: { name: "Number spoofing", job: "Reported numbers, routing, VoIP prefixes, and caller ID against the authority claimed." },
  stage_classifier: { name: "Stage classifier", job: "Which stage of the scam script each caller line is at." },
  script_match: { name: "Script match", job: "How closely the caller follows a known script, even paraphrased." },
  trust_passport: { name: "Trust passport", job: "Six checkable questions — did they ask for an OTP? — each citing a source." },
  coercion_tracker: { name: "Coercion tracker", job: "The victim's side: how much pressure they are under." },
  threat_fusion: { name: "Threat fusion", job: "Fuses the signals into the score, every point attributed to a named driver." },
  digital_twin: { name: "Digital twin", job: "Forecasts the next stage, and the seconds until money moves." },
};

/** The registry as of 2026-10-21, for when `/api/health` cannot be reached. */
const SNAPSHOT: { stages: string[]; agents: Record<string, string[]> } = {
  stages: ["extract", "investigate", "reason", "judge"],
  agents: {
    extract: ["input_classifier"],
    investigate: ["number_spoofing"],
    reason: ["stage_classifier", "script_match", "trust_passport", "coercion_tracker"],
    judge: ["threat_fusion", "digital_twin"],
  },
};

const titleCase = (id: string) =>
  id.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());

interface Wires {
  w: number;
  h: number;
  feed: Record<string, string>;
  out: Record<string, string>;
}

/** Leaves downward and arrives downward: reads as flow, not as a connector. */
const down = (ax: number, ay: number, bx: number, by: number) => {
  const my = (ay + by) / 2;
  return `M ${ax.toFixed(1)} ${ay.toFixed(1)} C ${ax.toFixed(1)} ${my.toFixed(1)}, ${bx.toFixed(1)} ${my.toFixed(1)}, ${bx.toFixed(1)} ${by.toFixed(1)}`;
};

export function AgentsSection() {
  const root = useRef<HTMLElement>(null);
  const stageRef = useRef<HTMLDivElement>(null);
  const health = useLiveHealth();
  const [wires, setWires] = useState<Wires | null>(null);

  const live = health?.agents;
  const registry = live ?? SNAPSHOT;
  const stages = registry.stages.map((id) => ({
    id,
    info: STAGE_INFO[id] ?? { label: titleCase(id), icon: Search, job: "" },
    agents: (registry.agents[id] ?? []).map((a) => ({
      id: a,
      name: AGENT_INFO[a]?.name ?? titleCase(a),
      job: AGENT_INFO[a]?.job ?? "",
      version: live?.versions?.[a] ?? null,
    })),
  }));
  const agentCount = stages.reduce((n, s) => n + s.agents.length, 0);
  const stageKey = stages.map((s) => `${s.id}:${s.agents.length}`).join("|");

  /* --- the connectors, measured from the boxes they join -------------- */
  useLayoutEffect(() => {
    const box = stageRef.current;
    if (!box) return;
    /* Layout positions, not painted ones: `offsetTop`/`offsetLeft` ignore
       transforms, and the cards spend their entrance 28px below where they
       settle. A measurement taken mid-entrance with `getBoundingClientRect`
       would aim every line at where a card briefly was. */
    const place = (n: HTMLElement) => {
      let x = 0;
      let y = 0;
      let cur: HTMLElement | null = n;
      while (cur && cur !== box) {
        x += cur.offsetLeft;
        y += cur.offsetTop;
        cur = cur.offsetParent as HTMLElement | null;
      }
      return { x, y, w: n.offsetWidth, h: n.offsetHeight };
    };
    const measure = () => {
      const coreEl = box.querySelector<HTMLElement>("[data-a-core]");
      const verdictEl = box.querySelector<HTMLElement>("[data-a-verdict]");
      if (!coreEl || !verdictEl) return;
      const core = place(coreEl);
      const verdict = place(verdictEl);
      const feed: Record<string, string> = {};
      const out: Record<string, string> = {};
      box.querySelectorAll<HTMLElement>("[data-a-card]").forEach((card) => {
        const r = place(card);
        const id = card.dataset.aCard ?? "";
        const cx = r.x + r.w / 2;
        feed[id] = down(core.x + core.w / 2, core.y + core.h, cx, r.y);
        out[id] = down(cx, r.y + r.h, verdict.x + verdict.w / 2, verdict.y);
      });
      setWires((prev) => {
        const next = { w: box.offsetWidth, h: box.offsetHeight, feed, out };
        return prev && JSON.stringify(prev) === JSON.stringify(next) ? prev : next;
      });
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(box);
    void fontsReady().then(measure);
    return () => ro.disconnect();
  }, [stageKey]);

  /* --- the entrance -------------------------------------------------- */
  useEffect(() => {
    const el = root.current;
    const box = stageRef.current;
    if (!el || !box) return;
    // Reduced motion: everything is simply there, lines drawn.
    if (reduced()) {
      box.dataset.built = "";
      return;
    }
    let cancelled = false;
    const teardown: (() => void)[] = [];

    void fontsReady().then(() => {
      if (cancelled) return;
      const ctx = gsap.context(() => {
        const h = split(el.querySelector("[data-a-h2]"), "lines");
        gsap.from(h.lines, {
          yPercent: 116,
          opacity: 0,
          filter: "blur(12px)",
          duration: DUR.slow,
          ease: EASE.out,
          stagger: 0.09,
          scrollTrigger: { trigger: el, start: "top 72%", once: true },
          onComplete: () => h.revert(),
        });
        gsap.from("[data-a-lede]", {
          opacity: 0,
          y: 22,
          filter: "blur(8px)",
          duration: DUR.reveal,
          ease: EASE.out,
          scrollTrigger: { trigger: "[data-a-lede]", start: "top 88%", once: true },
        });

        /* Played once, as the diagram comes into view — not scrubbed. A
           scrub tied to the diagram's own travel finished only once its top
           had left the screen, so nobody ever saw it whole. Core, then the
           four stages left to right, then the verdict; the lines draw in CSS
           as the stages land (`data-built`). */
        const tl = gsap.timeline({
          paused: true,
          defaults: { ease: EASE.out },
          onComplete: () => {
            box.dataset.live = "";
          },
        });
        tl.from("[data-a-core]", { opacity: 0, y: -14, scale: 0.92, duration: 0.6 })
          .add(() => {
            box.dataset.built = "";
          }, "-=0.2")
          .from("[data-a-card]", { opacity: 0, y: 28, filter: "blur(8px)", duration: 0.7, stagger: 0.12, clearProps: "filter" }, "-=0.1")
          .from("[data-a-card] li", { opacity: 0, x: -10, duration: 0.4, stagger: 0.035 }, "-=0.55")
          .from("[data-a-verdict]", { opacity: 0, y: 14, scale: 0.92, duration: 0.6 }, "-=0.25");

        ScrollTrigger.create({
          trigger: box,
          start: "top 78%",
          once: true,
          onEnter: () => tl.play(),
        });
      }, el);
      teardown.push(() => ctx.revert());
      refreshSoon();
    });

    return () => {
      cancelled = true;
      teardown.forEach((fn) => fn());
    };
  }, []);

  /* --- the system running: one packet per stage, in order --------------
     Rebuilt when the connectors are re-measured, because a packet rides the
     path as it was when its tween started. Waits for the entrance. */
  useEffect(() => {
    const box = stageRef.current;
    if (!box || !wires || reduced()) return;
    const ctx = gsap.context(() => {
      const ids = Object.keys(wires.feed);
      const dot = box.querySelector("[data-a-packet]");
      const verdict = box.querySelector("[data-a-verdict]");
      if (!dot || !ids.length) return;
      const loop = gsap.timeline({ repeat: -1, paused: true });
      ids.forEach((id) => {
        const feed = box.querySelector<SVGPathElement>(`[data-a-feed="${id}"]`);
        const out = box.querySelector<SVGPathElement>(`[data-a-out="${id}"]`);
        const card = box.querySelector<HTMLElement>(`[data-a-card="${id}"]`);
        if (!feed || !out || !card) return;
        loop
          .set(dot, { opacity: 1 })
          .to(dot, { motionPath: { path: feed, align: feed, alignOrigin: [0.5, 0.5] }, duration: 0.85, ease: "power1.inOut" })
          .add(() => card.setAttribute("data-hot", ""))
          .set(dot, { opacity: 0 })
          .to({}, { duration: 0.9 })
          .set(dot, { opacity: 1 })
          .to(dot, { motionPath: { path: out, align: out, alignOrigin: [0.5, 0.5] }, duration: 0.85, ease: "power1.inOut" })
          .add(() => card.removeAttribute("data-hot"))
          .set(dot, { opacity: 0 })
          .fromTo(verdict, { "--hit": 1 }, { "--hit": 0, duration: 0.6, ease: "power2.out", immediateRender: false })
          .to({}, { duration: 0.15 });
      });
      // Start once the entrance has finished; poll the attribute it sets
      // rather than coupling the two effects' lifetimes.
      const start = () => {
        if (box.hasAttribute("data-live")) loop.play();
        else gsap.delayedCall(0.4, start);
      };
      start();
    }, box);
    return () => {
      ctx.revert();
      box.querySelectorAll("[data-hot]").forEach((n) => n.removeAttribute("data-hot"));
    };
  }, [wires]);

  return (
    <section className="lp-section" id="agents" ref={root}>
      <div className="lp-shell">
        <p className="lp-eyebrow">
          <span className="lp-eyebrow__n">04</span> Capabilities
        </p>
        <h2 className="lp-h2" data-a-h2>
          One threat. <em>Many agents.</em>
        </h2>
        <p className="lp-lede" data-a-lede>
          Not one model with a large prompt. {agentCount} specialists in {stages.length} stages,
          each answering a question it can be held to, each versioned, timed and reporting its
          own status — because a single opaque answer cannot tell you which part of it failed.
        </p>

        <div className="lp-arch" data-a-stage ref={stageRef}>
          {wires && (
            <svg
              className="lp-arch__svg"
              viewBox={`0 0 ${wires.w} ${wires.h}`}
              width={wires.w}
              height={wires.h}
              fill="none"
              aria-hidden="true"
            >
              {stages.map((s, i) =>
                wires.feed[s.id] ? (
                  <path
                    key={`f-${s.id}`}
                    className="lp-arch__edge"
                    d={wires.feed[s.id]}
                    pathLength={1}
                    data-a-feed={s.id}
                    style={{ ["--i" as string]: i }}
                  />
                ) : null,
              )}
              {stages.map((s, i) =>
                wires.out[s.id] ? (
                  <path
                    key={`o-${s.id}`}
                    className="lp-arch__edge lp-arch__edge--out"
                    d={wires.out[s.id]}
                    pathLength={1}
                    data-a-out={s.id}
                    style={{ ["--i" as string]: i + stages.length }}
                  />
                ) : null,
              )}
              <circle className="lp-arch__packet" r={3.5} cx={0} cy={0} data-a-packet />
            </svg>
          )}

          <div className="lp-arch__hub lp-arch__hub--core" data-a-core>
            <b>AEGIS CORE</b>
            <span>orchestration · tracing · degradation</span>
          </div>

          <div className="lp-arch__row">
            {stages.map((s) => (
              <article className="lp-arch__card" key={s.id} data-a-card={s.id}>
                <header>
                  <span className="lp-arch__icon">
                    <s.info.icon size={16} strokeWidth={1.7} aria-hidden="true" />
                  </span>
                  <h3>{s.info.label}</h3>
                  <span className="lp-arch__count lp-mono">
                    {s.agents.length} {s.agents.length === 1 ? "agent" : "agents"}
                  </span>
                </header>
                {s.info.job && <p>{s.info.job}</p>}
                <ul>
                  {s.agents.map((a) => (
                    <li key={a.id}>
                      <span className="lp-arch__aname">
                        {a.name}
                        {a.version && <span className="lp-arch__ver lp-mono">v{a.version}</span>}
                      </span>
                      {a.job && <span className="lp-arch__ajob">{a.job}</span>}
                    </li>
                  ))}
                </ul>
              </article>
            ))}
          </div>

          <div className="lp-arch__hub lp-arch__hub--verdict" data-a-verdict>
            <b>One verdict</b>
            <span>score · reasons · next action</span>
          </div>
        </div>

        <p className="lp-arch__source lp-mono">
          <span className="lp-arch__srcdot" data-live={live ? "" : undefined} aria-hidden="true" />
          {live
            ? `${agentCount} agents registered · read live from /api/health`
            : `${agentCount} agents registered · from agents/registry.py, as of 2026-10-21`}
        </p>

        <p className="lp-note">
          <strong>Every agent ships with a benign-input test.</strong> Metadata that a
          legitimate caller might legitimately have must never be able to manufacture a
          scam on its own, so soft signals stay in weighted fusion instead of becoming
          dispositive rules.
        </p>
      </div>
    </section>
  );
}
