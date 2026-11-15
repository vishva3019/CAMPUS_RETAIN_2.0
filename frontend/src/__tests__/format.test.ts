import { describe, expect, it } from "vitest";
import { appLink, plural } from "../lib/format";

describe("format helpers", () => {
  it("maps classic notification links to app routes", () => {
    expect(appLink("/me")).toBe("/activity");
    expect(appLink("/app/activity?claim=4")).toBe("/activity?claim=4");
    expect(appLink("/app/?item=9")).toBe("/?item=9");
    expect(appLink("/dashboard?q=Blue%20bottle")).toBe("/?q=Blue%20bottle");
    expect(appLink("/dashboard")).toBe("/");
    expect(appLink("https://evil.example")).toBeNull();
    expect(appLink(null)).toBeNull();
  });

  it("pluralises", () => {
    expect(plural(1, "item")).toBe("1 item");
    expect(plural(3, "item")).toBe("3 items");
  });
});
