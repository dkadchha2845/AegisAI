/**
 * "Anything can be evidence."
 *
 * Eight artefacts, and for each one the thing AegisAI actually does with it.
 * Not eight feature cards: eight *objects*, each arriving the way that object
 * would — the screenshot is uncovered top to bottom like a scan, the QR turns
 * as it lands, the URL slides in from the left the way a link is pasted, the
 * APK drops. The choreography is the content. Eight identical fades would
 * say "here are eight features"; this says "all of this is admissible".
 *
 * **Why the copy is this specific.** Every line names a real behaviour of the
 * pipeline, including the constraints — the URL agent's redirect re-resolution
 * and the APK agent's network-less container are security properties, not
 * marketing. A capability list that a reader cannot check is the kind of claim
 * this product exists to catch.
 *
 * The grid is deliberately irregular: three columns with alternating vertical
 * offsets, so the eye moves through the set instead of scanning a table.
 */

import { useEffect, useRef } from "react";
import {
  FileCode2,
  Image as ImageIcon,
  Link2,
  Mail,
  Mic,
  PhoneCall,
  QrCode,
  Video,
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

interface Artefact {
  id: string;
  name: string;
  icon: typeof QrCode;
  body: string;
  /** This artefact's own entrance. The variety is the section's argument. */
  from: gsap.TweenVars;
}

const ARTEFACTS: Artefact[] = [
  {
    id: "shot",
    name: "Screenshot",
    icon: ImageIcon,
    body: "OCR and layout analysis pull the number, the UPI ID and the claim out of the pixels — then the extracted text is quoted in as untrusted data, never as instructions.",
    // Uncovered top to bottom, like something being scanned.
    from: { clipPath: "inset(0 0 100% 0)", opacity: 0, duration: 0.9 },
  },
  {
    id: "qr",
    name: "QR code",
    icon: QrCode,
    body: "Decoded, and then the payload is treated as what it is: a URL, a UPI handle or a payment intent, put through the agent that owns that type.",
    from: { scale: 0.55, rotate: -14, opacity: 0, filter: "blur(10px)" },
  },
  {
    id: "url",
    name: "Link",
    icon: Link2,
    body: "Fetched behind an SSRF guard that blocks private ranges and re-resolves DNS after every redirect. Domain age, registrar, certificate and redirect chain come back as features.",
    from: { x: -70, opacity: 0, filter: "blur(12px)" },
  },
  {
    id: "email",
    name: "Email",
    icon: Mail,
    body: "Headers first — display-name spoofing, failed authentication, reply-to mismatch — then every link in the body through the same guarded fetch.",
    from: { x: 70, opacity: 0, filter: "blur(12px)" },
  },
  {
    id: "audio",
    name: "Voice note",
    icon: Mic,
    body: "Transcribed, then read as a script rather than as a topic: which stage of the playbook is this, and how close is it to one we have seen before?",
    from: { y: 64, opacity: 0, filter: "blur(14px)" },
  },
  {
    id: "video",
    name: "Video",
    icon: Video,
    body: "Frames sampled for on-screen text and impersonated insignia; the audio track is split out and handled exactly like a call.",
    from: { scale: 1.22, opacity: 0, filter: "blur(16px)" },
  },
  {
    id: "apk",
    name: "APK",
    icon: FileCode2,
    body: "Static analysis only, in a network-less container on a read-only mount. Permissions, certificate, exported components — the file is never executed.",
    from: { y: -64, rotate: 4, opacity: 0, filter: "blur(10px)" },
  },
  {
    id: "call",
    name: "Live call",
    icon: PhoneCall,
    body: "Streamed rather than submitted. Stage, coercion index and the forecast update every few seconds while the call is still running.",
    from: { scale: 0.7, opacity: 0, filter: "blur(12px)" },
  },
];

export function EvidenceSection() {
  const root = useRef<HTMLElement>(null);

  useEffect(() => {
    const el = root.current;
    if (!el || reduced()) return;
    let cancelled = false;
    const teardown: (() => void)[] = [];

    void fontsReady().then(() => {
      if (cancelled) return;
      const ctx = gsap.context(() => {
        const h = split(el.querySelector("[data-e-h2]"), "lines");
        gsap.from(h.lines, {
          yPercent: 116,
          opacity: 0,
          filter: "blur(12px)",
          duration: DUR.slow,
          ease: EASE.out,
          stagger: 0.09,
          scrollTrigger: { trigger: el, start: "top 70%", once: true },
          onComplete: () => h.revert(),
        });
        gsap.from("[data-e-lede]", {
          opacity: 0,
          y: 24,
          filter: "blur(8px)",
          duration: DUR.reveal,
          ease: EASE.out,
          scrollTrigger: { trigger: "[data-e-lede]", start: "top 86%", once: true },
        });

        /* Each artefact triggers on its own arrival rather than on the grid's,
           so a tall column does not fire its bottom card while it is still two
           screens below the fold. */
        gsap.utils.toArray<HTMLElement>("[data-e-card]").forEach((card, i) => {
          const spec = ARTEFACTS[i];
          gsap.from(card, {
            ...spec.from,
            duration: (spec.from.duration as number) ?? DUR.slow,
            ease: EASE.out,
            clearProps: "filter,clipPath,transform",
            scrollTrigger: { trigger: card, start: "top 90%", once: true },
          });
        });

        gsap.from("[data-e-foot]", {
          opacity: 0,
          y: 20,
          duration: DUR.reveal,
          ease: EASE.out,
          scrollTrigger: { trigger: "[data-e-foot]", start: "top 90%", once: true },
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

  return (
    <section className="lp-section" id="evidence" ref={root}>
      <div className="lp-shell">
        <p className="lp-eyebrow">
          <span className="lp-eyebrow__n">02</span> Evidence
        </p>
        <h2 className="lp-h2 lp-h2--big" data-e-h2>
          Anything can be <em>evidence.</em>
        </h2>
        <p className="lp-lede" data-e-lede>
          A screenshot, a link, a voice note, an installer, a call still in progress —
          they all enter the same graph of agents and leave it the same way: a score,
          the signals behind it, and what to do next.
        </p>

        <div className="lp-eg">
          {/* The card is wrapped rather than offset directly: the grid's
              staggered rhythm is a `translateY` on the cell, and GSAP owns the
              whole `transform` of whatever it animates. Animating the card
              itself would wipe the offset the moment the entrance finished. */}
          {ARTEFACTS.map((a) => (
            <div className="lp-eg__cell" key={a.id}>
              <article className="lp-card lp-card--hover lp-eg__card" data-e-card>
                <span className="lp-eg__icon">
                  <a.icon size={17} strokeWidth={1.7} aria-hidden="true" />
                </span>
                <h3 className="lp-card__title">{a.name}</h3>
                <p className="lp-card__body">{a.body}</p>
              </article>
            </div>
          ))}
        </div>

        <p className="lp-note" data-e-foot>
          <strong>Eight front doors, one engine.</strong> Every one of them is validated
          by magic bytes rather than by its extension, size-capped, and handled as
          hostile until it has proved otherwise.
        </p>
      </div>
    </section>
  );
}
