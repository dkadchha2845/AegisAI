/**
 * The header block every route opens with.
 *
 * The audit found five spellings of this: `<p class="label">Overview</p>`,
 * `<p class="eyebrow">Analyst tool</p>`, and three pages with no eyebrow at
 * all — so the same H1 started at a different y on each screen, and the
 * eyebrow vocabulary ("OVERVIEW", "MONITOR", "UNDERSTAND", "INVESTIGATE",
 * "ANALYST TOOL") was five words for one idea that the sidebar and the
 * breadcrumb already answer.
 *
 * So there is no eyebrow. Location is the navigation's job, said once. What a
 * header owes the reader is the name of the thing and one sentence about what
 * it is for — plus, optionally, the actions that apply to the whole page.
 */

import type { ReactNode } from "react";

interface Props {
  title: string;
  /** One sentence. Kept short enough to read in a glance. */
  lede?: ReactNode;
  /** Page-level actions, right-aligned on wide viewports. */
  actions?: ReactNode;
  /** Rendered under the lede — a back link, a filter row, a status line. */
  children?: ReactNode;
}

export function PageHeader({ title, lede, actions, children }: Props) {
  return (
    <header className="page__head">
      <div className="page__headmain">
        <h1 className="page__title">{title}</h1>
        {lede && <p className="page__lede">{lede}</p>}
        {children}
      </div>
      {actions && <div className="page__actions">{actions}</div>}
    </header>
  );
}
