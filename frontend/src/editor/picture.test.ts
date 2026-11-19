/** The lyrics picture the panel sends (ADR 0010): a file becomes bare base64, and the route says whether it may be used. */
import { afterEach, describe, expect, it, vi } from "vitest";
import { spanRefusal } from "../modelRoute";
import { pictureToBase64 } from "./picture";

afterEach(() => vi.restoreAllMocks());

describe("pictureToBase64", () => {
  it("gives the bytes of the file as plain base64, without a data-URL prefix", async () => {
    const file = new File([new Uint8Array([0x89, 0x50, 0x4e, 0x47])], "words.png", { type: "image/png" });
    expect(await pictureToBase64(file)).toBe("iVBORw==");
  });
});

describe("the span a picture makes", () => {
  it("is refused on a route without vision and allowed on one with", () => {
    const span = { needs_image: true };
    const route = { id: "deepseek", label: "DeepSeek", model: "m", vision: false, configured: true, default: false };
    expect(spanRefusal(route, span)).toMatch(/DeepSeek cannot read images/);
    expect(spanRefusal({ ...route, vision: true }, span)).toBeNull();
  });
});
