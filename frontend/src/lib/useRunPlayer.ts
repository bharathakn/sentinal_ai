import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiError, api } from "./api";
import { deriveRun, holdAfter, type Run, type RunEvent } from "./run";

const TERMINAL = ["COMPLETED", "FAILED"];
// Runs whose animation already played in this page session: coming back from a case shows the report.
const played = new Set<string>();

/** Polls a run's event log and plays it at a watchable pace. */
export function useRunPlayer(runId: string) {
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [status, setStatus] = useState<Run["status"] | null>(null);
  const [shown, setShown] = useState(0);
  const [speed, setSpeed] = useState(1);
  const [skipped, setSkipped] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    let after = 0;
    let first = true;
    let timer: number | undefined;
    async function poll() {
      try {
        const page = await api.getRunEvents(runId, after);
        if (!alive) return;
        after = page.next;
        setError(null);
        setStatus(page.status);
        if (page.events.length) setEvents((prev) => [...prev, ...page.events]);
        const ended = TERMINAL.includes(page.status);
        // Opening a run that finished a while ago goes straight to its report (it can be replayed).
        if (first && ended) {
          const last = page.events[page.events.length - 1];
          if (played.has(runId) || (last && Date.now() - new Date(last.at_utc).getTime() > 30000)) setSkipped(true);
        }
        first = false;
        if (!ended || page.more) timer = window.setTimeout(poll, page.more ? 0 : 600);
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
    if (skipped) {
      setShown(events.length);
      return;
    }
    if (shown >= events.length) return;
    let rank = 0;
    for (let i = 0; i < shown; i++) if (events[i].type === "case.started") rank = events[i].data.rank;
    const timer = window.setTimeout(() => setShown((n) => n + 1), holdAfter(events[shown - 1], rank) / speed);
    return () => window.clearTimeout(timer);
  }, [events, shown, speed, skipped]);

  const run = useMemo(() => deriveRun(events.slice(0, shown)), [events, shown]);
  useEffect(() => {
    if (run.phase === "complete") played.add(runId);
  }, [run.phase, runId]);
  const replay = useCallback(() => {
    setSkipped(false);
    setShown(0);
  }, []);
  const skip = useCallback(() => setSkipped(true), []);

  return { run, status, error, speed, setSpeed, skip, skipped, replay };
}
