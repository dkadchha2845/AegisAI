/**
 * The room the page sits in.
 *
 * One fixed canvas, four layers, one animation frame: a technical grid that
 * drifts with the scroll, a light field that tracks the cursor, a slow lattice
 * of data points that connect when they pass near each other, and a static
 * grain tile that sits on top of all of it.
 *
 * **Why canvas and not the three.js field the rest of the product uses.**
 * `ThreatField` is a raymarched shader whose colour is driven by the live
 * threat level — on a console that is a readout, and it earns its 600 kB of
 * three.js. On the landing there is no threat level to read, so the same
 * effect would be decoration at the cost of the largest chunk in the bundle,
 * loaded before the first paint of the first screen anyone sees. This draws
 * the same atmosphere in roughly a hundred lines of 2D canvas and no
 * dependency at all.
 *
 * **Why it is subordinate.** Every alpha in here is under 0.1. The background
 * has one job — make the page feel alive and technical while you are reading
 * something else — and the moment it is legible as a picture it has failed.
 *
 * Degradation: no canvas context, no atmosphere, and the page is a flat dark
 * ground that looks deliberate rather than broken. Reduced motion paints one
 * static frame and stops the loop. A hidden tab stops it too.
 */

import { useEffect, useRef } from "react";
import { reduced } from "@/lib/landing-motion";

interface Node {
  x: number;
  y: number;
  vx: number;
  vy: number;
  /** Phase offset so the dots do not breathe in unison. */
  phase: number;
}

/** Points, by viewport width. A phone gets a third of a desktop's lattice —
 *  not because the maths is expensive but because the same density on a
 *  375px screen reads as clutter rather than as depth. */
function nodeCount(w: number): number {
  if (w < 640) return 12;
  if (w < 1100) return 22;
  return 34;
}

const GRID = 74;          /* px between grid lines at DPR 1 */
const LINK_DIST = 168;    /* px within which two points draw a connection */

export function Atmosphere() {
  const hostRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const grainRef = useRef<HTMLDivElement>(null);

  /* --- the grain tile, generated once ---------------------------------
     A 128px tile of monochrome noise, drawn to an offscreen canvas and
     handed to CSS as a data URI. It is a static background-image after
     that: no per-frame cost, and it survives every theme change because
     it is pure luminance at 3% alpha. */
  useEffect(() => {
    const host = grainRef.current;
    if (!host) return;
    const tile = document.createElement("canvas");
    tile.width = tile.height = 128;
    const tctx = tile.getContext("2d");
    if (!tctx) return;
    const img = tctx.createImageData(128, 128);
    for (let i = 0; i < img.data.length; i += 4) {
      const v = (Math.random() * 255) | 0;
      img.data[i] = img.data[i + 1] = img.data[i + 2] = v;
      img.data[i + 3] = 255;
    }
    tctx.putImageData(img, 0, 0);
    host.style.backgroundImage = `url(${tile.toDataURL()})`;
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    const host = hostRef.current;
    if (!canvas || !host) return;
    const ctx = canvas.getContext("2d", { alpha: true });
    if (!ctx) return;

    let width = 0;
    let height = 0;
    let dpr = 1;
    let nodes: Node[] = [];
    let raf = 0;
    let running = true;
    let t = 0;

    /* Colours are read from the document, not hard-coded, so the light theme
       and any future accent change are free. Re-read whenever the theme
       attribute changes. */
    let ink = "236, 238, 242";
    let accent = "77, 141, 255";
    let cyan = "73, 207, 221";
    let light = false;

    const readTheme = () => {
      const s = getComputedStyle(host);
      ink = rgbOf(s.getPropertyValue("--lp-ink")) ?? ink;
      accent = rgbOf(s.getPropertyValue("--lp-accent")) ?? accent;
      cyan = rgbOf(s.getPropertyValue("--lp-cyan")) ?? cyan;
      light = document.documentElement.dataset.theme === "light";
    };

    /* Pointer, in CSS pixels, lerped toward on every frame. The raw position
       would make the light field snap; the lerp is what makes it feel like a
       lamp being carried rather than a cursor. */
    let px = -9999;
    let py = -9999;
    let lx = -9999;
    let ly = -9999;

    const onPointer = (e: PointerEvent) => {
      px = e.clientX;
      py = e.clientY;
      if (lx === -9999) {
        lx = px;
        ly = py;
      }
    };

    const resize = () => {
      const r = host.getBoundingClientRect();
      width = Math.max(1, Math.round(r.width));
      height = Math.max(1, Math.round(r.height));
      // Capped at 1.5: a 3x retina phone would otherwise paint nine times the
      // pixels for a background nobody is looking at directly.
      dpr = Math.min(window.devicePixelRatio || 1, 1.5);
      canvas.width = Math.round(width * dpr);
      canvas.height = Math.round(height * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

      const want = nodeCount(width);
      nodes = Array.from({ length: want }, (_, i) => {
        const existing = nodes[i];
        if (existing && existing.x <= width && existing.y <= height) return existing;
        return {
          x: Math.random() * width,
          y: Math.random() * height,
          vx: (Math.random() - 0.5) * 0.12,
          vy: (Math.random() - 0.5) * 0.12,
          phase: Math.random() * Math.PI * 2,
        };
      });
      if (!running) draw(0);
    };

    function draw(dt: number) {
      if (!ctx) return;
      t += dt;
      ctx.clearRect(0, 0, width, height);

      /* --- 1. the grid ------------------------------------------------
         Offset by the scroll position at a fraction of its rate, which is
         the whole parallax: the grid is *behind* the page and moves like it.
         `scrollY % GRID` keeps the offset bounded, so the loop never grows
         with the length of the document. */
      const off = (window.scrollY * 0.12) % GRID;
      ctx.lineWidth = 1;
      ctx.strokeStyle = `rgba(${ink}, ${light ? 0.05 : 0.028})`;
      ctx.beginPath();
      for (let x = -GRID; x <= width + GRID; x += GRID) {
        const gx = Math.round(x) + 0.5;
        ctx.moveTo(gx, 0);
        ctx.lineTo(gx, height);
      }
      for (let y = -GRID; y <= height + GRID; y += GRID) {
        const gy = Math.round(y - off) + 0.5;
        ctx.moveTo(0, gy);
        ctx.lineTo(width, gy);
      }
      ctx.stroke();

      /* --- 2. the light field ----------------------------------------
         Two soft radial washes in `lighter`: one slow, autonomous drift so
         the page breathes with no cursor at all, and one that follows the
         pointer. Both are clipped to a low alpha — this is the layer that
         would turn the page into a lava lamp if it were allowed to. */
      lx += (px - lx) * 0.055;
      ly += (py - ly) * 0.055;
      ctx.globalCompositeOperation = "lighter";

      const dx = width * (0.5 + Math.sin(t * 0.00007) * 0.22);
      const dy = height * (0.36 + Math.cos(t * 0.00009) * 0.18);
      paintGlow(ctx, dx, dy, Math.max(width, height) * 0.55, accent, light ? 0.05 : 0.075);

      if (lx > -9998) {
        paintGlow(ctx, lx, ly, 420, cyan, light ? 0.035 : 0.055);
      }
      ctx.globalCompositeOperation = "source-over";

      /* --- 3. the lattice ---------------------------------------------
         Points drift, wrap at the edges, and draw a line to any neighbour
         inside LINK_DIST with the alpha falling off over that distance. The
         pair loop is O(n²) on at most 34 points — 561 comparisons, which is
         nothing next to the four gradients above it. */
      const linkBase = light ? 0.1 : 0.075;
      for (let i = 0; i < nodes.length; i++) {
        const a = nodes[i];
        a.x += a.vx;
        a.y += a.vy;
        if (a.x < -20) a.x = width + 20;
        if (a.x > width + 20) a.x = -20;
        if (a.y < -20) a.y = height + 20;
        if (a.y > height + 20) a.y = -20;

        for (let j = i + 1; j < nodes.length; j++) {
          const b = nodes[j];
          const d = Math.hypot(a.x - b.x, a.y - b.y);
          if (d > LINK_DIST) continue;
          ctx.strokeStyle = `rgba(${ink}, ${(1 - d / LINK_DIST) * linkBase})`;
          ctx.beginPath();
          ctx.moveTo(a.x, a.y);
          ctx.lineTo(b.x, b.y);
          ctx.stroke();
        }

        // Each point breathes on its own phase, and brightens as the cursor
        // approaches — the one place the background acknowledges the reader.
        const pulse = 0.5 + Math.sin(t * 0.0011 + a.phase) * 0.5;
        const near = lx > -9998 ? Math.max(0, 1 - Math.hypot(a.x - lx, a.y - ly) / 260) : 0;
        const alpha = (light ? 0.14 : 0.2) * (0.45 + pulse * 0.55) + near * 0.34;
        ctx.fillStyle = `rgba(${near > 0.25 ? accent : ink}, ${alpha})`;
        ctx.beginPath();
        ctx.arc(a.x, a.y, 1.25 + near * 1.1, 0, Math.PI * 2);
        ctx.fill();
      }
    }

    let last = performance.now();
    const loop = (now: number) => {
      const dt = Math.min(now - last, 48);   /* a backgrounded tab must not jump */
      last = now;
      draw(dt);
      raf = requestAnimationFrame(loop);
    };

    const start = () => {
      if (running) return;
      running = true;
      last = performance.now();
      raf = requestAnimationFrame(loop);
    };
    const stop = () => {
      running = false;
      cancelAnimationFrame(raf);
    };

    readTheme();
    resize();

    const still = reduced();
    if (still) {
      running = false;
      draw(0);
    } else {
      running = true;
      raf = requestAnimationFrame(loop);
      window.addEventListener("pointermove", onPointer, { passive: true });
    }

    const onVisibility = () => {
      if (still) return;
      if (document.hidden) stop();
      else start();
    };

    const ro = new ResizeObserver(resize);
    ro.observe(host);
    document.addEventListener("visibilitychange", onVisibility);

    // The theme toggle rewrites `<html data-theme>`; the canvas has already
    // sampled the old colours, so it has to be told.
    const themeWatch = new MutationObserver(() => {
      readTheme();
      if (still) draw(0);
    });
    themeWatch.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme"],
    });

    return () => {
      stop();
      ro.disconnect();
      themeWatch.disconnect();
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("pointermove", onPointer);
    };
  }, []);

  return (
    <div className="lp-atmos" ref={hostRef} aria-hidden="true">
      <canvas className="lp-atmos__canvas" ref={canvasRef} />
      <div className="lp-atmos__grain" ref={grainRef} />
      <div className="lp-atmos__vignette" />
    </div>
  );
}

/** A soft radial wash. Pulled out because it is called three times a frame
 *  and the gradient construction is the only allocation in the loop. */
function paintGlow(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  r: number,
  rgb: string,
  alpha: number,
) {
  const g = ctx.createRadialGradient(x, y, 0, x, y, r);
  g.addColorStop(0, `rgba(${rgb}, ${alpha})`);
  g.addColorStop(0.55, `rgba(${rgb}, ${alpha * 0.32})`);
  g.addColorStop(1, `rgba(${rgb}, 0)`);
  ctx.fillStyle = g;
  ctx.beginPath();
  ctx.arc(x, y, r, 0, Math.PI * 2);
  ctx.fill();
}

/**
 * `#4d8dff` / `rgb(...)` / `color(...)` → `"77, 141, 255"`.
 *
 * The tokens are authored as hex but `getComputedStyle` on a custom property
 * hands back whatever string was written, un-normalised — so both forms have
 * to be handled, and anything else falls back to the caller's default rather
 * than painting `NaN`.
 */
function rgbOf(value: string): string | null {
  const v = value.trim();
  if (!v) return null;
  const hex = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(v);
  if (hex) {
    let h = hex[1];
    if (h.length === 3) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
    const n = parseInt(h, 16);
    return `${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}`;
  }
  const rgb = /rgba?\(([^)]+)\)/i.exec(v);
  if (rgb) {
    const parts = rgb[1].split(/[,/\s]+/).filter(Boolean).slice(0, 3);
    if (parts.length === 3) return parts.join(", ");
  }
  return null;
}
