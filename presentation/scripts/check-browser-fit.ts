import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { pathToFileURL } from "node:url";

import { presentation } from "../src/content";
import { distRoot, isMainModule } from "./runtime";

const VIEWPORTS = [
  { width: 1366, height: 768 },
  { width: 1600, height: 900 },
] as const;
const ISOLATED_PASSES = 2;

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
  throw new Error(
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

function measureViewportInsets(
  chrome: string,
  profileDirectory: string,
): ViewportInsets {
  const requested = { width: 1000, height: 800 };
  const probe = encodeURIComponent(
    "<body><script>document.documentElement.dataset.viewport=innerWidth+'x'+innerHeight</script></body>",
  );
  const html = execFileSync(
    chrome,
    [
      ...isolatedChromeArguments(profileDirectory),
      `--window-size=${requested.width},${requested.height}`,
      "--dump-dom",
      `data:text/html,${probe}`,
    ],
    {
      encoding: "utf8",
      maxBuffer: 1024 * 1024,
      timeout: 10_000,
      stdio: ["ignore", "pipe", "pipe"],
    },
  );
  const dimensions = html.match(/data-viewport="(\d+)x(\d+)"/);
  if (dimensions === null) {
    throw new Error("Could not measure the isolated browser viewport");
  }
  const innerWidth = Number(dimensions[1]);
  const innerHeight = Number(dimensions[2]);
  const insets = {
    width: requested.width - innerWidth,
    height: requested.height - innerHeight,
  };
  if (insets.width < 0 || insets.height < 0) {
    throw new Error(
      `Browser viewport exceeded its requested window: ${innerWidth}x${innerHeight}`,
    );
  }
  return insets;
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
  const renderedSlide = html.match(/data-fit-slide="([^"]*)"/)?.[1];
  if (renderedSlide !== id) {
    // An unknown hash id silently falls back to the first slide, so a pass
    // for the wrong slide means the requested slide was never measured.
    return {
      id,
      pass,
      viewport: `${width}x${height}`,
      detail: `rendered slide "${renderedSlide ?? "none"}" instead of "${id}" (stale dist/?)`,
    };
  }
  if (html.includes('data-fit-status="pass"')) {
    return null;
  }
  const detail =
    html.match(/data-fit-detail="([^"]*)"/)?.[1] ??
    "fit measurement did not complete";
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
    throw new Error(
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
