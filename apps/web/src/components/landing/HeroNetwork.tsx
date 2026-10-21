/**
 * The hero's visual: AegisAI, drawn as what it does.
 *
 * Eight kinds of evidence on the outside, four analysis lanes inside them, and
 * the core in the middle. Each piece of evidence is wired to the lane that
 * actually reads it — a phone call and a voice note to **Voice**, a message
 * and an email to **Text**, a screenshot and a QR code to **Vision**, a UPI ID
 * and a caller number to **Identity** — and every lane feeds the core. Packets
 * travel the whole route, evidence → lane → core, and the core answers each
 * arrival, so the picture is not a diagram of a system: it is one running.
 *
 * **Every input on it is one the product reads today.** Voice is Whisper
 * (`/api/analyze/audio`) and the live session; Text is the analyzer behind
 * `/api/analyze/text`; Vision is OCR plus QR decoding (`/api/analyze/image`);
 * Identity is the structural UPI checks and the caller-number agent. A link
 * scanner is planned but not built, so there is no "URL" node here. A hero that
 * advertises a capability the product lacks is the claim this product exists
 * to catch.
 *
 * **The layout is symmetric by construction.** Lanes sit on the diagonals and
 * each lane's two inputs sit 22.5° either side of it, so the eight inputs are
 * evenly spaced at 45° and no edge crosses another or a label.
 *
 * **Why it is half SVG and half DOM.** The edges want to be SVG: drawing a
 * line *on* needs a stroke dash, and moving a packet *along* one needs a path
 * to sample. The nodes want to be DOM: real icons, real text. Both layers read
 * one table of positions, so a label cannot drift from its line.
 *
 * **Why every DOM node sits in a slot.** A node is centred on its point with
 * `translate(-50%, -50%)`. If GSAP animated that same element, it would read
 * the centring as its own starting transform and write it back in pixels —
 * measured before the web font landed, so the node ends up a few pixels off
 * its line. The slot owns the centring and never moves; the node inside it
 * owns the motion and never centres.
 *
 * Degradation: with JavaScript disabled, or with reduced motion, the diagram is
 * static, complete and correct — every node, label and edge is in the markup.
 * It is `aria-hidden` because it pictures the prose beside it.
 */

import { useEffect, useRef } from "react";
import {
  Hash,
  Image as ImageIcon,
  IndianRupee,
  Mail,
  MessageSquare,
  Mic,
  PhoneCall,
  QrCode,
} from "lucide-react";
import { gsap, DUR, EASE, reduced } from "@/lib/landing-motion";

/* ----------------------------------------------------------- geometry */

const VB = 620;                 /* the SVG viewBox, and the DOM layer's % basis */
const C = VB / 2;
const R_LANE = 134;
const R_INPUT = 250;
/** Where an input's edge stops travelling radially and turns toward its lane. */
const R_BEND = 192;

const rad = (deg: number) => ((deg - 90) * Math.PI) / 180;
const at = (deg: number, r: number) => ({
  x: C + Math.cos(rad(deg)) * r,
  y: C + Math.sin(rad(deg)) * r,
});
const pct = (n: number) => `${(n / VB) * 100}%`;
const f = (n: number) => n.toFixed(1);

const LANES = [
  { id: "text", label: "Text", deg: 45, inputs: [
    { id: "msg", label: "Message", icon: MessageSquare },
    { id: "email", label: "Email", icon: Mail },
  ] },
  { id: "identity", label: "Identity", deg: 135, inputs: [
    { id: "upi", label: "UPI ID", icon: IndianRupee },
    { id: "caller", label: "Caller number", icon: Hash },
  ] },
  { id: "vision", label: "Vision", deg: 225, inputs: [
    { id: "shot", label: "Screenshot", icon: ImageIcon },
    { id: "qr", label: "QR code", icon: QrCode },
  ] },
  { id: "voice", label: "Voice", deg: 315, inputs: [
    { id: "call", label: "Phone call", icon: PhoneCall },
    { id: "note", label: "Voice note", icon: Mic },
  ] },
].map((l) => ({ ...l, ...at(l.deg, R_LANE) }));

const INPUTS = LANES.flatMap((lane) =>
  lane.inputs.map((n, k) => {
    const deg = lane.deg + (k === 0 ? -22.5 : 22.5);
    const bend = at(deg, R_BEND);
    return { ...n, deg, lane, ...at(deg, R_INPUT), bend };
  }),
);

/** Input → lane: leaves the chip heading straight for the centre, then turns
 *  into its lane — a funnel, which is what the stage is. */
const inEdge = (n: (typeof INPUTS)[number]) =>
  `M ${f(n.x)} ${f(n.y)} Q ${f(n.bend.x)} ${f(n.bend.y)} ${f(n.lane.x)} ${f(n.lane.y)}`;
/** Lane → core, straight. A path rather than a line so a packet can ride it. */
const spoke = (l: (typeof LANES)[number]) => `M ${f(l.x)} ${f(l.y)} L ${C} ${C}`;

/** One full trip, evidence to core, and the gap between two inputs starting
 *  theirs. 8 × 0.72s ≈ one cycle, so the core is never idle and never busy. */
const LEG_IN = 1.15;
const LEG_CORE = 0.55;
const STAGGER = 0.72;
const CYCLE = STAGGER * INPUTS.length;

/* ---------------------------------------------------------- component */

export function HeroNetwork() {
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = root.current;
    if (!el || reduced()) return;

    const ctx = gsap.context(() => {
      /* --- assembly ------------------------------------------------
         Built from the middle out — core, lanes, evidence — which is the
         order the diagram is read in, so it explains itself as it arrives. */
      const intro = gsap.timeline({ delay: 0.22, defaults: { ease: EASE.out } });
      intro
        .from("[data-net-glow]", { opacity: 0, duration: DUR.slow })
        .from("[data-net-hub]", { scale: 0.5, opacity: 0, duration: DUR.slow }, "<")
        .from("[data-net-ring]", { opacity: 0, duration: DUR.slow, stagger: 0.12 }, "-=0.9")
        .from("[data-net-spoke]", { drawSVG: "100% 100%", duration: 0.5, ease: "power2.inOut", stagger: 0.06 }, "-=0.75")
        .from("[data-net-lane]", { scale: 0.6, opacity: 0, duration: DUR.quick, ease: "back.out(1.6)", stagger: 0.07 }, "-=0.3")
        .from("[data-net-edge]", { drawSVG: "100% 100%", duration: 0.6, ease: "power2.inOut", stagger: 0.04 }, "-=0.2")
        .from("[data-net-node]", { scale: 0.7, opacity: 0, y: 6, duration: DUR.quick, stagger: 0.045 }, "-=0.5");

      /* --- the system running ------------------------------------
         Each input sends a packet down its edge, a second packet carries
         it down the lane's spoke, and the core acknowledges the arrival.
         MotionPathPlugin samples the paths the edges already draw, so a
         packet cannot come adrift from its line. */
      const edges = gsap.utils.toArray<SVGPathElement>("[data-net-edge]");
      const spokes = new Map(
        gsap.utils.toArray<SVGPathElement>("[data-net-spoke]").map((p) => [p.dataset.lane, p]),
      );
      const pulse = el.querySelector("[data-net-pulse]");

      edges.forEach((path, i) => {
        const inDot = el.querySelector(`[data-net-packet="${i}"]`);
        const coreDot = el.querySelector(`[data-net-carry="${i}"]`);
        const lane = path.dataset.lane;
        const spokePath = lane ? spokes.get(lane) : undefined;
        const laneEl = el.querySelector(`[data-net-lane-id="${lane}"]`);
        if (!inDot || !coreDot || !spokePath || !laneEl) return;

        gsap
          .timeline({ repeat: -1, repeatDelay: CYCLE - LEG_IN - LEG_CORE, delay: intro.duration() + i * STAGGER })
          .set(inDot, { opacity: 1 })
          .to(inDot, {
            motionPath: { path, align: path, alignOrigin: [0.5, 0.5] },
            duration: LEG_IN,
            ease: "power1.inOut",
          })
          .set(inDot, { opacity: 0 })
          // Both acknowledgements are shorter than the gap between two
          // arrivals, so consecutive packets never animate the same lane or
          // the same pulse at once — no overwrite needed, and none wanted: an
          // overwrite here would kill the other inputs' tweens outright.
          .fromTo(laneEl, { "--hit": 1 }, { "--hit": 0, duration: 0.6, ease: "power2.out", immediateRender: false }, "<")
          .set(coreDot, { opacity: 1 }, "<")
          .to(coreDot, {
            motionPath: { path: spokePath, align: spokePath, alignOrigin: [0.5, 0.5] },
            duration: LEG_CORE,
            ease: "power2.in",
          }, "<")
          .set(coreDot, { opacity: 0 })
          .fromTo(
            pulse,
            { scale: 1, opacity: 0.55 },
            { scale: 1.32, opacity: 0, duration: 0.62, ease: "power2.out", immediateRender: false },
            "<",
          );
      });

      // Two counter-rotating dashed rings, 60 and 92 seconds a turn —
      // perceptible only if you stop and look, which is the right amount for
      // structure.
      gsap.to("[data-net-spin='cw']", { rotation: 360, duration: 60, repeat: -1, ease: "none", svgOrigin: `${C} ${C}` });
      gsap.to("[data-net-spin='ccw']", { rotation: -360, duration: 92, repeat: -1, ease: "none", svgOrigin: `${C} ${C}` });

      /* --- the diagram acknowledges the cursor ---------------------
         A small parallax on the whole picture, pointer devices only. `x`/`y`
         rather than a custom property: `quickTo` passes a bare number, and a
         unitless number in `translate3d()` discards the whole transform. */
      if (window.matchMedia("(pointer: fine)").matches) {
        const xTo = gsap.quickTo(el, "x", { duration: 0.9, ease: "power3.out" });
        const yTo = gsap.quickTo(el, "y", { duration: 0.9, ease: "power3.out" });
        const onMove = (e: PointerEvent) => {
          const r = el.getBoundingClientRect();
          xTo(((e.clientX - (r.left + r.width / 2)) / r.width) * 18);
          yTo(((e.clientY - (r.top + r.height / 2)) / r.height) * 18);
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
      <svg className="lp-net__svg" viewBox={`0 0 ${VB} ${VB}`} fill="none">
        <defs>
          <radialGradient id="lp-net-glow" cx="50%" cy="50%">
            <stop offset="0%" stopColor="var(--lp-accent)" stopOpacity="0.3" />
            <stop offset="65%" stopColor="var(--lp-accent)" stopOpacity="0.05" />
            <stop offset="100%" stopColor="var(--lp-accent)" stopOpacity="0" />
          </radialGradient>
        </defs>

        <circle cx={C} cy={C} r={196} fill="url(#lp-net-glow)" data-net-glow />

        {/* Structure: the lane ring and the evidence ring. Dashed, because a
            solid ring at this scale reads as a border. */}
        <circle className="lp-net__ring" cx={C} cy={C} r={R_LANE} strokeDasharray="2 9" data-net-ring data-net-spin="cw" />
        <circle className="lp-net__ring lp-net__ring--outer" cx={C} cy={C} r={R_INPUT} strokeDasharray="1 14" data-net-ring data-net-spin="ccw" />

        {LANES.map((l) => (
          <path key={l.id} className="lp-net__spoke" d={spoke(l)} data-net-spoke data-lane={l.id} />
        ))}
        {INPUTS.map((n) => (
          <path key={n.id} className="lp-net__edge" d={inEdge(n)} data-net-edge data-lane={n.lane.id} />
        ))}

        {/* Packets start parked on their own chip, invisible; the timeline
            shows each one only while it is travelling. */}
        {INPUTS.map((n, i) => (
          <circle key={`p-${n.id}`} className="lp-net__packet" r={3} cx={n.x} cy={n.y} data-net-packet={i} />
        ))}
        {INPUTS.map((n, i) => (
          <circle
            key={`c-${n.id}`}
            className="lp-net__packet lp-net__packet--core"
            r={3}
            cx={n.lane.x}
            cy={n.lane.y}
            data-net-carry={i}
          />
        ))}
      </svg>

      <div className="lp-net__layer">
        {LANES.map((l) => (
          <div key={l.id} className="lp-net__slot" style={{ left: pct(l.x), top: pct(l.y) }}>
            <div className="lp-net__lane" data-net-lane data-net-lane-id={l.id}>
              <span className="lp-net__ldot" />
              {l.label}
            </div>
          </div>
        ))}

        {INPUTS.map((n) => (
          <div key={n.id} className="lp-net__slot" style={{ left: pct(n.x), top: pct(n.y) }}>
            <div className="lp-net__node" data-net-node>
              <n.icon strokeWidth={1.7} aria-hidden="true" />
              {n.label}
            </div>
          </div>
        ))}

        {/* The core, in the DOM so its wordmark is real text at a real weight
            rather than an SVG glyph that ignores the theme. */}
        <div className="lp-net__slot" style={{ left: "50%", top: "50%" }}>
          <div className="lp-net__hub" data-net-hub>
            <span className="lp-net__pulse" data-net-pulse />
            <span className="lp-net__hubname">AEGIS</span>
            <span className="lp-net__hubsub">Core</span>
          </div>
        </div>
      </div>
    </div>
  );
}
