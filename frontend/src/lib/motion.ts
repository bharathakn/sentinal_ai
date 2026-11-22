import { useEffect, useRef, useState } from "react";

export function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
}

/** Counts from the last displayed value to `target`. */
export function useCountUp(target: number, ms = 900): number {
  const [value, setValue] = useState(0);
  const current = useRef(0);
  useEffect(() => {
    const from = current.current;
    if (from === target) return;
    if (prefersReducedMotion() || typeof requestAnimationFrame === "undefined") {
      current.current = target;
      setValue(target);
      return;
    }
    let frame = 0;
    const start = performance.now();
    const tick = (now: number) => {
      const t = Math.max(0, Math.min(1, (now - start) / ms));
      current.current = from + (target - from) * (1 - (1 - t) ** 3);
      setValue(current.current);
      if (t < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [target, ms]);
  return value;
}
