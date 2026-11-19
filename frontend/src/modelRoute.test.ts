import { describe, expect, it } from "vitest";
import { initialRoute, spanRefusal, type ModelRoute } from "./modelRoute";

const anthropic: ModelRoute = { id: "anthropic", label: "Anthropic", model: "m", vision: true, configured: false, default: true };
const deepseek: ModelRoute = { id: "deepseek", label: "DeepSeek", model: "d", vision: false, configured: true, default: false };

describe("a span on a route", () => {
  it("is refused with a reason when it needs the picture and the route cannot see", () => {
    expect(spanRefusal(deepseek, { needs_image: true })).toMatch(/DeepSeek cannot read images/);
  });
  it("runs when it is typed words, or when the route can see", () => {
    expect(spanRefusal(deepseek, {})).toBeNull();
    expect(spanRefusal(anthropic, { needs_image: true })).toBeNull();
  });
});

describe("the route shown first", () => {
  it("is the default when it has a key, else one that has", () => {
    expect(initialRoute([anthropic, deepseek])).toBe(deepseek);
    expect(initialRoute([{ ...anthropic, configured: true }, deepseek])?.id).toBe("anthropic");
  });
  it("is the default when no route has a key, so a visitor can bring one", () => {
    expect(initialRoute([anthropic, { ...deepseek, configured: false }])?.id).toBe("anthropic");
  });
});
