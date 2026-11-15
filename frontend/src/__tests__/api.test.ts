import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError, qs, setCsrfToken } from "../lib/api";

function mockFetch(status: number, body: unknown) {
  const fn = vi.fn().mockResolvedValue(
    new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } }),
  );
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => vi.unstubAllGlobals());

describe("api client", () => {
  it("sends the CSRF token on writes but not reads", async () => {
    setCsrfToken("tok-123");
    const fetch = mockFetch(200, { status: "success" });
    await api.post("/api/x", { a: 1 });
    expect(fetch.mock.calls[0][1].headers["X-CSRFToken"]).toBe("tok-123");
    expect(fetch.mock.calls[0][1].body).toBe('{"a":1}');
    await api.get("/api/y");
    expect(fetch.mock.calls[1][1].headers["X-CSRFToken"]).toBeUndefined();
  });

  it("does not set a JSON content type for uploads", async () => {
    const fetch = mockFetch(200, {});
    const form = new FormData();
    form.set("name", "x");
    await api.post("/api/report", form);
    expect(fetch.mock.calls[0][1].headers["Content-Type"]).toBeUndefined();
    expect(fetch.mock.calls[0][1].body).toBe(form);
  });

  it("surfaces the server's error message and status", async () => {
    mockFetch(409, { error: "This item already has a claim under review." });
    await expect(api.post("/api/claim")).rejects.toMatchObject({ message: "This item already has a claim under review.", status: 409 });
  });

  it("falls back to a readable message and signals sign-out on 401", async () => {
    mockFetch(401, {});
    const spy = vi.fn();
    window.addEventListener("cr:signed-out", spy);
    const err = (await api.get("/api/v1/session").catch((e: unknown) => e)) as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.message).toMatch(/sign in again/);
    expect(spy).toHaveBeenCalled();
  });

  it("reports network failures", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    await expect(api.get("/api/x")).rejects.toMatchObject({ status: 0 });
  });

  it("builds query strings without empty values", () => {
    expect(qs({ kind: "lost", q: "", page: 2, category: null })).toBe("?kind=lost&page=2");
    expect(qs({})).toBe("");
  });
});
