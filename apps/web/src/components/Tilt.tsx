/**
 * Thin wrapper that gives its child card a cursor-driven 3D tilt. Kept as a
 * component (not just the hook) so a `.map` of cards can each own their own
 * tilt without juggling an array of refs.
 */
import type { CSSProperties, ReactNode } from "react";
import { useTilt } from "@/hooks/useTilt";

export function Tilt({
  className,
  style,
  children,
  max,
  lift,
}: {
  className?: string;
  style?: CSSProperties;
  children: ReactNode;
  max?: number;
  lift?: number;
}) {
  const ref = useTilt<HTMLDivElement>({ max, lift });
  return (
    <div ref={ref} className={className} style={style}>
      {children}
    </div>
  );
}
