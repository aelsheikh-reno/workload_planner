// @vitest-environment node

import { describe, expect, it } from "vitest";

import { resolveBffProxyTarget } from "../../vite.config.js";

describe("resolveBffProxyTarget", () => {
  it("defaults to the seeded local BFF target", () => {
    expect(resolveBffProxyTarget({})).toBe("http://127.0.0.1:8000");
  });

  it("uses the explicit launcher-provided BFF target", () => {
    expect(
      resolveBffProxyTarget({ BFF_PROXY_TARGET: "http://127.0.0.1:8011" }),
    ).toBe("http://127.0.0.1:8011");
  });
});
