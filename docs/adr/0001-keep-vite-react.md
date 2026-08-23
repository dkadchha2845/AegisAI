# ADR-0001 — Keep React + Vite; do not migrate to Next.js

**Status:** Accepted · **Date:** 2026-08-23 · **Deviates from:** master §22

## Context
The master context lists Next.js as the frontend recommendation. The inherited
codebase is React 18 + TypeScript + Vite: 17 routes, a working design-token
system with light/dark, GSAP motion, a three.js threat field, a React-Leaflet
map with ARIA handling, a command palette, route boundaries and auth context.
It typechecks clean and builds in 1.24 s.

## Decision
Keep React + Vite. Add React Flow (agent trace) and Cytoscape.js (graph
explorer) as libraries, exactly as the master doc intends.

## Rationale
1. **Next.js's differentiators do not apply.** AegisAI is an authenticated SPA
   for investigation work. There is no SEO surface, no public content to
   server-render, no ISR story. Every page sits behind a login.
2. **Migration cost is real and the benefit is zero.** ~3 weeks to port 17
   routes, motion, and the map — time that buys no capability. Those weeks are
   worth more spent on the URL agent and the dataset.
3. **The master doc's own rules point this way.** §36: "every component should
   have a technical purpose." §40.10: "prioritise a working MVP."
4. **The invariant that matters is preserved.** "The frontend is a pure
   renderer" is a property of our contract discipline, not of the framework.

## Consequences
- No SSR. Acceptable — nothing needs it.
- Slightly more manual routing/code-splitting config. Already solved in-repo.
- If a public marketing site is ever needed, it ships as a separate static
  project rather than dragging the app into a heavier framework.

## Revisit if
A public, indexable content surface becomes a requirement.
