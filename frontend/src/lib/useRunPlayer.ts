import { useEffect, useMemo, useRef, useState } from "react";
import { ApiError, api } from "./api";
import { deriveRun, holdAfter, type Run, type RunEvent } from "./run";

const TERMINAL = ["COMPLETED", "FAILED"];

// Runs started in this tab, with how far each has been shown. A run is animated once: coming
// back continues where it was, and any other way of opening it shows its current state at once.
const started = new Map<string, number>();

export function markStarted(runId: string) {
  started.set(runId, 0);
}

/** Polls a run's event log and shows it step by step. */
export function useRunPlayer(runId: string) {
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [status, setStatus] = useState<Run["status"] | null>(null);
  const [shown, setShown] = useState(() => started.get(runId) ?? 0);
  const [error, setError] = useState<string | null>(null);
  const shownAt = useRef(performance.now());

  useEffect(() => {
    let alive = true;
    let after = 0;
    let catchingUp = !started.has(runId);
    let timer: number | undefined;
    async function poll() {
      try {
        const page = await api.getRunEvents(runId, after);
        if (!alive) return;
        after = page.next;
        setError(null);
        setStatus(page.status);
        if (page.events.length) setEvents((prev) => [...prev, ...page.events]);
        if (catchingUp) {
          setShown(after); // seq numbers are 1..n, so the last one is also the count
          catchingUp = page.more;
        }
        if (!TERMINAL.includes(page.status) || page.more) timer = window.setTimeout(poll, page.more ? 0 : 400);
      } catch (e) {
        if (!alive || (e instanceof ApiError && e.status === 401)) return;
        if (e instanceof ApiError && e.status === 404) {
          setError("This investigation was not found.");
          return;
        }
        setError("Connection lost. Reconnecting…");
        timer = window.setTimeout(poll, 2000);
      }
    }
    poll();
    return () => {
      alive = false;
      window.clearTimeout(timer);
    };
  }, [runId]);

  useEffect(() => {
    shownAt.current = performance.now();
    if (started.has(runId)) started.set(runId, shown);
  }, [runId, shown]);

  useEffect(() => {
    if (shown >= events.length) return;
    let rank = 0;
    let count = 0;
    for (let i = 0; i < shown; i++) {
      if (events[i].type === "case.started") rank = events[i].data.rank;
      else if (events[i].type === "screening.completed") count = events[i].data.selected.length;
    }
    // Measured from when the current step appeared, so arriving events never restart the wait.
    const wait = holdAfter(events[shown - 1], rank, count) - (performance.now() - shownAt.current);
    const timer = window.setTimeout(() => setShown((n) => n + 1), Math.max(0, wait));
    return () => window.clearTimeout(timer);
  }, [events, shown]);

  const run = useMemo(() => deriveRun(events.slice(0, shown)), [events, shown]);

  return { run, status, error, caughtUp: shown >= events.length };
}
