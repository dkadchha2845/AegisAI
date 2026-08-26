/**
 * Display formatting shared across screens.
 *
 * Currency lived in three places and disagreed with itself: the admin screen
 * rendered `total_loss_inr` through `Intl.NumberFormat(… notation: "compact")`
 * as "₹12Cr", the intel screen had its own helper producing "₹12.16 cr", and
 * the operations screen had a third. Three renderings of one contract field
 * read as three different measurements of three different things — which is
 * the same failure as two spellings of a label, except it is a *number*, and
 * a number on this product is evidence.
 *
 * One implementation, Indian digit grouping throughout, because every figure
 * here is an Indian one.
 */

const GROUPED = new Intl.NumberFormat("en-IN");

/** Exact rupees with Indian grouping — "₹1,23,45,678". For reports. */
export const inr = (n: number): string => `₹${GROUPED.format(Math.round(n))}`;

/** Whole numbers with Indian grouping — "1,14,238". */
export const count = (n: number): string => GROUPED.format(n);

/**
 * Compact Indian-system figure for stat tiles — "₹12.16 Cr", "₹4.5 L".
 * Two decimals at crore, one at lakh: enough to distinguish two clusters,
 * short enough that a tile never wraps its own number across two lines.
 */
export function formatInr(n: number): string {
  if (n >= 1e7) return `₹${(n / 1e7).toFixed(2).replace(/\.?0+$/, "")} Cr`;
  if (n >= 1e5) return `₹${(n / 1e5).toFixed(1).replace(/\.0$/, "")} L`;
  return inr(n);
}
