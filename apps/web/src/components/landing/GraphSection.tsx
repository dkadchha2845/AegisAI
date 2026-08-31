/**
 * What the graph knows that no single check can.
 *
 * A phone number, on its own, is a nuisance. The same number appearing beside
 * two payment handles, three domains and four earlier cases is an
 * organisation, and that is a different fact requiring a different response —
 * blocking a caller versus dismantling a crew.
 *
 * **The nodes reposition as you scroll.** They start scattered, as unrelated
 * indicators, and settle into the clustered arrangement as the section
 * arrives, with the edges drawing themselves between them. That is the
 * section's whole claim performed rather than described: nothing about the
 * indicators changed, only what is known about how they relate.
 *
 * **Hover or focus a node and the graph answers.** Its edges brighten, the
 * rest of the graph dims, and the panel beside it says what that entity is
 * connected to. It is keyboard-reachable, so this is a real reading of the
 * data rather than a mouse-only flourish.
 *
 * **Not pinned, deliberately.** The page already spends one long pin on the
 * investigation sequence, which needs it because it is a *sequence*. This is a
 * picture that rearranges; scrubbing it against its own travel through the
 * viewport gives the same effect for none of the pin's cost, and leaves the
 * reader free to stop and interrogate it.
 */

import { useEffect, useRef, useState } from "react";
import {
  gsap,
  split,
  fontsReady,
  DUR,
  EASE,
  reduced,
  refreshSoon,
} from "@/lib/landing-motion";

const W = 900;
const H = 560;

interface GNode {
  id: string;
  label: string;
  kind: "phone" | "upi" | "domain" | "apk" | "case" | "qr";
  /** Settled position. */
  x: number;
  y: number;
  /** Where it starts, before anything is known to connect it. */
  sx: number;
  sy: number;
  meta: string[];
}

const NODES: GNode[] = [
  { id: "phone", label: "+1-838-224-7719", kind: "phone", x: 450, y: 275, sx: 300, sy: 120, meta: ["3 domains", "2 UPI handles", "4 investigations"] },
  { id: "upi1", label: "verify@okaxis", kind: "upi", x: 205, y: 150, sx: 90, sy: 420, meta: ["seen in 3 cases", "first seen 11 days ago"] },
  { id: "upi2", label: "rbi.audit@ybl", kind: "upi", x: 190, y: 400, sx: 620, sy: 470, meta: ["seen in 2 cases", "shares a device fingerprint"] },
  { id: "dom1", label: "cbi-verify.in", kind: "domain", x: 690, y: 128, sx: 760, sy: 380, meta: ["registered 9 days ago", "privacy-shielded registrar"] },
  { id: "dom2", label: "rbi-secure-audit.co", kind: "domain", x: 745, y: 300, sx: 160, sy: 240, meta: ["shares a certificate with cbi-verify.in"] },
  { id: "dom3", label: "parcel-status.link", kind: "domain", x: 672, y: 452, sx: 430, sy: 60, meta: ["redirects to rbi-secure-audit.co"] },
  { id: "apk", label: "CBI-Verify.apk", kind: "apk", x: 430, y: 96, sx: 800, sy: 150, meta: ["requests SMS + accessibility", "self-signed certificate"] },
  { id: "case", label: "Case 4471 · Pune", kind: "case", x: 420, y: 470, sx: 240, sy: 500, meta: ["4 linked cases", "3 states"] },
];

const EDGES: [string, string][] = [
  ["phone", "upi1"],
  ["phone", "upi2"],
  ["phone", "dom1"],
  ["phone", "dom2"],
  ["phone", "apk"],
  ["phone", "case"],
  ["dom1", "dom2"],
  ["dom2", "dom3"],
  ["dom3", "apk"],
  ["upi1", "case"],
  ["upi2", "case"],
];

const KIND_LABEL: Record<GNode["kind"], string> = {
  phone: "Phone",
  upi: "UPI handle",
  domain: "Domain",
  apk: "Installer",
  case: "Investigation",
  qr: "QR",
};

const byId = (id: string) => NODES.find((n) => n.id === id)!;

export function GraphSection() {
  const root = useRef<HTMLElement>(null);
  const [active, setActive] = useState<string>("phone");

  useEffect(() => {
    const el = root.current;
    if (!el || reduced()) return;
    let cancelled = false;
    const teardown: (() => void)[] = [];

    void fontsReady().then(() => {
      if (cancelled) return;
      const ctx = gsap.context(() => {
        const h = split(el.querySelector("[data-g-h2]"), "lines");
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
        gsap.from("[data-g-lede]", {
          opacity: 0,
          y: 22,
          filter: "blur(8px)",
          duration: DUR.reveal,
          ease: EASE.out,
          scrollTrigger: { trigger: "[data-g-lede]", start: "top 88%", once: true },
        });

        /* The rearrangement. Nodes are authored at their *settled* position
           and offset to the scattered one, so the DOM and the SVG never
           disagree about where a node ends up — only about where it currently
           is, which is what the tween owns. */
        const tl = gsap.timeline({
          scrollTrigger: {
            trigger: "[data-g-stage]",
            start: "top 82%",
            end: "top 34%",
            scrub: 0.8,
          },
        });

        NODES.forEach((n, i) => {
          const stage = el.querySelector("[data-g-stage]") as HTMLElement;
          tl.from(
            `[data-g-node="${n.id}"]`,
            {
              x: () => ((n.sx - n.x) / W) * stage.clientWidth,
              y: () => ((n.sy - n.y) / H) * stage.clientHeight,
              opacity: 0,
              scale: 0.7,
              filter: "blur(9px)",
              duration: 0.9,
              ease: EASE.out,
            },
            i * 0.06,
          );
        });

        tl.from("[data-g-edge]", { drawSVG: "0% 0%", duration: 0.6, stagger: 0.05, ease: "power2.inOut" }, 0.4);

        gsap.from("[data-g-panel]", {
          opacity: 0,
          x: 26,
          filter: "blur(8px)",
          duration: DUR.reveal,
          ease: EASE.out,
          scrollTrigger: { trigger: "[data-g-panel]", start: "top 88%", once: true },
        });
      }, el);
      teardown.push(() => ctx.revert());
      // Triggers built after the route's own refresh; see `refreshSoon`.
      refreshSoon();
    });

    return () => {
      cancelled = true;
      teardown.forEach((fn) => fn());
    };
  }, []);

  const node = byId(active);
  const links = EDGES.filter(([a, b]) => a === active || b === active).map(([a, b]) =>
    a === active ? b : a,
  );

  return (
    <section className="lp-section" id="graph" ref={root}>
      <div className="lp-shell">
        <p className="lp-eyebrow">
          <span className="lp-eyebrow__n">06</span> Intelligence
        </p>
        <h2 className="lp-h2" data-g-h2>
          Connections reveal what <em>isolated signals hide.</em>
        </h2>
        <p className="lp-lede" data-g-lede>
          Every detection becomes a node. Numbers, handles, domains and installers that
          keep reappearing together collapse into a single campaign with a risk score, a
          footprint across states, and a report an investigator can file.
        </p>

        <div className="lp-graph">
          <div className="lp-graph__stage" data-g-stage>
            <svg className="lp-graph__svg" viewBox={`0 0 ${W} ${H}`} fill="none" preserveAspectRatio="none">
              {EDGES.map(([a, b]) => {
                const na = byId(a);
                const nb = byId(b);
                const on = a === active || b === active;
                return (
                  <line
                    key={`${a}-${b}`}
                    className="lp-graph__edge"
                    data-g-edge
                    data-on={on || undefined}
                    x1={na.x}
                    y1={na.y}
                    x2={nb.x}
                    y2={nb.y}
                  />
                );
              })}
            </svg>

            <div className="lp-graph__layer">
              {NODES.map((n) => (
                <button
                  type="button"
                  className="lp-graph__node"
                  key={n.id}
                  data-g-node={n.id}
                  data-kind={n.kind}
                  data-on={n.id === active || links.includes(n.id) || undefined}
                  aria-pressed={n.id === active}
                  style={{ left: `${(n.x / W) * 100}%`, top: `${(n.y / H) * 100}%` }}
                  onMouseEnter={() => setActive(n.id)}
                  onFocus={() => setActive(n.id)}
                  onClick={() => setActive(n.id)}
                >
                  <span className="lp-graph__kind">{KIND_LABEL[n.kind]}</span>
                  <span className="lp-graph__label lp-mono">{n.label}</span>
                </button>
              ))}
            </div>
          </div>

          {/* The readout. `aria-live` because the panel is the answer to the
              interaction, and a keyboard user tabbing the graph needs it
              announced rather than merely repainted. */}
          <aside className="lp-graph__panel lp-card" data-g-panel aria-live="polite">
            <p className="lp-label">{KIND_LABEL[node.kind]}</p>
            <p className="lp-graph__pname lp-mono">{node.label}</p>
            <p className="lp-label lp-graph__psub">Connected to</p>
            <ul className="lp-graph__links">
              {links.map((id) => (
                <li key={id}>
                  <span className="lp-mono">{byId(id).label}</span>
                  <em>{KIND_LABEL[byId(id).kind]}</em>
                </li>
              ))}
            </ul>
            <ul className="lp-graph__meta">
              {node.meta.map((m) => (
                <li key={m}>{m}</li>
              ))}
            </ul>
            <p className="lp-graph__hint">
              Hover or tab through the graph. This is a worked example built from the
              recorded session, not live case data.
            </p>
          </aside>
        </div>
      </div>
    </section>
  );
}
