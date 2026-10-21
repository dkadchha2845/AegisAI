/**
 * The problem, stated as a shape rather than as a list.
 *
 * Ten channels scattered around a stage, each arriving on its own — and then
 * the lines draw and they turn out to be one operation. That is the argument
 * of the section in one gesture: the attack is joined up and the defence is
 * not, because every tool built to stop it watches exactly one of these.
 *
 * **Why the entrances differ from chip to chip.** Ten identical fades would
 * say "here is a list of ten things". Cycling four entrances — up, in from the
 * side, out of scale, out of a clip — says "these arrived separately", which
 * is the claim. The cycle is deterministic by index, so it is a composition
 * rather than a randomiser, and every one of them lands on the same easing
 * and the same duration so the section still reads as one system.
 *
 * **The geometry is computed once and shared.** The chips are DOM, the lines
 * are SVG, and both read the same table of positions — so a label can never
 * drift away from the line that belongs to it, at any viewport.
 *
 * **Why each chip sits in a slot.** A chip is centred on its point with
 * `translate(-50%, -50%)`. When GSAP animated that same element it read the
 * centring as its starting transform — mid-way through a CSS transition, as it
 * happened — and wrote a wrong one back as the end state: chips settled up to
 * 90px off their lines, and three stayed at half size. The slot owns the
 * centring and never moves; the chip inside it owns the entrance.
 *
 * **After the web forms, it keeps working.** One signal at a time travels a
 * line from its channel into the centre, which answers each arrival — the
 * section's claim, that eleven surfaces are one operation, shown rather than
 * asserted.
 */

import { useEffect, useRef } from "react";
import {
  FileText,
  Fingerprint,
  Globe,
  Image as ImageIcon,
  Mail,
  MessageCircle,
  MessageSquare,
  Mic,
  Package,
  Phone,
  QrCode,
} from "lucide-react";
import {
  gsap,
  split,
  fontsReady,
  DUR,
  EASE,
  reduced,
  refreshSoon,
} from "@/lib/landing-motion";

const W = 1000;
const H = 520;
const CX = W / 2;
const CY = H / 2;
const RX = 396;
const RY = 196;

/** Where the attacker actually is. Deliberately not "channels we support" —
 *  the point of the section is that the surface is one surface. */
const CHANNELS = [
  { id: "sms", label: "SMS", icon: MessageSquare },
  { id: "wa", label: "WhatsApp", icon: MessageCircle },
  { id: "email", label: "Email", icon: Mail },
  { id: "qr", label: "QR code", icon: QrCode },
  { id: "call", label: "Phone call", icon: Phone },
  { id: "upi", label: "UPI ID", icon: Fingerprint },
  { id: "web", label: "Website", icon: Globe },
  { id: "apk", label: "APK", icon: Package },
  { id: "audio", label: "Voice note", icon: Mic },
  { id: "pdf", label: "PDF", icon: FileText },
  { id: "shot", label: "Screenshot", icon: ImageIcon },
].map((c, i, all) => {
  const a = ((i / all.length) * 360 - 90) * (Math.PI / 180);
  return { ...c, x: CX + Math.cos(a) * RX, y: CY + Math.sin(a) * RY };
});

/** The four entrances, cycled by index. */
const ENTRANCES = [
  { opacity: 0, y: 32, filter: "blur(12px)" },
  { opacity: 0, x: -44, filter: "blur(10px)" },
  { opacity: 0, scale: 0.6, filter: "blur(10px)" },
  { opacity: 0, x: 44, filter: "blur(10px)" },
];

/** A channel's line into the centre. A path rather than a line, so a signal
 *  can ride it. */
const toCore = (c: (typeof CHANNELS)[number]) =>
  `M ${c.x.toFixed(1)} ${c.y.toFixed(1)} L ${CX} ${CY}`;

export function ProblemSection() {
  const root = useRef<HTMLElement>(null);

  useEffect(() => {
    const el = root.current;
    if (!el || reduced()) return;
    let cancelled = false;
    const teardown: (() => void)[] = [];

    void fontsReady().then(() => {
      if (cancelled) return;
      const ctx = gsap.context(() => {
        const h = split(el.querySelector("[data-p-h2]"), "lines");
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

        gsap.from("[data-p-lede]", {
          opacity: 0,
          y: 24,
          filter: "blur(8px)",
          duration: DUR.reveal,
          ease: EASE.out,
          scrollTrigger: { trigger: "[data-p-lede]", start: "top 86%", once: true },
        });

        /* The chips arrive separately, then the lines find them, then the
           centre resolves. One timeline so the three beats cannot overlap
           into mush no matter how fast the reader scrolls past. */
        const tl = gsap.timeline({
          scrollTrigger: { trigger: "[data-p-stage]", start: "top 76%", once: true },
        });

        gsap.utils.toArray<HTMLElement>("[data-p-chip]").forEach((chip, i) => {
          tl.from(
            chip,
            { ...ENTRANCES[i % ENTRANCES.length], duration: DUR.reveal, ease: EASE.out },
            i * 0.075,
          );
        });

        tl.from(
          "[data-p-edge]",
          { drawSVG: "0% 0%", duration: 0.7, ease: "power2.inOut", stagger: 0.05 },
          ">-0.25",
        )
          .from(
            "[data-p-core]",
            { scale: 0.3, opacity: 0, duration: DUR.reveal, ease: "back.out(1.7)", transformOrigin: "50% 50%" },
            "<0.25",
          )
          .from("[data-p-verdict]", { opacity: 0, y: 16, duration: DUR.reveal, ease: EASE.out }, "-=0.3");

        /* Once the web exists it keeps working: a signal leaves one channel
           at a time, travels its line, and the centre answers. Channels fire
           in a shuffled but fixed order, so neighbours never fire back to
           back and the pattern does not read as a clock hand. */
        const edges = gsap.utils.toArray<SVGPathElement>("[data-p-edge]");
        const core = el.querySelector("[data-p-core]");
        const signal = gsap.timeline({ paused: true, repeat: -1 });
        const ORDER = [0, 6, 3, 9, 1, 7, 4, 10, 2, 8, 5];
        ORDER.forEach((i, k) => {
          const path = edges[i];
          const dot = el.querySelector(`[data-p-signal="${i}"]`);
          if (!path || !dot) return;
          const t = k * 0.62;
          signal
            .set(dot, { opacity: 1 }, t)
            .to(dot, { motionPath: { path, align: path, alignOrigin: [0.5, 0.5] }, duration: 0.95, ease: "power1.in" }, t)
            .set(dot, { opacity: 0 }, t + 0.95)
            .fromTo(
              core,
              { "--hit": 1 },
              { "--hit": 0, duration: 0.55, ease: "power2.out", immediateRender: false },
              t + 0.95,
            );
        });
        tl.add(() => {
          signal.play(0);
        }, ">");
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

  return (
    <section className="lp-section" id="problem" ref={root}>
      <div className="lp-shell">
        <p className="lp-eyebrow">
          <span className="lp-eyebrow__n">01</span> The problem
        </p>
        <h2 className="lp-h2" data-p-h2>
          Fraud doesn't happen <em>in one place.</em>
        </h2>
        <p className="lp-lede" data-p-lede>
          One operation reaches a person by SMS, moves them to WhatsApp, sends a PDF that
          looks like a warrant, puts a voice on the line for two hours, and collects on a
          UPI ID. Eleven front doors, one crew — and almost every tool built to stop it
          is watching exactly one of them.
        </p>

        <div className="lp-web" data-p-stage aria-hidden="true">
          <svg className="lp-web__svg" viewBox={`0 0 ${W} ${H}`} fill="none">
            {CHANNELS.map((c) => (
              <path key={c.id} className="lp-web__edge" data-p-edge d={toCore(c)} />
            ))}
            {CHANNELS.map((c, i) => (
              <circle key={`s-${c.id}`} className="lp-web__signal" r={3.2} cx={c.x} cy={c.y} data-p-signal={i} />
            ))}
          </svg>

          <div className="lp-web__nodes">
            {CHANNELS.map((c) => (
              <div
                key={c.id}
                className="lp-web__slot"
                style={{ left: `${(c.x / W) * 100}%`, top: `${(c.y / H) * 100}%` }}
              >
                <div className="lp-web__chip" data-p-chip>
                  <c.icon size={14} strokeWidth={1.7} aria-hidden="true" />
                  {c.label}
                </div>
              </div>
            ))}

            <div className="lp-web__slot lp-web__slot--core">
              <div className="lp-web__core" data-p-core>
                <span className="lp-web__coren">One operation</span>
                <span className="lp-web__cores">Eleven surfaces</span>
              </div>
            </div>
          </div>
        </div>

        <p className="lp-note" data-p-verdict>
          <strong>The attack is joined up. The defence has not been.</strong> A URL
          scanner never hears the call. A call blocker never reads the PDF. The link
          between them is the case, and the case is the thing nobody was holding.
        </p>
      </div>
    </section>
  );
}
