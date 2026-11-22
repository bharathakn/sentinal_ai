// Minimal hash router. Hash routes need no server-side SPA fallback.
import { useEffect, useState } from "react";

export type Route =
  | { name: "home" }
  | { name: "run"; runId: string }
  | { name: "queue" }
  | { name: "case"; caseId: string; tab?: string };

export function parseHash(hash: string): Route {
  const path = hash.replace(/^#/, "");
  const run = path.match(/^\/runs\/([A-Za-z0-9_-]+)$/);
  if (run) return { name: "run", runId: run[1] };
  const c = path.match(/^\/cases\/([A-Za-z0-9_-]+)(?:\/([a-z]+))?$/);
  if (c) return { name: "case", caseId: c[1], tab: c[2] };
  if (path === "/cases") return { name: "queue" };
  return { name: "home" };
}

export function navigate(path: string) {
  window.location.hash = path;
}

export function useRoute(): Route {
  const [route, setRoute] = useState<Route>(() => parseHash(window.location.hash));
  useEffect(() => {
    const onChange = () => {
      const next = parseHash(window.location.hash);
      setRoute((prev) => {
        // A tab change inside a case keeps the scroll position; a new page starts at the top.
        if (prev.name !== next.name || next.name === "run") window.scrollTo(0, 0);
        return next;
      });
    };
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return route;
}
