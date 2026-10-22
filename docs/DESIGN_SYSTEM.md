# AegisAI — Design System

| | |
|---|---|
| Version | 1.0 — 2026-10-22 (T-03) |
| Status | ✅ Approved by the owner, 2026-10-22 |
| Source of truth | [`apps/web/src/styles/tokens.css`](../apps/web/src/styles/tokens.css) (tokens) · [`primitives.css`](../apps/web/src/styles/primitives.css) (primitives) · [`components/ui/`](../apps/web/src/components/ui/) |
| Scope | The product (every route inside the app shell). The landing page has its own scoped surface — §8 |

This document describes the design system the product **already has**, and
lists — as a gap table, §9 — what the brief requires and the product lacks.
Every token below is quoted with the value it has in `tokens.css` on
2026-10-22. Every contrast ratio is **measured** (WCAG 2.1 relative-luminance
formula, translucent tints composited over the surface they sit on), not
asserted.

The rule for code (brief §8): UI uses these tokens and components only — no
one-off colours, sizes or radii.

---

## 1. Visual direction

**An instrument, not a dashboard.** The reference points are Linear and
Stripe, not the glassmorphic "mission control" look. Three reasons, from the
header of `tokens.css`:

1. **Colour has to mean something.** Chrome is near-monochrome; saturation is
   reserved almost entirely for the threat ramp. When the meter goes red it is
   the only red on screen.
2. **Restraint is the differentiator.** Examiners have seen many dark
   dashboards with purple gradients.
3. **Every number is evidence.** Numerals use tabular figures so they read as
   measurement.

Serious, trustworthy, calm, high contrast. **Dark is the default theme**; a
light theme exists for a projector in a bright room, set by
`html[data-theme="light"]`.

---

## 2. Tokens

### 2.1 Typography

| Token | Value | Use |
|---|---|---|
| `--font-display` | `Satoshi, ui-sans-serif, system-ui, -apple-system, sans-serif` | Headings, UI |
| `--font-body` | `var(--font-display)` | Body |
| `--font-mono` | `"DM Sans", sans-serif` | Numbers and data, with `font-variant-numeric: tabular-nums` |

> **Mismatch, recorded:** the comment above these tokens says "JetBrains Mono
> (data)", but `--font-mono` is DM Sans — a proportional face. Tabular
> figures keep numbers aligned; letters are not fixed-width. The landing page
> defines a real monospace stack of its own (`--lp-mono`, §8). Which is
> intended is a decision for T-16.

**Type scale** — a 1.25 ratio, clamped at the top for projector safety:

| Token | Value | Size | Use |
|---|---|---|---|
| `--t-2xs` | `0.6875rem` | 11 px | labels, axis ticks |
| `--t-xs` | `0.75rem` | 12 px | metadata |
| `--t-sm` | `0.8125rem` | 13 px | small body, transcript, buttons |
| `--t-base` | `0.9375rem` | 15 px | body |
| `--t-md` | `1.125rem` | 18 px | — |
| `--t-lg` | `1.5rem` | 24 px | — |
| `--t-xl` | `2rem` | 32 px | — |
| `--t-2xl` | `clamp(2.5rem, 4vw, 3.5rem)` | 40–56 px | the threat score |
| `--t-3xl` | `clamp(3.5rem, 6vw, 5rem)` | 56–80 px | display |
| `--tracking-tight` | `-0.02em` | | headings |
| `--tracking-label` | `0.09em` | | uppercase micro-labels |

### 2.2 Spacing — 4 px base, 8 px rhythm

| `--s-1` | `--s-2` | `--s-3` | `--s-4` | `--s-5` | `--s-6` | `--s-7` | `--s-8` |
|---|---|---|---|---|---|---|---|
| `4px` | `8px` | `12px` | `16px` | `24px` | `32px` | `48px` | `64px` |

### 2.3 Radius — small and consistent

| `--r-xs` | `--r-sm` | `--r-md` | `--r-lg` | `--r-pill` |
|---|---|---|---|---|
| `4px` | `6px` | `10px` | `14px` | `999px` |

Big radii read as "app", not "instrument". Buttons are pills; cards and panels
use `--r-md`/`--r-lg`; chips use `--r-xs`.

### 2.4 Shadows — tight and dark, no coloured glows

| Token | Dark | Light |
|---|---|---|
| `--shadow-sm` | `0 1px 2px rgba(0, 0, 0, 0.4)` | `0 1px 2px rgba(15, 23, 42, 0.08)` |
| `--shadow-md` | `0 4px 16px rgba(0, 0, 0, 0.45)` | `0 4px 16px rgba(15, 23, 42, 0.10)` |
| `--shadow-lg` | `0 16px 48px rgba(0, 0, 0, 0.55)` | `0 16px 48px rgba(15, 23, 42, 0.14)` |

### 2.5 Motion — fast and physical

| Token | Value | Use |
|---|---|---|
| `--ease-out` | `cubic-bezier(0.16, 1, 0.3, 1)` | entrances (expo out) |
| `--ease-in-out` | `cubic-bezier(0.76, 0, 0.24, 1)` | state changes |
| `--ease-spring` | `cubic-bezier(0.34, 1.56, 0.64, 1)` | overshoot — "stamps" only |
| `--t-instant` | `90ms` | press feedback |
| `--t-fast` | `180ms` | hover, colour |
| `--t-med` | `320ms` | panels, layout |
| `--t-slow` | `620ms` | narrative entrances |

The meter must feel wired to the data, so its response is near-instant;
entrances are slower because they are narrative. **Reduced motion** is
honoured globally (`global.css`): with `prefers-reduced-motion` or
`html[data-motion="reduced"]`, animation and transition durations collapse to
0.001 ms and delays to 0.

### 2.6 Containers, focus, layers

| Token | Value | Use |
|---|---|---|
| `--w-doc` | `820px` | prose-led pages |
| `--w-app` | `1180px` | the standard workspace |
| `--w-wide` | `1480px` | graph and table screens |
| `--focus-ring` | `2px` | focus outline width |
| `--focus-offset` | `2px` | focus outline offset |
| `--z-base` · `--z-sticky` · `--z-overlay` · `--z-modal` · `--z-toast` · `--z-vignette` | `1` · `50` · `400` · `800` · `900` · `950` | stacking |

### 2.7 Colour — neutrals and inks

| Token | Dark (default) | Light | Use |
|---|---|---|---|
| `--bg` | `#08090b` | `#f7f8fa` | page ground |
| `--bg-raised` | `#0c0e11` | `#ffffff` | raised ground |
| `--panel` | `#101317` | `#ffffff` | cards, panels |
| `--panel-hover` | `#151920` | `#f1f3f6` | hovered / darkest surface |
| `--line` | `rgba(255, 255, 255, 0.07)` | `rgba(15, 23, 42, 0.10)` | hairlines |
| `--line-strong` | `rgba(255, 255, 255, 0.13)` | `rgba(15, 23, 42, 0.18)` | borders |
| `--ink` | `#e8eaed` | `#16181d` | primary text |
| `--ink-muted` | `#9198a3` | `#5b6472` | secondary text |
| `--ink-faint` | `#7d8492` | `#666e7d` | captions, axis labels |
| `--ink-ghost` | `#5f6672` | `#8a93a1` | **non-text only**: hairlines, disabled glyphs |
| `--accent` | `#4d8dff` | `#2d69d9` | the single UI accent: focus, active, links. **Never threat** |
| `--accent-dim` | `rgba(77, 141, 255, 0.14)` | `rgba(45, 105, 217, 0.12)` | accent wash |
| `--accent-ink` | `var(--accent)` | `#275cbd` | accent used as text on a tint |

### 2.8 Colour — the threat ramp

The only saturated colours on screen. Each level has three roles: **fill**
(meters, bars, map bubbles), **dim** (a tint behind it) and **ink** (the level
written as text on its own tint). On near-black the fill and the ink coincide;
on paper one value cannot do both jobs, so the light theme deepens the inks.

| Level | Fill — dark | Fill — light | Dim — dark | Dim — light | Ink — dark | Ink — light |
|---|---|---|---|---|---|---|
| CALM | `#35c08b` | `#187d58` | `rgba(53, 192, 139, 0.13)` | `rgba(24, 125, 88, 0.12)` | = fill | `#156d4d` |
| WATCH | `#b8c34a` | `#6b731b` | `rgba(184, 195, 74, 0.13)` | `rgba(107, 115, 27, 0.12)` | = fill | `#5e6618` |
| ELEVATED | `#e0a33c` | `#956416` | `rgba(224, 163, 60, 0.13)` | `rgba(149, 100, 22, 0.12)` | = fill | `#835813` |
| HIGH | `#ec6a45` | `#bf4727` | `rgba(236, 106, 69, 0.14)` | `rgba(191, 71, 39, 0.12)` | = fill | `#a83e22` |
| CRITICAL | `#f2473f` | `#d22a22` | `rgba(242, 71, 63, 0.16)` | `rgba(210, 42, 34, 0.13)` | `color-mix(in srgb, var(--critical) 86%, white)` → `#f4615a` | `#b6241d` |

Tokens: `--calm`, `--watch`, `--elevated`, `--high`, `--critical`; `--*-dim`;
`--*-ink`; aliases `--safe: var(--calm)` and `--danger: var(--critical)`.

**The current level is global.** The app sets `html[data-threat="…"]`, which
sets `--threat-color` and `--threat-dim` for any component without prop
drilling; with no level set, `--threat-color` is `var(--ink-faint)`.

---

## 3. Risk levels — colour **and** label **and** number

Risk is never shown by colour alone (brief §8, NFR-18). Every risk display
carries all three: the **number** (0–100), the **label** (one of five words,
uppercase), and the **colour** (the ramp). The bands come from
`engine/threat.py` `level_of()`, mirrored in `schema/models.py` and kept in
lockstep by `schema/check_contract.py`:

| Score | Label | Colour token | Brief's name | Meaning to a user |
|---|---|---|---|---|
| 0 – 24.9 | **CALM** | `--calm` | safe | No sign of a scam |
| 25 – 49.9 | **WATCH** | `--watch` | low | Something to be careful about |
| 50 – 69.9 | **ELEVATED** | `--elevated` | medium | Several warning signs |
| 70 – 89.9 | **HIGH** | `--high` | high | Likely a scam — act on the advice |
| 90 – 100 | **CRITICAL** | `--critical` | critical | A scam in progress — stop, do not pay |

Implemented by `components/ui/RiskDial.tsx` (gauge: number, label, confidence
and caption together; an unscored case says "Not scored" rather than showing
0) and the `.chip--caps` badge with `data-risk` (label written in the `-ink`
variant, border and tint in the fill). The brief's names (safe / low /
medium / high / critical) are a mapping, not a rename: the product's five
words are in the contract and on every screen.

---

## 4. Contrast — measured

WCAG 2.1 AA requires 4.5:1 for normal text and 3:1 for large text and
non-text UI. Measured 2026-10-22 from the token values above. A threat-level
ink is measured against the worst surface it is written on: its own tint
composited over `--panel-hover`.

### 4.1 Inks and accent

| Token | Dark: on `--bg` | on `--panel` | on `--panel-hover` | Light: on `--bg` | on `--panel` | on `--panel-hover` | AA text |
|---|---|---|---|---|---|---|---|
| `--ink` | 16.53 | 15.45 | 14.62 | 16.71 | 17.76 | 15.98 | ✅ |
| `--ink-muted` | 6.85 | 6.41 | 6.06 | 5.63 | 5.98 | 5.38 | ✅ |
| `--ink-faint` | 5.30 | 4.96 | 4.69 | 4.83 | 5.13 | 4.62 | ✅ |
| `--ink-ghost` | 3.44 | 3.22 | 3.05 | 2.92 | 3.10 | 2.79 | ❌ — non-text only, by design |
| `--accent` | 6.23 | 5.83 | 5.51 | 4.78 | 5.08 | 4.57 | ✅ |
| `--accent-ink` | — | 5.83 | — | — | 6.27 | — | ✅ |

### 4.2 The threat ramp

| Level | Dark: fill on panel | ink on panel | ink on own tint (worst) | Light: fill on panel | ink on panel | ink on own tint (worst) | AA text |
|---|---|---|---|---|---|---|---|
| CALM | 8.04 | 8.04 | 6.09 | 5.11 | 6.31 | 4.87 | ✅ |
| WATCH | 9.71 | 9.71 | 7.14 | 5.13 | 6.20 | 4.82 | ✅ |
| ELEVATED | 8.40 | 8.40 | 6.35 | 5.11 | 6.23 | 4.83 | ✅ |
| HIGH | 5.95 | 5.95 | 4.73 | 5.07 | 6.22 | 4.75 | ✅ |
| CRITICAL | 5.10 | 5.95 | 4.78 | 5.13 | 6.44 | 4.77 | ✅ |

The lowest text pair in the product is dark-theme HIGH written on its own
tint over a hovered panel: **4.73:1**. Every claim in the comments of
`tokens.css` (e.g. "`--ink-faint` 5.0:1 on panel", "the ramp 5.1:1 on white")
was re-measured and holds.

### 4.3 Controls

| Pair | Dark | Light |
|---|---|---|
| Primary button text on `--accent` (`.btn2--primary`: `#04070f` dark, `#fff` light) | 6.30 | 5.08 |
| Focus ring (`--accent`) against `--panel` — non-text, needs 3:1 | 5.83 | 5.08 |

---

## 5. Primitives that exist

From `primitives.css` and `components/ui/`. Use these; do not restyle them
per page.

| Primitive | Classes / component | Notes |
|---|---|---|
| Page | `.page`, `.page--doc`, `.page--wide`, `.page__head`, `.page__title`, `.page__lede`, `.page__actions`; `ui/PageHeader.tsx` | Width from `--w-doc` / `--w-app` / `--w-wide` |
| Button | `.btn2` + `--primary` · `--ghost` · `--danger` · `--sm` · `--lg` · `--block`; `.iconbtn` | 38 px tall, pill, DM Sans 13 px / 500. `.btn` is a legacy alias |
| Field | `.field`, `.fieldlabel`, `.fieldhint`, `.fieldpair`, `.row--fields`, `.segmented` | Focus: accent border + 3 px `--accent-dim` ring |
| Card / panel | `.card` + `--flush` · `--tight` · `--link`; `.card__title`; `.panel` | |
| Chip / badge | `.chip`, `.badge`, `.chip--caps`, `.chip--link`; `data-risk` for the ramp | Text in `-ink`, border and tint in the fill |
| Tabs | `.tabs`, `.tab` | |
| Table | `.table`, `.tablewrap`; `.admin-table`, `.cb-table` | Two page-specific variants exist (gap) |
| Stat | `.stat`, `.stat__n`, `.stat__l`; `.live-stat`; `.admin-kpi` | Three variants for one idea (gap) |
| Alert | `.alert`, `.alert__title` | |
| Empty state | `ui/States.tsx` `EmptyState`; `.empty` + `__mark` (`--bad`), `__title`, `__body`, `__action`, `--inline` | |
| Loading | `ui/States.tsx` `Skeleton`, `SkeletonRows`, `Spinner`; `.skeleton--line/--text/--block`, `.skelrows` | |
| Error state | `ui/States.tsx` `ErrorState` | |
| Risk gauge | `ui/RiskDial.tsx`; `.riskdial__*` | Number + label + confidence + caption; "Not scored" state |
| Threat meter | `components/ThreatMeter.tsx` (`ThreatMeter`, `ThreatDrivers`) | The live session's meter and its drivers |
| Live panels | `components/Panels.tsx` (`ManipulationMap`, `CoercionSparkline`, `TrustPassport`, `CoachCard`), `ForecastChip.tsx`, `NumberIntelPanel.tsx`, `NarrationPanel.tsx`, `TranscriptPane.tsx` | The live console's instruments |
| Verdict | `.verdict` + `__dial`, `__label`, `__summary`, `__body` | The Analyze result |
| Utility | `.stack`, `.row`, `.muted`, `.faint`, `.small`, `.label`, `.eyebrow`, `.vh` (visually hidden), `.skiplink` | |

---

## 6. Components the brief requires

The brief (§5) lists sixteen. **Have** — a reusable component exists.
**Partial** — the job is done somewhere, but inline in one page or without the
states the brief requires. **Missing** — not built.

| # | Component | Status | Where it is today | Gap |
|---|---|---|---|---|
| 1 | Buttons | **Have** | `.btn2` family, `.iconbtn` — `styles/primitives.css` | — |
| 2 | Inputs | **Have** | `.field`, `.fieldlabel`, `.fieldhint`, `.segmented` — `styles/primitives.css` | No error/invalid style or message pattern |
| 3 | File dropzone | **Partial** | Inline in `pages/Shield.tsx` (`onDrop`, `onDragOver`) and `pages/Investigate.tsx` | Two implementations; no shared component, no rejected-file state |
| 4 | Cards | **Have** | `.card` family, `.panel` — `styles/primitives.css` | Several page-specific cards (`.featurecard`, `.clustercard`, `.home-task`) |
| 5 | Risk badge | **Have** | `.chip--caps` with `data-risk` — `styles/primitives.css` | Not a React component; each page writes the markup |
| 6 | Risk gauge | **Have** | `components/ui/RiskDial.tsx`; `components/ThreatMeter.tsx` (live) | Two gauges for one idea |
| 7 | Timeline (scam stages) | **Partial** | `.live-timeline` inline in `pages/LiveProtection.tsx` (events by time) | No stage-by-stage timeline component; nothing for an investigation's timeline (T-52) |
| 8 | Evidence viewer | **Missing** | — | Nothing shows a submitted image, recording or document with what was extracted from it (T-48) |
| 9 | Agent-trace panel | **Partial** | `AgentRow` inline in `pages/Investigate.tsx` (status, latency) | Not reusable; no graph view, no inputs/outputs on click (T-49) |
| 10 | Case-file viewer | **Partial** | `components/report/InvestigationReport.tsx` | Renders the thin report; no A7 verdicts, entities or hashes yet (T-50) |
| 11 | Tables | **Have** | `.table`, `.tablewrap` — `styles/primitives.css` | Two page variants (`.admin-table`, `.cb-table`); no sort or empty-row pattern |
| 12 | Toasts | **Missing** | — | `--z-toast` is reserved, nothing uses it |
| 13 | Modals | **Partial** | `components/layout/CommandPalette.tsx` (`role="dialog"`, `aria-modal`) | One bespoke dialog; no general modal with focus trap and return |
| 14 | Empty states | **Have** | `EmptyState` — `components/ui/States.tsx` | — |
| 15 | Loading skeletons | **Have** | `Skeleton`, `SkeletonRows`, `Spinner` — `components/ui/States.tsx` | — |
| 16 | Error states | **Have** | `ErrorState` — `components/ui/States.tsx` | — |

**Count: 9 have, 5 partial, 2 missing.** The partial and missing ones are the
scope of T-16.

---

## 7. Layout and accessibility rules

### 7.1 Layout

- **Navigation pattern.** Inside the app, `components/layout/AppShell.tsx`: a
  persistent **sidebar** that owns the left column (brand at the top, live API
  and degradation status in its footer, collapsible — remembered in
  `aegis:sidebar-collapsed`), a **top bar** whose leading edge is the page
  title, and a **command palette**. Navigation is role-aware: one group for a
  citizen, two for an analyst. The landing and sign-in screens render outside
  the shell.
- **Widths.** A page picks one of three: `--w-doc` 820 px (prose),
  `--w-app` 1180 px (workspace), `--w-wide` 1480 px (graphs and tables).
- **Spacing.** Only `--s-*` values. Section gaps `--s-6`/`--s-7`; inside a card
  `--s-3`/`--s-4`.
- **Breakpoints — a gap.** The stylesheets use about a dozen different widths
  (most often 620, 560, 1080, 720, 980, 900, 860, 940, 920 px) and there are no
  breakpoint tokens. **Proposed canonical set, adopted in T-16:** `560px`
  (phone), `900px` (tablet / single column), `1080px` (desktop, two-column
  layouts). Every screen must work from **375 px** with no horizontal scroll
  (NFR-19).
- **Two layout modes.** The live console is a fixed instrument viewport;
  every other route is a scrolling document (`LayoutMode`, `App.tsx`).

### 7.2 Accessibility

- **Focus.** One ring, everywhere: `:focus-visible { outline: 2px solid
  var(--accent); outline-offset: 2px }`. Elements that take focus only as a
  scroll target (`tabindex="-1"`) opt out. Never remove focus without a
  replacement.
- **Contrast.** Text uses `--ink`, `--ink-muted`, `--ink-faint` or a `-ink`
  ramp variant — all ≥ 4.5:1 (§4). `--ink-ghost` never carries text.
- **Risk.** Colour + label + number, always (§3).
- **Keyboard.** Every interactive element is a real `button`, `a` or form
  control; a skip link (`.skiplink`) jumps to the main content; the command
  palette and any dialog close on Escape.
- **Names.** Every icon-only control has an `aria-label` (audit U-02 found two
  that did not — T-11). Live regions (`aria-live="polite"`) announce panels
  that change in answer to an interaction.
- **Motion.** Honour reduced motion (§2.5); nothing essential is conveyed by
  motion alone.
- **Language.** `lang` is set on the document; Hindi and Hinglish content is
  shown as written.

---

## 8. The landing surface

`/` renders outside the app shell with its own tokens, scoped under `.lp` in
`styles/landing.css`, because its job is persuasion rather than operation: a
deeper ground, a display type scale and one motion vocabulary. It **inherits**
the product's accent (`--lp-accent: var(--accent)`) and threat ramp, and adds:

| Token | Dark | Light | Measured |
|---|---|---|---|
| `--lp-void` | `#050608` | `#f6f7f9` | ground |
| `--lp-deep` | `#07080b` | `#fbfbfd` | ground |
| `--lp-ink` | `#eceef2` | `#12141a` | 17.24 / 17.81 on `--lp-deep` |
| `--lp-ink-2` | `#969db0` | `#545c6b` | 7.39 / 6.51 |
| `--lp-ink-3` | `#788092` | `#616977` | 5.06 / 5.35 on `--lp-deep`; 4.77 / 4.73 on a card — fixed in T-71 (U-08; was `#6f7789` / `#6a7280`, 4.46 and 4.14 at worst) |
| `--lp-cyan` | `#49cfdd` | `#0d7f8e` | 10.73 on `--lp-deep` / 4.73 on white |
| `--lp-indigo` | `#8b7bff` | `#5b4bd6` | structural accent |
| `--lp-mono` | `ui-monospace, "SF Mono", SFMono-Regular, "Cascadia Mono", Menlo, Consolas, monospace` | | the real monospace |

`--lp-ink-3` used to be `#6f7789` / `#6a7280`: 4.46:1 on `--lp-deep` in dark
(its comment claimed 4.6) and 4.14:1 on a card in light — under the AA floor
for the captions and micro-labels it sets (audit **U-08**). T-71 lightened the
dark value and deepened the light one; both now clear 4.5:1 on every landing
surface, cards included.

---

## 9. Gaps — the input to T-16

| ID | Gap | Proposed resolution |
|---|---|---|
| G-01 | No reusable file dropzone (two inline implementations) | `ui/Dropzone.tsx`: drag, browse, accepted types, size cap, rejected-file state |
| G-02 | No stage timeline component | `ui/StageTimeline.tsx`: the eight stages, current and visited, with timestamps — live and investigation |
| G-03 | No evidence viewer | `ui/EvidenceViewer.tsx`: image / audio / document, with the extracted text and its confidence beside it |
| G-04 | Agent trace is page-inline | `ui/AgentTrace.tsx`: one row per agent (status, latency, findings), expandable to inputs/outputs; the graph view is T-49 |
| G-05 | Case-file viewer renders the thin report | Extend `report/InvestigationReport.tsx` for A7 verdicts, entities, hashes, timeline (T-50) |
| G-06 | No toast | `ui/Toast.tsx` on `--z-toast`, `aria-live`, auto-dismiss that pauses on hover |
| G-07 | No general modal | `ui/Modal.tsx`: focus trap, Escape, focus return, `aria-modal` |
| G-08 | Risk badge is markup, not a component | `ui/RiskBadge.tsx`: number + label + colour from one `level` and `score` |
| G-09 | Two risk gauges (`RiskDial`, `ThreatMeter`) | Decide one gauge with a live mode |
| G-10 | Three stat variants, two table variants | Consolidate into `.stat` and `.table` |
| G-11 | Inputs have no invalid state | `.field[aria-invalid]` + message pattern |
| G-12 | ~12 ad-hoc breakpoints, no tokens | Three: 560 / 900 / 1080 (§7.1) |
| G-13 | `--font-mono` is DM Sans, not a monospace; the comment says JetBrains Mono | Decide, and make the comment and the token agree |
| G-14 | `--lp-ink-3` at 4.46:1 (U-08) | ✅ Fixed in T-71 |
