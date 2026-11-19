/** The lyrics picture the panel sends (ticket 07): a file becomes bare base64, and the route says whether it may be used. */
import { afterEach, describe, expect, it, vi } from "vitest";
import { getModelRoute } from "../api";
import { pictureToBase64 } from "./picture";

afterEach(() => vi.restoreAllMocks());

describe("pictureToBase64", () => {
  it("gives the bytes of the file as plain base64, without a data-URL prefix", async () => {
    const file = new File([new Uint8Array([0x89, 0x50, 0x4e, 0x47])], "words.png", { type: "image/png" });
    expect(await pictureToBase64(file)).toBe("iVBORw==");
  });
});

describe("getModelRoute", () => {
  it("reads what the server's route offers", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ enabled: true, model: "m", vision: false }), { status: 200 })));
    expect(await getModelRoute()).toEqual({ enabled: true, model: "m", vision: false });
    expect(fetch).toHaveBeenCalledWith("/api/model-route");
  });
});
