import assert from "node:assert/strict";
import test from "node:test";

import worker, { publicLocation, targetFor } from "./src/index.mjs";

const ORIGIN = "https://jbs-macroradar.pages.dev";

test("strips only the public macro radar prefix and preserves query", () => {
  const target = targetFor(
    "https://jbs.finance/macroradar/macro/?period=2026-09",
    ORIGIN,
  );
  assert.equal(target.href, "https://jbs-macroradar.pages.dev/macro/?period=2026-09");
});

test("rejects paths outside the macro radar contract and encoded separators", () => {
  assert.equal(targetFor("https://jbs.finance/ai/", ORIGIN), null);
  assert.equal(targetFor("https://jbs.finance/macroradar/%2fprivate", ORIGIN), null);
});

test("rewrites Pages redirects back to the public URL", () => {
  assert.equal(
    publicLocation("https://jbs-macroradar.pages.dev/macro/", ORIGIN),
    "/macroradar/macro/",
  );
  assert.equal(publicLocation("https://example.com/", ORIGIN), "https://example.com/");
});

test("fails closed for methods other than GET and HEAD", async () => {
  const response = await worker.fetch(
    new Request("https://jbs.finance/macroradar/", { method: "POST" }),
    { PAGES_ORIGIN: ORIGIN },
  );
  assert.equal(response.status, 405);
  assert.equal(response.headers.get("allow"), "GET, HEAD");
  assert.equal(response.headers.get("x-macroradar-upstream"), "jbs-macroradar-pages");
});

test("redirects the bare public path to its canonical trailing slash", async () => {
  const response = await worker.fetch(
    new Request("https://jbs.finance/macroradar?utm=release"),
    { PAGES_ORIGIN: ORIGIN },
  );
  assert.equal(response.status, 308);
  assert.equal(
    response.headers.get("location"),
    "https://jbs.finance/macroradar/?utm=release",
  );
  assert.equal(response.headers.get("x-macroradar-upstream"), "jbs-macroradar-pages");
});

test("marks upstream responses so release smoke cannot read the legacy site", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (target, init) => {
    assert.equal(target.href, "https://jbs-macroradar.pages.dev/macro/?v=1");
    assert.equal(init.method, "GET");
    return new Response("radar", { status: 200 });
  };
  try {
    const response = await worker.fetch(
      new Request("https://jbs.finance/macroradar/macro/?v=1"),
      { PAGES_ORIGIN: ORIGIN },
    );
    assert.equal(response.status, 200);
    assert.equal(response.headers.get("x-macroradar-upstream"), "jbs-macroradar-pages");
  } finally {
    globalThis.fetch = originalFetch;
  }
});
