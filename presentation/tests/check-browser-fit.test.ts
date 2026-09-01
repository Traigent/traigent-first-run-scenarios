import { describe, expect, it } from "vitest";

import {
  evaluateFitDump,
  isColdStartTimeout,
  parseViewportProbe,
  viewportInsets,
} from "../scripts/check-browser-fit";
import {
  HtmlParseError,
  readDocumentElementAttributes,
  readHtml,
} from "../scripts/html";

function dump(rootAttributes: string, body: string): string {
  return `<!DOCTYPE html>\n<html lang="en" ${rootAttributes}><head><title>Deck</title></head><body>${body}</body></html>`;
}

describe("browser-fit verdicts", () => {
  it("keeps a failing slide failing when deck copy quotes a passing status", () => {
    const contaminated = dump(
      'data-fit-status="fail" data-fit-detail="slide vertical overflow 19624/527" data-fit-slide="ready-to-optimize"',
      '<p>Reviewers ask what data-fit-status="pass" means in the build log.</p>',
    );

    expect(evaluateFitDump(contaminated, "ready-to-optimize")).toBe(
      "slide vertical overflow 19624/527",
    );
  });

  it("keeps a fitting slide passing when deck copy quotes a failing status", () => {
    const passing = dump(
      'data-fit-status="pass" data-fit-detail="" data-fit-slide="ready-to-optimize"',
      '<p>A slide that overflows is reported as data-fit-status="fail" with a detail.</p>',
    );

    expect(evaluateFitDump(passing, "ready-to-optimize")).toBeNull();
  });

  it("refuses a render of a slide it did not ask for, whatever the copy says", () => {
    const wrongSlide = dump(
      'data-fit-status="pass" data-fit-slide="ready-to-optimize"',
      '<p>The requested slide would report data-fit-slide="next-step" here.</p>',
    );

    expect(evaluateFitDump(wrongSlide, "next-step")).toBe(
      'rendered slide "ready-to-optimize" instead of "next-step" (stale dist/?)',
    );
  });

  it("refuses a render that never reported a measurement", () => {
    const unmeasured = dump(
      'data-fit-slide="ready-to-optimize"',
      "<p>Deck</p>",
    );

    expect(evaluateFitDump(unmeasured, "ready-to-optimize")).toBe(
      "fit measurement did not complete: the document element carries no data-fit-status",
    );
  });

  it("refuses a status it does not recognize rather than assuming a pass", () => {
    const unknown = dump(
      'data-fit-status="skipped" data-fit-slide="ready-to-optimize"',
      "<p>Deck</p>",
    );

    expect(evaluateFitDump(unknown, "ready-to-optimize")).toBe(
      'document element reported an unrecognized fit status "skipped"',
    );
  });

  it("reads the verdict past a doctype and comments, and decodes the detail", () => {
    const commented = `<!DOCTYPE html>\n<!-- built deck -->\n<html data-fit-status="fail" data-fit-detail="clipped .a &amp; .b at &quot;1366x768&quot;" data-fit-slide="case-46"></html>`;

    expect(evaluateFitDump(commented, "case-46")).toBe(
      'clipped .a & .b at "1366x768"',
    );
  });

  it("refuses a payload that is not an HTML document", () => {
    expect(() => evaluateFitDump("fit-status: pass\n", "case-46")).toThrowError(
      HtmlParseError,
    );
  });

  it("measures the viewport from the probe page's own root element", () => {
    expect(
      parseViewportProbe(
        '<html data-viewport="1000x775"><body><p>data-viewport="9999x9999"</p></body></html>',
      ),
    ).toEqual({ width: 1000, height: 775 });
  });

  it("refuses a self-closed raw-text element rather than guessing its extent", () => {
    // `<script/>` closes the element inside SVG and does not in HTML, and the
    // difference decides whether everything after it is markup or script.
    expect(() =>
      readHtml("<html><body><svg><script/></svg><p>after</p></body></html>"),
    ).toThrowError(HtmlParseError);
  });

  it("refuses a script that opens the escaped script-data state", () => {
    expect(() =>
      readHtml(
        '<html><body><script>var a="<!--<script>";var b="</script>";</script></body></html>',
      ),
    ).toThrowError(HtmlParseError);
  });

  it("does not end a raw-text block on a longer tag name", () => {
    const document = readHtml(
      '<html><body><script>const s="</scriptx";const t=1</script></body></html>',
    );

    expect(document.rawText[0]?.content).toContain("const t=1");
  });

  it("keeps its index aligned when copy contains a locale-expanding letter", () => {
    // "İ" lower-cases to two UTF-16 units, so reading tag positions from a
    // lower-cased copy of the document drifts one unit per occurrence.
    const document = readHtml(
      `<html><body><p>${"İ".repeat(10)}</p><script>const ok=1</script><script src="https://cdn.invalid/beacon.js"></script></body></html>`,
    );

    expect(document.elements.map((element) => element.name)).toEqual([
      "html",
      "body",
      "p",
      "script",
      "script",
    ]);
  });

  it.each([
    [{ width: 0, height: 0 }, "empty viewport"],
    [{ width: 0, height: 143 }, "empty viewport"],
    [{ width: 1000, height: 143 }, "too large to be a window frame"],
  ])(
    "refuses a probe measurement of %o that would stretch every later window",
    (measured, expected) => {
      expect(() =>
        viewportInsets({ width: 1000, height: 800 }, measured),
      ).toThrowError(expected);
    },
  );

  it("accepts a window frame's worth of inset", () => {
    expect(
      viewportInsets(
        { width: 1000, height: 800 },
        { width: 1000, height: 775 },
      ),
    ).toEqual({ width: 0, height: 25 });
  });

  it("reads only the document element's attributes", () => {
    const attributes = readDocumentElementAttributes(
      '<html data-fit-status=fail><body><div data-fit-status="pass"></div></body></html>',
    );

    expect(attributes.get("data-fit-status")).toBe("fail");
  });

  it("retries only a cold-start spawn timeout, never another spawn error", () => {
    const timedOut = Object.assign(
      new Error("spawnSync /usr/bin/google-chrome ETIMEDOUT"),
      { code: "ETIMEDOUT" },
    );
    expect(isColdStartTimeout(timedOut)).toBe(true);

    const missingBinary = Object.assign(
      new Error("spawnSync /usr/bin/google-chrome ENOENT"),
      { code: "ENOENT" },
    );
    expect(isColdStartTimeout(missingBinary)).toBe(false);
    expect(isColdStartTimeout(new Error("ETIMEDOUT"))).toBe(false);
    expect(isColdStartTimeout("ETIMEDOUT")).toBe(false);
  });
});
