import { useEffect, useState } from "react";

export type Route =
  | { kind: "home" }
  | { kind: "project"; projectId: string }
  | { kind: "settings" };

export function readRoute(location: Pick<Location, "pathname"> | URL): Route {
  const path = location.pathname.replace(/\/+$/, "") || "/";
  if (path === "/") return { kind: "home" };
  if (path === "/settings") return { kind: "settings" };
  const match = path.match(/^\/projects\/([^/]+)$/);
  if (match) return { kind: "project", projectId: decodeURIComponent(match[1]) };
  return { kind: "home" };
}

export function pathForRoute(route: Route): string {
  if (route.kind === "home") return "/";
  if (route.kind === "settings") return "/settings";
  return `/projects/${encodeURIComponent(route.projectId)}`;
}

export function useRoute(): [Route, (next: Route) => void] {
  const [route, setRoute] = useState<Route>(() => readRoute(window.location));

  useEffect(() => {
    const onPopState = () => setRoute(readRoute(window.location));
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  const navigate = (next: Route) => {
    window.history.pushState({}, "", pathForRoute(next));
    setRoute(next);
  };
  return [route, navigate];
}
