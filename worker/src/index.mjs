const PUBLIC_PREFIX = "/macroradar";
const UPSTREAM_HEADER = "X-MacroRadar-Upstream";
const UPSTREAM_HEADER_VALUE = "jbs-macroradar-pages";
const SAFE_METHODS = new Set(["GET", "HEAD"]);
const FORWARDED_HEADERS = [
  "accept",
  "accept-encoding",
  "accept-language",
  "if-modified-since",
  "if-none-match",
  "range",
  "user-agent",
];

function originUrl(origin) {
  const parsed = new URL(origin);
  if (parsed.protocol !== "https:" || parsed.pathname !== "/") {
    throw new TypeError("PAGES_ORIGIN must be an HTTPS origin without a path");
  }
  return parsed;
}

export function targetFor(requestUrl, pagesOrigin) {
  const incoming = new URL(requestUrl);
  const pathname = incoming.pathname;
  if (!pathname.startsWith(`${PUBLIC_PREFIX}/`)) return null;

  const relativePath = pathname.slice(PUBLIC_PREFIX.length);
  if (
    relativePath.includes("//") ||
    /%2f|%5c/i.test(relativePath) ||
    relativePath.split("/").includes("..")
  ) {
    return null;
  }

  const target = originUrl(pagesOrigin);
  target.pathname = relativePath;
  target.search = incoming.search;
  return target;
}

export function publicLocation(location, pagesOrigin) {
  const target = new URL(location, pagesOrigin);
  const origin = originUrl(pagesOrigin);
  if (target.origin !== origin.origin) return location;
  return `${PUBLIC_PREFIX}${target.pathname}${target.search}${target.hash}`;
}

function forwardedHeaders(request) {
  const headers = new Headers();
  for (const name of FORWARDED_HEADERS) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  // These credentials must never leave jbs.finance for the Pages origin.
  headers.delete("cookie");
  headers.delete("authorization");
  return headers;
}

function workerResponse(body, init = {}) {
  const headers = new Headers(init.headers);
  headers.set(UPSTREAM_HEADER, UPSTREAM_HEADER_VALUE);
  return new Response(body, { ...init, headers });
}

export default {
  async fetch(request, env) {
    const incoming = new URL(request.url);
    if (incoming.pathname === PUBLIC_PREFIX) {
      return workerResponse(null, {
        status: 308,
        headers: { location: `${incoming.origin}${PUBLIC_PREFIX}/${incoming.search}` },
      });
    }
    if (!SAFE_METHODS.has(request.method)) {
      return workerResponse("Method not allowed", {
        status: 405,
        headers: { Allow: "GET, HEAD" },
      });
    }

    const target = targetFor(request.url, env.PAGES_ORIGIN);
    if (!target) return workerResponse("Not found", { status: 404 });

    const response = await fetch(target, {
      method: request.method,
      headers: forwardedHeaders(request),
      redirect: "manual",
    });
    const headers = new Headers(response.headers);
    headers.set(UPSTREAM_HEADER, UPSTREAM_HEADER_VALUE);
    const location = headers.get("location");
    if (location) headers.set("location", publicLocation(location, env.PAGES_ORIGIN));
    return new Response(response.body, { status: response.status, headers });
  },
};
