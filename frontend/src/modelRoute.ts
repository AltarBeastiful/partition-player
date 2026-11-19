/** A model route as the server offers it (ADR 0010, decision 9). `configured`: the server holds a key for it. */
export interface ModelRoute { id: string; label: string; model: string; vision: boolean; configured: boolean; default: boolean }

/** A span as far as the route cares: does its answer need a crop or a picture? */
export interface RouteSpan { needs_image?: boolean }

/** Why this span cannot run on this route, or null when it can. Typed lyrics placement runs on any route. */
export function spanRefusal(route: ModelRoute | undefined, span: RouteSpan): string | null {
  if (!route || route.vision || !span.needs_image) return null;
  return `${route.label} cannot read images: use typed words, or pick a route with vision`;
}

/** The route to show first: the server's default, else the first one with a key, else the first. */
export function initialRoute(routes: ModelRoute[]): ModelRoute | undefined {
  return routes.find((r) => r.default && r.configured) ?? routes.find((r) => r.configured) ?? routes.find((r) => r.default) ?? routes[0];
}
