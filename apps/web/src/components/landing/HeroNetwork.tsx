/**
 * The hero's visual: AegisAI, drawn as what it is.
 *
 * A core, four faculties around it, and nine kinds of evidence around those.
 * Edges curve inward from every input to the faculty that handles it, and
 * from each faculty into the core. Packets travel the edges continuously, so
 * the picture is not a diagram of a system — it is a system running.
 *
 * **Why it is half SVG and half DOM.** The edges want to be SVG: drawing a
 * line *on* requires a stroke dash, and moving something *along* one requires
 * a path to sample. The nodes want to be DOM: they carry a real Lucide icon
 * and a real text label, and a nine-node ring of `<foreignObject>` is a
 * rendering bug hunt in Safari. So the geometry is computed once, in one
 * place, and both layers read from it — which is also why the labels cannot
 * drift away from the lines they belong to.
 *
 * **Why it is not three.js.** Everything here is two-dimensional information:
 * what connects to what. Perspective would add depth to a picture whose whole
 * point is legibility, at the cost of the largest dependency in the bundle on
 * the first screen of the site.
 *
 * Degradation: with JavaScript disabled the diagram is static, complete and
 * correct — every node, label and edge is in the markup. It is `aria-hidden`
 * because it is a picture of the prose beside it; the prose is the content.
 */

import { useEffect, useRef } from "react";
import {
  Fingerprint,
  Globe,
  Image as ImageIcon,
  Mail,
  Mic,
  Package,
  Phone,
  QrCode,
  Link2,
} from "lucide-react";
import { gsap, DUR, EASE, reduced } from "@/lib/landing-motion";

/* ----------------------------------------------------------- geometry */

const VB = 620;                 /* the SVG viewBox, and the DOM overlay's % basis */
const C = VB / 2;
const R_PILLAR = 128;
const R_INPUT = 246;

const rad = (deg: number) => ((deg - 90) * Math.PI) / 180;
const at = (deg: number, r: number) => ({
  x: C + Math.cos(rad(deg)) * r,
  y: C + Math.sin(rad(deg)) * r,
});
const pct = (n: number) => `${(n / VB) * 100}%`;

/** The four faculties, on the diagonals so the nine inputs can sit on the
 *  cardinal spread between them without a label collision. */
const PILLARS = [
  { id: "evidence", label: "Evidence", deg: 315 },
  { id: "agents", label: "Agents", deg: 45 },
  { id: "intel", label: "Threat intel", deg: 135 },
  { id: "risk", label: "Risk", deg: 225 },
].map((p) => ({ ...p, ...at(p.deg, R_PILLAR) }));

/** Nine kinds of evidence, evenly spread. The list is the product's actual
 *  input surface, not a plausible-looking sample of one. */
const INPUTS = [
  { id: "phone", label: "Phone", icon: Phone },
  { id: "url", label: "URL", icon: Link2 },
  { id: "qr", label: "QR", icon: QrCode },
  { id: "email", label: "Email", icon: Mail },
  { id: "image", label: "Image", icon: ImageIcon },
  { id: "audio", label: "Audio", icon: Mic },
  { id: "apk", label: "APK", icon: Package },
  { id: "upi", label: "UPI", icon: Fingerprint },
  { id: "site", label: "Website", icon: Globe },
].map((n, i) => {
  const deg = (360 / 9) * i + 20;
  const p = at(deg, R_INPUT);
  // Nearest faculty by angle, so an edge never crosses the ring to reach one
  // on the far side.
  const pillar = PILLARS.reduce((best, cand) => {
    const d = (a: number, b: number) => Math.abs(((a - b + 540) % 360) - 180);
    return d(cand.deg, deg) < d(best.deg, deg) ? cand : best;
  }, PILLARS[0]);
  return { ...n, deg, ...p, pillar };
});

/** Input → faculty, as a quadratic pulled toward the core: the edges bow
 *  inward, which reads as convergence rather than as a wheel's spokes. */
function inEdge(n: (typeof INPUTS)[number]): string {
  const mx = (n.x + n.pillar.x) / 2;
  const my = (n.y + n.pillar.y) / 2;
  const cx = mx + (C - mx) * 0.34;
  const cy = my + (C - my) * 0.34;
  return `M ${n.x.toFixed(1)} ${n.y.toFixed(1)} Q ${cx.toFixed(1)} ${cy.toFixed(1)} ${n.pillar.x.toFixed(1)} ${n.pillar.y.toFixed(1)}`;
}

/* ---------------------------------------------------------- component */

export function HeroNetwork() {
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = root.current;
    if (!el) return;
    const still = reduced();

    const ctx = gsap.context(() => {
      /* --- assembly ------------------------------------------------
         The system builds itself from the middle out: core, then the
         faculties and the edges that reach them, then the evidence around
         the outside. It is the reading order of the diagram, so the picture
         explains itself while it arrives. */
      if (!still) {
        const tl = gsap.timeline({ delay: 0.22 });
        tl.from("[data-net-core]", {
          scale: 0.4,
          opacity: 0,
          duration: DUR.slow,
          ease: EASE.out,
          transformOrigin: "50% 50%",
        })
          .from("[data-net-ring]", { scale: 0.6, opacity: 0, duration: DUR.slow, ease: EASE.out, stagger: 0.09, transformOrigin: "50% 50%" }, "-=0.9")
          .from("[data-net-spoke]", { drawSVG: "0% 0%", duration: 0.5, ease: "power2.inOut", stagger: 0.06 }, "-=0.7")
          .from("[data-net-pillar]", { scale: 0.5, opacity: 0, duration: DUR.quick, ease: "back.out(1.7)", stagger: 0.07 }, "-=0.35")
          .from("[data-net-edge]", { drawSVG: "0% 0%", duration: 0.62, ease: "power2.inOut", stagger: 0.045 }, "-=0.25")
          .from("[data-net-node]", { scale: 0.4, opacity: 0, filter: "blur(6px)", duration: DUR.quick, ease: "back.out(1.6)", stagger: 0.04 }, "-=0.55");

        /* --- the system running ------------------------------------
           One packet per edge, each starting at a different point in the
           same 3.4s cycle. MotionPathPlugin samples the path the edge
           already draws, so a packet cannot come adrift from its line. */
        gsap.utils.toArray<SVGPathElement>("[data-net-edge]").forEach((path, i) => {
          const dot = el.querySelector<SVGCircleElement>(`[data-net-packet="${i}"]`);
          if (!dot) return;
          gsap.set(dot, { opacity: 0 });
          gsap
            .timeline({ repeat: -1, delay: 1.4 + i * 0.38, repeatDelay: 1.9 })
            .to(dot, { opacity: 1, duration: 0.2 })
            .to(
              dot,
              {
                motionPath: { path, align: path, alignOrigin: [0.5, 0.5] },
                duration: 1.5,
                ease: "power1.inOut",
              },
              0,
            )
            .to(dot, { opacity: 0, duration: 0.24 }, "-=0.24");
        });

        // The faculties breathe, a beat apart, so the ring never looks
        // switched on all at once.
        gsap.to("[data-net-pillar] .lp-net__pdot", {
          scale: 1.55,
          opacity: 0.35,
          duration: 1.5,
          ease: "sine.inOut",
          repeat: -1,
          yoyo: true,
          stagger: 0.42,
          transformOrigin: "50% 50%",
        });

        // Two counter-rotating rings. The only rotation on the page, and it
        // is 60 and 90 seconds a turn — perceptible only if you stop and
        // look, which is the correct amount for a background element.
        gsap.to("[data-net-spin='cw']", { rotation: 360, duration: 60, repeat: -1, ease: "none", transformOrigin: "50% 50%" });
        gsap.to("[data-net-spin='ccw']", { rotation: -360, duration: 92, repeat: -1, ease: "none", transformOrigin: "50% 50%" });
      }

      /* --- the diagram acknowledges the cursor ---------------------
         A 14px parallax on the whole group and a slightly larger one on the
         outer ring, so the picture has depth without becoming a toy. Pointer
         only: on a touch device this is dead weight, and `quickTo` keeps it
         to two writes a frame either way. */
      if (!still && window.matchMedia("(pointer: fine)").matches) {
        // `x`/`y` rather than a custom property: `quickTo` only ever passes a
        // bare number, and a number written to `--net-x` lands in the
        // stylesheet unitless, where `translate3d()` silently discards the
        // whole transform.
        const xTo = gsap.quickTo(el, "x", { duration: 0.9, ease: "power3.out" });
        const yTo = gsap.quickTo(el, "y", { duration: 0.9, ease: "power3.out" });
        const onMove = (e: PointerEvent) => {
          const r = el.getBoundingClientRect();
          xTo(((e.clientX - (r.left + r.width / 2)) / r.width) * 26);
          yTo(((e.clientY - (r.top + r.height / 2)) / r.height) * 26);
        };
        window.addEventListener("pointermove", onMove, { passive: true });
        return () => window.removeEventListener("pointermove", onMove);
      }
      return undefined;
    }, el);

    return () => ctx.revert();
  }, []);

  return (
    <div className="lp-net" ref={root} aria-hidden="true">
      <svg className="lp-net__svg" viewBox={`0 0 ${VB} ${VB}`} fill="none" data-net-svg>
        <defs>
          <radialGradient id="lp-net-core" cx="50%" cy="50%">
            <stop offset="0%" stopColor="var(--lp-accent)" stopOpacity="0.34" />
            <stop offset="70%" stopColor="var(--lp-accent)" stopOpacity="0.05" />
            <stop offset="100%" stopColor="var(--lp-accent)" stopOpacity="0" />
          </radialGradient>
        </defs>

        {/* The field the core sits in. */}
        <circle cx={C} cy={C} r={210} fill="url(#lp-net-core)" data-net-core />

        {/* Two structural rings, counter-rotating. Dashed, because a solid
            ring at this scale reads as a border and a dashed one reads as a
            measurement. */}
        <circle
          className="lp-net__ring"
          cx={C}
          cy={C}
          r={R_PILLAR}
          data-net-ring
          data-net-spin="cw"
          strokeDasharray="2 10"
        />
        <circle
          className="lp-net__ring lp-net__ring--outer"
          cx={C}
          cy={C}
          r={R_INPUT}
          data-net-ring
          data-net-spin="ccw"
          strokeDasharray="1 16"
        />

        {/* Faculty → core. */}
        {PILLARS.map((p) => (
          <line
            key={p.id}
            className="lp-net__spoke"
            data-net-spoke
            x1={p.x}
            y1={p.y}
            x2={C}
            y2={C}
          />
        ))}

        {/* Evidence → faculty, and the packet that travels it. */}
        {INPUTS.map((n) => (
          <path key={n.id} className="lp-net__edge" data-net-edge d={inEdge(n)} />
        ))}
        {INPUTS.map((n, i) => (
          <circle key={`p-${n.id}`} className="lp-net__packet" data-net-packet={i} r={2.6} cx={n.x} cy={n.y} />
        ))}
      </svg>

      {/* --- the DOM layer: faculties and evidence ------------------- */}
      <div className="lp-net__nodes">
        {PILLARS.map((p) => (
          <div
            key={p.id}
            className="lp-net__pillar"
            data-net-pillar
            style={{ left: pct(p.x), top: pct(p.y) }}
          >
            <span className="lp-net__pdot" />
            <span className="lp-net__plabel">{p.label}</span>
          </div>
        ))}

        {INPUTS.map((n) => (
          <div
            key={n.id}
            className="lp-net__node"
            data-net-node
            style={{ left: pct(n.x), top: pct(n.y) }}
          >
            <n.icon size={15} strokeWidth={1.6} />
            <span className="lp-net__nlabel">{n.label}</span>
          </div>
        ))}

        {/* The core, in the DOM so the wordmark inside it is real text at a
            real weight rather than an SVG glyph that ignores the theme. */}
        <div className="lp-net__hub" data-net-core>
          <span className="lp-net__hubring" />
          <span className="lp-net__hubname">AEGIS</span>
          <span className="lp-net__hubsub">CORE</span>
        </div>
      </div>
    </div>
  );
}
