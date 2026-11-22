// Minimal hash router: #/ (queue) and #/cases/<id>. Hash routes need no
// server-side SPA fallback, so deep links work on any static host.
import { useEffect, useState } from "react";

export type Route = { name: "queue" } | { name: "case"; caseId: string; tab?: string };

export function parseHash(hash: string): Route {
  const path = hash.replace(/^#/, "");
  const m = path.match(/^\/cases\/([A-Za-z0-9_-]+)(?:\/([a-z]+))?$/);
  if (m) return { name: "case", caseId: m[1], tab: m[2] };
  return { name: "queue" };
}

export function navigate(path: string) {
  window.location.hash = path;
}

export function useRoute(): Route {
  const [route, setRoute] = useState<Route>(() => parseHash(window.location.hash));
  useEffect(() => {
    const onChange = () => setRoute(parseHash(window.location.hash));
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return route;
}
