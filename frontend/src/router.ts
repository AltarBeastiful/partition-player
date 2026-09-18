// Minimal history router: two routes, no dependency. "/" is the library, "/s/{id}" is one score.
import { useEffect, useState } from "react";

export type Route = { kind: "home" } | { kind: "score"; id: string } | { kind: "missing" };

export function parse(path: string): Route {
  if (path === "/" || path === "") return { kind: "home" };
  const m = /^\/s\/([A-Za-z0-9]+)\/?$/.exec(path);
  if (m) return { kind: "score", id: m[1] };
  return { kind: "missing" };
}

export function scorePath(id: string): string {
  return `/s/${id}`;
}

export function navigate(path: string, replace = false): void {
  if (replace) history.replaceState(null, "", path);
  else history.pushState(null, "", path);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

export function useRoute(): Route {
  const [route, setRoute] = useState<Route>(() => parse(location.pathname));
  useEffect(() => {
    const onPop = () => setRoute(parse(location.pathname));
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);
  return route;
}

/** Click handler for <a href> that keeps the SPA in place while leaving ctrl/middle-click alone. */
export function onLinkClick(e: React.MouseEvent<HTMLAnchorElement>): void {
  if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
  e.preventDefault();
  navigate(e.currentTarget.getAttribute("href") ?? "/");
}
