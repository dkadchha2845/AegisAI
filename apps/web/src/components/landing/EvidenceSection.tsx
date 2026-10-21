/**
 * "Anything can be evidence."
 *
 * Eight things a person is actually sent, and for each one what AegisAI does
 * with it **today**. Every card is checked against the code it describes:
 *
 *   Screenshot, QR code  `/api/analyze/image` — OCR, plus QR decoding
 *   Voice note           `/api/analyze/audio` — Whisper, then the analyzer
 *   Live call            the live session — stage, coercion, forecast per turn
 *   Message, Document    `/api/analyze/text`, `/api/analyze/file`
 *   UPI ID               `engine/upi.py` — structural checks, no network call
 *   Caller number        `engine/spoofing.py` — four checks, capped in fusion
 *
 * An earlier version of this section also promised a link scanner with an SSRF
 * guard, email-header analysis, video frames and APK static analysis. None of
 * those is built — the link scanner is a planned task, the other three are
 * parked — so none of them is here. A capability list a reader cannot check is
 * the kind of claim this product exists to catch.
 *
 * **Layout: an aligned grid.** Four columns, two rows, every card the same
 * height, the reader's name pinned to the bottom of each. The previous
 * staggered offsets read as misalignment rather than as rhythm, and because a
 * `translateY` takes no layout space, the note below the grid ended up beside
 * the lowest cards instead of under them.
 *
 * **Motion: one entrance, eight gestures.** Each row of cards rises into place
 * together, left to right, as the row reaches the viewport — one consistent
 * movement, so the grid reads as a set. The individuality lives in the icon:
 * the screenshot is scanned top to bottom, the QR code turns as it lands, the
 * voice note swells like a level meter, the live call rings. The objects still
 * arrive the way those objects would, without the boxes leaving their grid.
 */

import { useEffect, useRef } from "react";
import {
  FileText,
  Hash,
  Image as ImageIcon,
  IndianRupee,
  MessageSquare,
  Mic,
  PhoneCall,
  QrCode,
} from "lucide-react";
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

interface Artefact {
  id: string;
  name: string;
  icon: typeof QrCode;
  body: string;
  /** What reads it, named so a reader can go and check. */
  reader: string;
  /** The icon's own arrival. The card's is shared; this is not. */
  gesture: gsap.TweenVars;
}

const ARTEFACTS: Artefact[] = [
  {
    id: "shot",
    name: "Screenshot",
    icon: ImageIcon,
    body: "OCR reads the text out of the pixels — a fake notice, a payment screen, a chat — and it is scored exactly like a pasted message. With no OCR engine installed, it says so instead of guessing.",
    reader: "Tesseract · EasyOCR",
    gesture: { clipPath: "inset(0 0 100% 0)", duration: 0.7, ease: "power2.inOut" },
  },
  {
    id: "qr",
    name: "QR code",
    icon: QrCode,
    body: "Decoded from the same upload. A payment link inside it is checked like one that was typed in — including the classic lie that scanning it will pay you.",
    reader: "QR decode",
    gesture: { rotate: -90, scale: 0.6, opacity: 0, duration: 0.7, ease: "back.out(1.6)" },
  },
  {
    id: "audio",
    name: "Voice note",
    icon: Mic,
    body: "Transcribed, then read as a script rather than as a topic: which stage of the scam playbook it is at, and how close it runs to a script seen before.",
    reader: "Whisper",
    gesture: { scaleY: 0.2, opacity: 0, duration: 0.6, ease: "back.out(2.2)", transformOrigin: "50% 100%" },
  },
  {
    id: "call",
    name: "Live call",
    icon: PhoneCall,
    body: "Followed turn by turn while the conversation is still happening. The scam stage, a coercion index and a forecast of the next move update with every line.",
    reader: "Live session",
    gesture: { rotate: -18, opacity: 0, duration: 0.55, ease: "elastic.out(1.1, 0.4)" },
  },
  {
    id: "text",
    name: "Message",
    icon: MessageSquare,
    body: "An SMS, a WhatsApp forward, an email body — pasted as text, in English, Hindi or Hinglish, and placed on the scam's script: authority, fear, isolation, payment.",
    reader: "Text analyzer",
    gesture: { x: -12, opacity: 0, duration: 0.5 },
  },
  {
    id: "upi",
    name: "UPI ID",
    icon: IndianRupee,
    body: "Checked for what the ID says about itself: an institution's name in a personal handle, an unrecognised payment app, a mobile number posing as an office. No blocklist to go stale.",
    reader: "Structural checks",
    gesture: { y: 10, opacity: 0, duration: 0.5 },
  },
  {
    id: "caller",
    name: "Caller number",
    icon: Hash,
    body: "Reported numbers, international routing, VoIP prefixes, and whether the caller ID fits the authority claimed. Metadata can raise a score; it can never make one critical alone.",
    reader: "Spoofing checks",
    gesture: { scale: 0.5, opacity: 0, duration: 0.5, ease: "back.out(1.8)" },
  },
  {
    id: "doc",
    name: "Document",
    icon: FileText,
    body: "A chat export or a call transcript — .txt, .csv, .json, .vtt or .srt — read in full and scored by the same analyzer as everything else on this page.",
    reader: "File reader",
    gesture: { clipPath: "inset(0 100% 0 0)", duration: 0.6, ease: "power2.inOut" },
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

        /* The cards start hidden and are revealed a row at a time. `batch`
           groups whichever cards cross the line in the same frame — a whole
           row on a four-column screen, a pair on two columns, one on a phone —
           so the stagger always runs along the row the reader is looking at. */
        const cards = gsap.utils.toArray<HTMLElement>("[data-e-card]");
        gsap.set(cards, { opacity: 0, y: 34 });
        ScrollTrigger.batch(cards, {
          start: "top 88%",
          once: true,
          onEnter: (batch) => {
            gsap.to(batch, {
              opacity: 1,
              y: 0,
              duration: DUR.reveal,
              ease: EASE.out,
              stagger: 0.09,
              clearProps: "transform,opacity",
            });
            batch.forEach((card, k) => {
              const i = cards.indexOf(card as HTMLElement);
              const icon = card.querySelector("[data-e-icon]");
              const spec = ARTEFACTS[i];
              if (!icon || !spec) return;
              gsap.from(icon, {
                ease: EASE.out,
                ...spec.gesture,
                delay: 0.18 + k * 0.09,
                clearProps: "all",
              });
            });
          },
        });

        gsap.from("[data-e-foot]", {
          opacity: 0,
          y: 20,
          duration: DUR.reveal,
          ease: EASE.out,
          scrollTrigger: { trigger: "[data-e-foot]", start: "top 92%", once: true },
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
          A screenshot, a voice note, a UPI ID, a call still in progress — each is
          read for what it is, then scored by the same engine, which hands back the
          same three things: a score, the signals behind it, and what to do next.
        </p>

        <div className="lp-eg">
          {ARTEFACTS.map((a) => (
            <article className="lp-card lp-card--hover lp-eg__card" data-e-card key={a.id}>
              <span className="lp-eg__icon" data-e-icon>
                <a.icon size={18} strokeWidth={1.7} aria-hidden="true" />
              </span>
              <h3 className="lp-card__title">{a.name}</h3>
              <p className="lp-card__body">{a.body}</p>
              <p className="lp-eg__reader">{a.reader}</p>
            </article>
          ))}
        </div>

        <p className="lp-note" data-e-foot>
          <strong>Eight ways in, one engine.</strong> Every one of them ends in the
          same scoring code, so a screenshot and a pasted message cannot disagree.
          Uploads are size-capped, and when a reader is missing — no OCR, no
          speech-to-text — the answer says so rather than guessing.
        </p>
      </div>
    </section>
  );
}
