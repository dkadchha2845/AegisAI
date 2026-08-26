# AegisAI — UI/UX audit and redesign

**Date:** 2026-08-26 · **Scope:** every route, both themes, desktop and mobile.

This is the record of a full-product interface audit and the redesign that
followed it. It is written in the order the work happened: what was measured,
what was found, what changed, and what was verified afterwards.

The audit was run against the **running application** — the Vite dev server
with the FastAPI service behind it — not against the source. Several of the
worst findings are invisible in code review and only appear when a real
browser lays the page out.

---

## 1. Method

Three passes, all against `localhost`:

1. **Route walk.** All 17 routes opened individually at 1440×900, 1280×1000
   and 375×812, in dark and light, signed out and signed in as each of the
   four demo roles.
2. **Instrumented sweep.** A script injected into the running page and run on
   every route, measuring: elements whose box extends past the viewport with
   no scrollable or clipping ancestor; text truncated by `text-overflow`;
   WCAG 2.1 contrast for every element that renders its own text, compositing
   the real stacked backgrounds; touch-target size under `pointer: coarse`;
   controls with no accessible name; form fields with no label; heading order
   and `<h1>` count; and the set of font families and border radii actually in
   use.
3. **Flow walk.** The real submit paths exercised end to end — an analysis
   through `/api/shield/verify`, an investigation through
   `/api/investigations` with its event stream, sign-in, sign-out, theme
   toggle, command palette, mobile drawer.

### What could not be verified here

The browser pane this work ran in does not composite frames while hidden:
programmatic scrolling updates `scrollY` but fires no `scroll` event, and
`IntersectionObserver` callbacks never run. So **scroll-driven behaviour was
not verified in a browser** — that means the landing page's scroll-triggered
reveals, its pipeline rail, and the header's transparent→settled transition.
Their code is written and typechecks; their *behaviour* is unconfirmed and
should be checked by hand once. Everything else in this document was measured.

---

## 2. Findings

### 2.1 Critical — the landing page and the login screen could not scroll

`global.css` set `overflow: hidden` on `<body>` for the live console's
benefit, and `app.css` gave the scrolling routes a way to opt back in via
`html[data-layout="flow"]`. That attribute was set by **`AppShell`** — and the
landing (`/`) and login (`/login`) render *outside* the AppShell.

Measured on a fresh load of `/`: `data-layout` unset, `body` computed
`overflow-y: hidden`, `body` height pinned to the viewport, document height
3088px in a 720px viewport. Pressing `End` did nothing. Everything below the
hero — the whole pipeline section, the live figures, the seven-step scam arc,
the engineering principles, both closing CTAs and the footer — was
unreachable in any browser.

On `/login` at a 720px viewport the card's bottom edge measured 779px: the
"Citizens don't need an account" line was cut off, and on a shorter laptop the
**Sign in button itself** would have been.

The same mechanism had a second failure mode: navigating from the console to
the landing left `data-layout="fixed"` behind, because nothing unset it.

**Fixed** by inverting the default. Documents scroll unless a route declares
itself a fixed viewport, and the declaration moved from `AppShell` to a
`LayoutMode` component at the router level, where it covers every route
including the two that render outside the shell.

### 2.2 Critical — the live console was unusable on a phone

At 375px, **90 elements** extended past the right edge of the viewport. Because
the console runs in fixed-viewport mode with `overflow: hidden`, they were not
merely cut off — they were unreachable. The transport controls, the rehearsal
scrubber, the manipulation map, the trust passport and the number-intelligence
panel were all off-screen with no way to get to them.

Two root causes, both in grid sizing:

- `.shell` used an implicit `auto` column, which is as wide as its widest
  item's min-content — one row of `white-space: nowrap` transport buttons
  forced the entire console to 441px inside a 375px viewport.
- `.grid` and `.topbar` had the default `min-width: auto`, so neither could
  shrink below its content.

**Fixed** with `minmax(0, 1fr)` and explicit `min-width: 0`, and by taking the
console out of fixed-viewport mode below 900px entirely: the columns stack in
reading order (transcript → threat reading → intelligence), the transport
controls scroll horizontally inside their own row, and the page scrolls.

Same class of bug found and fixed across the codebase: **25 grid declarations**
used bare `1fr`, which is `minmax(auto, 1fr)` and cannot shrink. Every one is
now `minmax(0, 1fr)`. This is what was pushing `/analyzer` 132px past a phone
viewport and `/emergency` 54px past it.

### 2.3 Accessibility — the tertiary ink failed AA everywhere at once

`--ink-faint` measured **3.22:1** on `--panel` in dark and **3.10:1** on white
in light. It carries every caption, every stat label, every micro-label and
every sidebar blurb in the product, so the failure was not in one corner — it
was on every screen.

**Fixed**: dark `#5f6672 → #7d8492` (4.96:1 on panel), light `#8a93a1 →
#666e7d` (5.13:1 on white). The old value is kept as `--ink-ghost` for
non-text use (hairlines, disabled glyphs).

The light theme's semantic ramp failed the same way — measured against
`--panel-hover`, the darkest surface any of it sits on: calm 3.2, watch 2.9,
elevated 3.0, high 3.9, accent 4.4. Every status chip, every risk badge and
the degraded pill failed in light mode.

**Fixed** by separating the ramp's two jobs. A ramp colour *fills* things
(meter arcs, bars, map bubbles) and it *writes* things (an 11px chip label on
a 12% wash of its own hue). On near-black those want the same value; on paper
they do not, and no single value serves both. The fills stay saturated; new
`--{calm,watch,elevated,high,critical,accent}-ink` tokens carry the text and
clear 4.6:1 against the interface's actual worst case.

### 2.4 Information architecture — pages that were about the wrong audience

- **`/reports` ("My Reports")** — a citizen page whose own lede reads "every
  investigation you've saved" — rendered five panels: Identity, Organisations,
  Saved cases, Activity log and **Users**, with a form for creating platform
  accounts. `/admin` rendered a *second* user table with a *second* add-user
  form. Someone opening "My Reports" for a complaint PDF was shown a table of
  platform tenants.

  **Fixed**: tenancy moved to `pages/admin/Tenancy.tsx` and is rendered once,
  by the admin route. The duplicate on `/admin` was deleted in its favour.
  Identity moved to Profile. `/reports` is now saved cases and nothing else.

- **`/learn`** — the citizen education page — rendered its content as a list of
  our own repository filenames: `rbi-advisories.md § intro`,
  `scam-playbooks.md § PAYMENT_EXECUTION`, seventeen rows of monospace.

  **Fixed**: the readable half of each citation id leads ("Banks and the RBI
  never ask for OTP, PIN, CVV or passwords"), the filename follows as
  provenance. Not dropped — a citation you cannot trace is not a citation.

- **`/dashboard`** opened with a configuration readout and closed with seven
  cards duplicating the seven sidebar destinations, same labels, same icons.

  **Fixed**: platform measurements first, system state below, card grid gone.

- **Analyst tools were not in the navigation at all.** They lived as eight link
  rows on the Profile page, which is why the Dashboard grew a card grid to
  compensate. `navGroups` now renders them as a second, role-gated sidebar
  group.

### 2.5 The design system had been built more than once

| Component | Implementations found |
|---|---|
| Button | `.btn` · `.btn2` · `.helpbtn` · `.task-tile` · `.login__role` |
| Segmented control | `.tabs/.tab` · `.inv__kinds/.inv__kind` · `.threat-ramp__step` |
| Table | `.admin-table` · `.cb-table` — different header casing, padding and hover |
| Micro-label | `.label` · `.eyebrow` · `.fieldlabel` · `.inv__label` |
| Stat tile | `.stat` · `.admin-kpi` · `.live-stat` |
| Brand mark | four separate 9px squares, three of which tracked the threat colour |
| Currency | three formatters — `₹12Cr`, `₹12.16 cr`, and a third |
| Empty state | four differently-styled sentences, no component |

Each pair looked *almost* the same, which is worse than looking different: two
6px-vs-8px paddings read as sloppiness rather than as a choice.

The page eyebrow was the clearest symptom — five different words for one idea
("OVERVIEW", "MONITOR", "UNDERSTAND", "INVESTIGATE", "ANALYST TOOL"), in two
different classes, on five of thirteen pages, so the same `<h1>` started at a
different y on every screen.

**Fixed**: `styles/primitives.css` owns one implementation per component and
re-points the duplicate class names at it, so one edit moves every instance.
`PageHeader` replaced all thirteen ad-hoc headers and dropped the eyebrow
entirely — location is the navigation's job, said once. `lib/format.ts` owns
currency.

### 2.6 Typography — form controls were rendering in Arial

`button`, `input`, `select` and `textarea` do not inherit `font-family` in any
browser, and nothing in the reset said so. Measured: 15 elements per page in
Arial at 13.33px. Invisible while the buttons held only icons, and wrong the
moment one grows a label. Leaflet brought a third and fourth family
(`Lucida Console`) into the map screens through its own controls.

**Fixed**: `font: inherit` on form controls in the reset, and the Leaflet
furniture restyled. Every route now measures exactly two families: Satoshi and
JetBrains Mono.

### 2.7 Smaller findings

- **Sidebar blurbs were clipped mid-word** — "Check a message, screenshot, or
  nu…" told the reader less than nothing. Now two lines, clamped.
- **System status and identity were hidden below 620px** — the viewport where
  a degraded backend matters most, because that is the phone someone reaches
  for while the call is still live. Both moved to the sidebar footer, which
  survives into the mobile drawer.
- **The ⌘K hint showed a keyboard shortcut on touch devices.** Now a search
  affordance under `pointer: coarse`.
- **The command palette never took focus reliably** — it focused via
  `requestAnimationFrame`, one frame late, and its Escape handler was bound to
  a panel that focus had never entered. Now `useLayoutEffect`, Escape at the
  document, and focus restored to the trigger on close.
- **The live console had no `<h1>`.**
- **Three search inputs had placeholders instead of labels** — a placeholder is
  gone exactly when the label is needed.
- **Colour was being spent where it carried no reading**: the landing's
  section heading was a red→amber→green gradient and the three module cards
  had red/amber/green top borders, which put the ramp's most urgent colour on
  the word "Detect"; `/intel` rendered cumulative reported loss — money
  already gone, not a live danger — in critical red. Both neutralised.
- **A duplicate React key** (`phone-7042118830`) in the matched-entities row,
  where one entity can be matched by more than one cluster.
- **No favicon and no meta description.** The tab strip is the one place a
  browser shows a product to someone who has not opened it.

---

## 3. What the design system is now

**`styles/tokens.css`** — the vocabulary. Type scale, 4px spacing, radii,
motion, container widths (`--w-doc` 820px, `--w-app` 1180px, `--w-wide`
1480px), three inks plus a non-text ghost, one accent, the five-step threat
ramp, and the `-ink` writing variants of both.

**`styles/primitives.css`** — one implementation per component: button, icon
button, card, panel, badge, field, select, segmented control, table, stat
tile, empty state, alert, skeleton, tooltip, page header, risk dial,
workspace, brand.

**`components/ui/`** — `PageHeader`, `States` (`EmptyState`, `ErrorState`,
`Skeleton`, `SkeletonRows`, `Spinner`), `RiskDial`.

**`components/brand/Logo.tsx`** — one geometric mark, three variants (full,
compact, live), used in the sidebar, the top bar, the landing header, the
login panel, the console and the favicon. It deliberately does *not* follow
the threat colour: tying the logo to the ramp turned the brand red on a
CRITICAL call, spending the ramp's most urgent colour on something carrying no
reading. The console's `live` variant is the one exception, because there a
pulsing threat-coloured mark *is* a status readout.

### Rules the redesign holds itself to

1. **Colour means something.** The threat ramp appears where a threat is being
   described and nowhere else.
2. **Nothing on the landing page is invented.** The live-call panel is one
   frame of `mock/stream.json` at t=36s — the same recorded session the
   console plays — and says so. Platform figures come from `/api/intel/stats`.
   The two hero statistics are attributed. There are no benchmark claims.
3. **No decorative controls.** The obvious way to fill a settings page is
   eight sections of plausible toggles; every one would change nothing. Every
   control on Profile is wired to real behaviour, and the sections that are
   statements of fact are written as statements of fact.
4. **Unscored is not zero.** `RiskDial` renders a null score as an explicit
   "not scored" state, never as a dial reading 0 — mirroring the same refusal
   in `investigations/report.py`.
5. **Motion is never how the interface says something.** Turning it off leaves
   every reading, label and control exactly where it was.

---

## 4. Verification

Instrumented sweep over 15 in-shell routes, both themes, at 1280×1000 and
375×812:

| Check | Before | After |
|---|---|---|
| Elements past the viewport with no way to reach them | 90 (console, 375px) · 17 (analyzer) · 8 (emergency) | **0** on every route |
| WCAG AA contrast failures | systemic — `--ink-faint` everywhere; whole light ramp | **0** on every route, both themes |
| Form fields with no label | 3 | **0** |
| Controls with no accessible name | 0 | **0** |
| Routes with exactly one `<h1>` | 14 of 15 | **15 of 15** |
| Heading-level skips | 0 | **0** |
| Font families in use | 4 (Satoshi, JetBrains Mono, Arial, Lucida Console) | **2** |
| Landing page reachable below the fold | no | yes |

Two flags remain in the sweep output and are false positives: Leaflet map
tiles positioned outside their own `overflow: hidden` container, and the
cluster-count bubbles, whose background is declared in `color()` syntax that
the measuring script does not parse. Both were checked by hand — the bubble
text measures roughly 7:1.

Interaction paths exercised against the real API: analysis (verdict 93 /
CRITICAL, confidence 88%, dial and evidence chips rendering), investigation
(7 of 7 nodes, 6 agents, one reporting degraded and shown degraded, verdict
correctly "not scored"), sign-in and sign-out, theme toggle, motion preference
(attribute set, persisted, transitions collapsed to 1µs), command palette
(focus in, Escape, focus restored), mobile drawer (scrim, scroll lock, focus
in, Escape, focus restored). Browser console clean on a fresh load.

**Gates:** 495 passed / 23 skipped · contract consistent · frontend typecheck
clean · production build succeeds.

The classifier is the **lexical fallback** in this worktree — `ml/artifacts/`
is gitignored, so no checkpoint is present. Nothing in this change touches the
model path, but the "2 running degraded" pill visible in every screenshot is
that fallback plus the ephemeral database, and it is telling the truth.
