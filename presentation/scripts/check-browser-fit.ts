import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { pathToFileURL } from "node:url";

import { presentation } from "../src/content";
import { readDocumentElementAttributes } from "./html";
import { distRoot, isMainModule } from "./runtime";

const VIEWPORTS = [
  { width: 1366, height: 768 },
  { width: 1600, height: 900 },
] as const;
const ISOLATED_PASSES = 2;

export class BrowserFitError extends Error {
  constructor(message: string, options?: ErrorOptions) {
    super(message, options);
    this.name = "BrowserFitError";
  }
}

function chromeExecutable(): string {
  const candidates = [
    process.env.CHROME_BIN,
    "google-chrome",
    "google-chrome-stable",
    "chromium",
    "chromium-browser",
    "chrome",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
  ].filter((candidate): candidate is string => candidate !== undefined);
  for (const candidate of candidates) {
    try {
      execFileSync(candidate, ["--version"], { stdio: "ignore" });
      return candidate;
    } catch {
      continue;
    }
  }
  throw new BrowserFitError(
    "Browser-fit validation requires Google Chrome or Chromium; set CHROME_BIN",
  );
}

interface FitFailure {
  id: string;
  pass: number;
  viewport: string;
  detail: string;
}

interface ViewportInsets {
  width: number;
  height: number;
}

function isolatedChromeArguments(profileDirectory: string): string[] {
  return [
    "--headless=new",
    "--disable-gpu",
    "--hide-scrollbars",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-background-networking",
    "--disable-component-update",
    "--disable-default-apps",
    "--disable-domain-reliability",
    "--disable-features=OptimizationHints,MediaRouter",
    "--disable-sync",
    "--force-device-scale-factor=1",
    "--metrics-recording-only",
    "--no-pings",
    "--host-resolver-rules=MAP * 0.0.0.0",
    `--user-data-dir=${profileDirectory}`,
  ];
}

/**
 * Decide one slide render from the document element's own measurement.
 * Returns `null` when the slide fits, otherwise the failure detail.
 */
export function evaluateFitDump(
  dumpedDom: string,
  expectedSlideId: string,
): string | null {
  const attributes = readDocumentElementAttributes(dumpedDom);
  const renderedSlide = attributes.get("data-fit-slide");
  if (renderedSlide !== expectedSlideId) {
    // An unknown hash id silently falls back to the first slide, so a pass
    // for the wrong slide means the requested slide was never measured.
    return `rendered slide "${renderedSlide ?? "none"}" instead of "${expectedSlideId}" (stale dist/?)`;
  }
  const status = attributes.get("data-fit-status");
  if (status === "pass") {
    return null;
  }
  if (status === undefined) {
    return "fit measurement did not complete: the document element carries no data-fit-status";
  }
  if (status !== "fail") {
    return `document element reported an unrecognized fit status "${status}"`;
  }
  return (
    attributes.get("data-fit-detail") ??
    "fit measurement reported a failure without detail"
  );
}

export function parseViewportProbe(dumpedDom: string): {
  width: number;
  height: number;
} {
  const measured =
    readDocumentElementAttributes(dumpedDom).get("data-viewport");
  const dimensions =
    measured === undefined ? null : /^(\d+)x(\d+)$/.exec(measured);
  if (dimensions === null) {
    throw new BrowserFitError(
      "Could not measure the isolated browser viewport",
    );
  }
  return { width: Number(dimensions[1]), height: Number(dimensions[2]) };
}

// A headless window's frame is tens of pixels at most. A larger difference
// means the probe did not measure a laid-out window, and accepting it would
// render every slide at a size the gate never asked for.
const MAXIMUM_WINDOW_INSET = 200;

export function viewportInsets(
  requested: ViewportInsets,
  measured: ViewportInsets,
): ViewportInsets {
  const insets = {
    width: requested.width - measured.width,
    height: requested.height - measured.height,
  };
  if (measured.width <= 0 || measured.height <= 0) {
    throw new BrowserFitError(
      `Browser reported an empty viewport for a ${requested.width}x${requested.height} window: ${measured.width}x${measured.height}`,
    );
  }
  if (insets.width < 0 || insets.height < 0) {
    throw new BrowserFitError(
      `Browser viewport exceeded its requested window: ${measured.width}x${measured.height}`,
    );
  }
  if (
    insets.width > MAXIMUM_WINDOW_INSET ||
    insets.height > MAXIMUM_WINDOW_INSET
  ) {
    throw new BrowserFitError(
      `Browser window insets of ${insets.width}x${insets.height} are too large to be a window frame; the probe did not measure a laid-out window`,
    );
  }
  return insets;
}

const VIEWPORT_PROBE_ATTEMPTS = 3;

function probeViewport(
  chrome: string,
  profileDirectory: string,
  requested: ViewportInsets,
): ViewportInsets {
  const probe = encodeURIComponent(
    "<body><script>document.documentElement.dataset.viewport=innerWidth+'x'+innerHeight</script></body>",
  );
  const html = execFileSync(
    chrome,
    [
      ...isolatedChromeArguments(profileDirectory),
      // The probe decides the size every later render is measured at, so it
      // waits for layout exactly as those renders do.
      "--run-all-compositor-stages-before-draw",
      "--virtual-time-budget=1500",
      `--window-size=${requested.width},${requested.height}`,
      "--dump-dom",
      `data:text/html,${probe}`,
    ],
    {
      encoding: "utf8",
      maxBuffer: 1024 * 1024,
      // The probe is the run's first Chrome launch, and a cold start on a
      // busy CI runner can exceed the 10s the warmed per-slide launches get.
      timeout: 30_000,
      stdio: ["ignore", "pipe", "pipe"],
    },
  );
  return parseViewportProbe(html);
}

/**
 * A cold Chrome start on a busy CI runner occasionally exceeds the probe's
 * spawn timeout, surfacing as an ETIMEDOUT errno rather than a
 * BrowserFitError. Only the run's first launch fails this way, so the probe
 * retries it like a zero-sized reading; per-slide launches after warm-up
 * still fail loudly on any spawn error.
 */
export function isColdStartTimeout(error: unknown): boolean {
  return (
    error instanceof Error &&
    (error as NodeJS.ErrnoException).code === "ETIMEDOUT"
  );
}

/**
 * Measure the difference between a requested window and the viewport inside
 * it, so later renders can ask for an exact viewport.
 *
 * A browser occasionally dumps this probe page before its window has been
 * sized, reporting a viewport of zero. That reading is refused rather than
 * turned into an inset - an inset that stretches every later window would
 * measure all 28 slides at a size the gate never asked for - and the probe is
 * simply taken again.
 */
function measureViewportInsets(
  chrome: string,
  profileDirectory: string,
): ViewportInsets {
  const requested = { width: 1000, height: 800 };
  let lastFailure: unknown;
  for (let attempt = 1; attempt <= VIEWPORT_PROBE_ATTEMPTS; attempt += 1) {
    try {
      return viewportInsets(
        requested,
        probeViewport(chrome, profileDirectory, requested),
      );
    } catch (error: unknown) {
      if (!(error instanceof BrowserFitError) && !isColdStartTimeout(error)) {
        throw error;
      }
      lastFailure = error;
    }
  }
  throw new BrowserFitError(
    `Could not measure the isolated browser viewport in ${VIEWPORT_PROBE_ATTEMPTS} attempts`,
    { cause: lastFailure },
  );
}

function inspectSlide(
  chrome: string,
  profileDirectory: string,
  viewportInsets: ViewportInsets,
  presentationUrl: string,
  id: string,
  width: number,
  height: number,
  pass: number,
): FitFailure | null {
  const html = execFileSync(
    chrome,
    [
      ...isolatedChromeArguments(profileDirectory),
      "--run-all-compositor-stages-before-draw",
      "--virtual-time-budget=1500",
      `--window-size=${width + viewportInsets.width},${height + viewportInsets.height}`,
      "--dump-dom",
      `${presentationUrl}?fit-check=1&fit-width=${width}&fit-height=${height}#/${id}`,
    ],
    {
      encoding: "utf8",
      maxBuffer: 8 * 1024 * 1024,
      timeout: 10_000,
      stdio: ["ignore", "pipe", "pipe"],
    },
  );
  const detail = evaluateFitDump(html, id);
  if (detail === null) {
    return null;
  }
  return {
    id,
    pass,
    viewport: `${width}x${height}`,
    detail,
  };
}

export function checkBrowserFit(): void {
  const presentationPath = path.join(distRoot, "index.html");
  readFileSync(presentationPath);
  const presentationUrl = pathToFileURL(presentationPath).href;
  const chrome = chromeExecutable();
  const failures: FitFailure[] = [];

  for (let pass = 1; pass <= ISOLATED_PASSES; pass += 1) {
    const profileDirectory = mkdtempSync(
      path.join(os.tmpdir(), "traigent-browser-fit-"),
    );
    try {
      const viewportInsets = measureViewportInsets(chrome, profileDirectory);
      for (const { width, height } of VIEWPORTS) {
        for (const slide of presentation.slides) {
          const failure = inspectSlide(
            chrome,
            profileDirectory,
            viewportInsets,
            presentationUrl,
            slide.id,
            width,
            height,
            pass,
          );
          if (failure !== null) {
            failures.push(failure);
          }
        }
      }
    } finally {
      rmSync(profileDirectory, { recursive: true, force: true });
    }
  }

  if (failures.length > 0) {
    throw new BrowserFitError(
      `Browser-fit validation failed:\n${failures
        .map(
          (failure) =>
            `- pass ${failure.pass}, ${failure.id} at ${failure.viewport}: ${failure.detail}`,
        )
        .join("\n")}`,
    );
  }
  process.stdout.write(
    `Browser-fit validation passed for ${presentation.slides.length} slides at ${VIEWPORTS.map(({ width, height }) => `${width}x${height}`).join(", ")} across ${ISOLATED_PASSES} isolated passes.\n`,
  );
}

if (isMainModule(import.meta.url)) {
  checkBrowserFit();
}
