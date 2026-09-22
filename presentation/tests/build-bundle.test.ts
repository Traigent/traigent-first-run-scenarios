import { createHash } from "node:crypto";
import {
  mkdtemp,
  mkdir,
  readFile,
  rm,
  symlink,
  writeFile,
} from "node:fs/promises";
import os from "node:os";
import path from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import {
  assertNoForbiddenRuntimeSource,
  assertSelfContainedHtml,
  buildCustomerBundle,
  buildThirdPartyNotices,
  BundleBuildError,
  discoverRuntimePackageNames,
  resolveBuildTimestamp,
  resolveGitMetadata,
  type GitMetadata,
} from "../scripts/build-bundle";
import { pptxFileName } from "../scripts/build-pptx";
import { presentationRoot, repositoryRoot } from "../scripts/runtime";
import { presentation } from "../src/content";

const temporaryDirectories: string[] = [];
const COMMITTED_GIT_METADATA: GitMetadata = {
  revision: "0123456789abcdef0123456789abcdef01234567",
  state: "committed",
  commitSha: "0123456789abcdef0123456789abcdef01234567",
  commitEpochSeconds: 1_700_000_000,
};

interface ManifestShape {
  schema_version: number;
  generated_at: string;
  source: {
    revision: string;
    state: string;
    commit_sha: string | null;
  };
  deck: {
    schema_version: number;
    evidence_states: string[];
    guide_contract_source_revisions: string[];
    slide_count: number;
    slides: Array<{
      id: string;
      evidence_state: string;
      source_revision: string | null;
    }>;
  };
  offline: {
    self_contained_html: boolean;
    runtime_network_dependencies: boolean;
    verified_by: {
      source_files_scanned: number;
      built_html_elements_read: number;
      browser_execution_observed: boolean;
    };
  };
  licensing: {
    repository_spdx_license: string;
    repository_license_file: string;
    repository_notice_file: string;
    third_party_notices_file: string;
  };
  artifacts: Array<{
    path: string;
    bytes: number;
    sha256: string;
  }>;
}

async function temporaryDirectory(prefix: string): Promise<string> {
  const directory = await mkdtemp(path.join(os.tmpdir(), prefix));
  temporaryDirectories.push(directory);
  return directory;
}

function hash(value: Uint8Array): string {
  return createHash("sha256").update(value).digest("hex");
}

afterEach(async () => {
  await Promise.all(
    temporaryDirectories
      .splice(0)
      .map((directory) => rm(directory, { recursive: true, force: true })),
  );
});

describe("offline bundle validation", () => {
  it("allows an inline deck and visible hyperlink without a network dependency", () => {
    const html =
      '<!doctype html><a href="https://example.invalid">Source</a><style>.icon{background:url(data:image/svg+xml;base64,AA==)}</style><script>const schema={url(value){return value}}</script>';

    expect(() => assertSelfContainedHtml(html)).not.toThrow();
  });

  it.each([
    '<script src="app.js"></script>',
    '<link rel="stylesheet" href="styles.css">',
    '<link rel="icon" href="https://example.invalid/icon.ico">',
    '<img src="remote.png">',
    '<img srcset="small.png 1x, large.png 2x">',
    '<style>.hero{background:url("remote.png")}</style>',
    '<style>@import "remote.css";</style>',
    '<base href="https://example.invalid/">',
    '<object data="https://example.invalid/object"></object>',
    '<embed src="https://example.invalid/embed">',
    '<video poster="https://example.invalid/poster.png"></video>',
    '<svg><image href="https://example.invalid/image.svg"/></svg>',
    '<meta http-equiv="refresh" content="0;url=https://example.invalid">',
    '<form action="https://example.invalid"><button>Submit</button></form>',
    '<a href="https://example.invalid" ping="https://tracker.invalid">Source</a>',
    '<html manifest="https://example.invalid/deck.appcache"></html>',
  ])("rejects external runtime resources: %s", (html) => {
    expect(() => assertSelfContainedHtml(html)).toThrowError(BundleBuildError);
  });

  it("rejects network calls in presentation source", async () => {
    const sourceDirectory = await temporaryDirectory("presentation-source-");
    await writeFile(
      path.join(sourceDirectory, "unsafe.ts"),
      'export async function load() { return fetch("https://example.invalid"); }\n',
      "utf8",
    );

    await expect(
      assertNoForbiddenRuntimeSource(sourceDirectory),
    ).rejects.toThrowError("fetch");
  });

  it("rejects aliased network capabilities in presentation source", async () => {
    const sourceDirectory = await temporaryDirectory("presentation-source-");
    await writeFile(
      path.join(sourceDirectory, "unsafe.ts"),
      'const request = fetch; export function load() { return request("https://example.invalid"); }\n',
      "utf8",
    );

    await expect(
      assertNoForbiddenRuntimeSource(sourceDirectory),
    ).rejects.toThrowError("fetch");
  });

  it("accepts local, declarative presentation source", async () => {
    const sourceDirectory = await temporaryDirectory("presentation-source-");
    await writeFile(
      path.join(sourceDirectory, "safe.ts"),
      'export const customerLink = "https://example.invalid";\n',
      "utf8",
    );

    await expect(
      assertNoForbiddenRuntimeSource(sourceDirectory),
    ).resolves.toMatchObject({
      selfContainedHtml: true,
      runtimeNetworkDependencies: false,
    });
  });

  it("rejects symbolic links anywhere in a presentation source walk", async () => {
    const temporaryRoot = await temporaryDirectory("presentation-source-");
    const sourceDirectory = path.join(temporaryRoot, "src");
    await mkdir(sourceDirectory);
    await writeFile(
      path.join(temporaryRoot, "outside.ts"),
      "export const value = 1;\n",
    );
    await symlink(
      path.join(temporaryRoot, "outside.ts"),
      path.join(sourceDirectory, "linked.ts"),
    );

    await expect(
      assertNoForbiddenRuntimeSource(sourceDirectory),
    ).rejects.toThrowError("Symbolic links are not allowed");
  });

  it.each([
    ["beacon.js", "js"],
    ["beacon.mjs", "mjs"],
    ["beacon.cjs", "cjs"],
    ["Beacon.TSX", "upper-case TSX"],
    ["beacon.jsx", "jsx"],
  ])(
    "scans %s, because every file the bundler can reach ships to the customer",
    async (fileName) => {
      const sourceDirectory = await temporaryDirectory("presentation-source-");
      await writeFile(
        path.join(sourceDirectory, fileName),
        'export function report() { fetch("https://telemetry.invalid/deck-opened", { method: "POST" }); }\n',
        "utf8",
      );

      await expect(
        assertNoForbiddenRuntimeSource(sourceDirectory),
      ).rejects.toThrowError(`${fileName}: network capability fetch`);
    },
  );

  it("refuses a source file it cannot classify instead of walking past it", async () => {
    const sourceDirectory = await temporaryDirectory("presentation-source-");
    await writeFile(
      path.join(sourceDirectory, "runtime.wasm"),
      "\u0000asm-fixture\n",
      "utf8",
    );

    await expect(
      assertNoForbiddenRuntimeSource(sourceDirectory),
    ).rejects.toThrowError("cannot classify");
  });

  it("follows an import out of the source tree, where a walk would not look", async () => {
    const temporaryRoot = await temporaryDirectory("presentation-source-");
    const sourceDirectory = path.join(temporaryRoot, "src");
    await mkdir(sourceDirectory);
    await writeFile(
      path.join(temporaryRoot, "beacon.ts"),
      'const endpoint = "https://telemetry.invalid/deck-opened";\nexport function report() { fetch(endpoint, { method: "POST" }); }\n',
      "utf8",
    );
    await writeFile(
      path.join(sourceDirectory, "main.ts"),
      'import { report } from "../beacon";\nreport();\n',
      "utf8",
    );

    await expect(
      assertNoForbiddenRuntimeSource(sourceDirectory),
    ).rejects.toThrowError("../beacon.ts: network capability fetch");
  });

  it("refuses an import it cannot resolve rather than assuming it is inert", async () => {
    const sourceDirectory = await temporaryDirectory("presentation-source-");
    await writeFile(
      path.join(sourceDirectory, "main.ts"),
      'import { value } from "./missing-module";\nexport const used = value;\n',
      "utf8",
    );

    await expect(
      assertNoForbiddenRuntimeSource(sourceDirectory),
    ).rejects.toThrowError("cannot resolve to a file it can read");
  });

  it("records but does not scan an inert data file the bundler can inline", async () => {
    const sourceDirectory = await temporaryDirectory("presentation-source-");
    await writeFile(
      path.join(sourceDirectory, "main.ts"),
      'import facts from "./facts.json";\nexport const rows = facts;\n',
      "utf8",
    );
    await writeFile(
      path.join(sourceDirectory, "facts.json"),
      '{"documentation":"https://example.invalid/reference"}\n',
      "utf8",
    );

    await expect(
      assertNoForbiddenRuntimeSource(sourceDirectory),
    ).resolves.toMatchObject({ filesScanned: 2 });
  });

  it("scans a stylesheet that ships from source for external resources", async () => {
    const sourceDirectory = await temporaryDirectory("presentation-source-");
    await writeFile(
      path.join(sourceDirectory, "styles.css"),
      '@import url("https://fonts.invalid/deck.css");\n',
      "utf8",
    );

    await expect(
      assertNoForbiddenRuntimeSource(sourceDirectory),
    ).rejects.toThrowError("external CSS resource");
  });

  it("accepts a stylesheet whose resources are inline", async () => {
    const sourceDirectory = await temporaryDirectory("presentation-source-");
    await writeFile(
      path.join(sourceDirectory, "styles.css"),
      ".icon{background:url(data:image/svg+xml;base64,AA==)}\n",
      "utf8",
    );

    await expect(
      assertNoForbiddenRuntimeSource(sourceDirectory),
    ).resolves.toMatchObject({
      selfContainedHtml: true,
      runtimeNetworkDependencies: false,
    });
  });

  it.each([
    '<script>fetch("https://telemetry.invalid/deck-opened",{method:"POST"})</script>',
    "<script>fetch(`https://telemetry.invalid/deck-opened`)</script>",
    '<script>new WebSocket("wss://telemetry.invalid/socket")</script>',
    '<script>new EventSource("https://telemetry.invalid/stream")</script>',
    '<script>navigator.sendBeacon("https://telemetry.invalid/beacon")</script>',
    '<script type="module">import("https://cdn.invalid/plugin.js")</script>',
    '<script>const s=document.createElement("script");s.src="https://cdn.invalid/plugin.js";document.head.appendChild(s)</script>',
    '<script>const l=document.createElement("link");l.rel="stylesheet";l.href="https://cdn.invalid/deck.css";document.head.appendChild(l)</script>',
    '<script>document.createElement("img").setAttribute("src","https://telemetry.invalid/pixel.gif")</script>',
    // A regular expression ending in an escaped `//` would begin a comment if
    // the script were read as text, hiding everything after it on the line.
    '<script>const p=/^https?:\\/\\//;fetch("https://telemetry.invalid/after-a-regexp")</script>',
    // An object literal, not a block, so the `/` after `}` divides.
    '<script>const r=({a:1}/1);fetch("https://telemetry.invalid/after-a-division")</script>',
    // A name reached by computed member access spells the same capability.
    '<script>navigator["sendBeacon"]("https://telemetry.invalid/beacon")</script>',
    '<script>a["href"]="https://telemetry.invalid/computed"</script>',
    // A no-break space separates tokens in JavaScript but is not a name part.
    '<script>fetch\u00a0("https://telemetry.invalid/nbsp")</script>',
    // An identifier may spell its own characters as escapes.
    '<script>new \\u0057ebSocket("wss://telemetry.invalid/escaped")</script>',
    // A markup sink carries the address inside a tag rather than as the value.
    `<script>document.body.innerHTML='<img src="https://telemetry.invalid/pixel.gif">'</script>`,
  ])("rejects a runtime network dependency inside the deck: %s", (html) => {
    expect(() => assertSelfContainedHtml(html)).toThrowError(BundleBuildError);
  });

  it.each([
    "<p>Reviewers ask why &lt;script src=&quot;app.js&quot;&gt; never appears in the bundle.</p>",
    "<p>&lt;link href&gt;, &lt;img srcset&gt; and &lt;iframe&gt; are all refused by the offline gate.</p>",
    "<p>The deck never calls fetch() and never opens a WebSocket.</p>",
    "<p>A deck that loaded https://fonts.example.invalid/deck.css would not be offline.</p>",
    '<script>const prompt="Clone https://github.com/Traigent/traigent-first-run and follow GUIDE.md.";document.title=prompt</script>',
    "<script>const pattern=/^https?:\\/\\//;const ok=!pattern.test(location.hash)</script>",
  ])("accepts deck copy that only describes the network: %s", (body) => {
    expect(() =>
      assertSelfContainedHtml(
        `<!doctype html><html><body>${body}</body></html>`,
      ),
    ).not.toThrow();
  });

  it("accepts a resource the document carries inline", () => {
    expect(() =>
      assertSelfContainedHtml(
        '<!doctype html><html><head><link rel="icon" href="data:image/svg+xml,%3Csvg/%3E"></head><body></body></html>',
      ),
    ).not.toThrow();
  });

  it("accepts deck copy inside the bundled script that quotes a script tag", () => {
    // Slide copy is emitted into the inline bundle as a string literal, where
    // its angle brackets are not escaped. Only a `</script` sequence ends the
    // block, so text like this is script content, never a second element.
    expect(() =>
      assertSelfContainedHtml(
        '<!doctype html><html><body><script>const copy="Never ship a <script src= tag to a customer";document.title=copy</script></body></html>',
      ),
    ).not.toThrow();
  });

  it.each([
    '<script type="importmap">{"imports":{"react":"https://cdn.invalid/react.js"}}</script>',
    '<script type="speculationrules">{"prefetch":[{"urls":["https://telemetry.invalid/p"]}]}</script>',
  ])(
    "rejects a script whose whole purpose is to name resources: %s",
    (html) => {
      expect(() => assertSelfContainedHtml(html)).toThrowError(
        "resource-directing script",
      );
    },
  );

  it.each([
    '<frame src="https://example.invalid/frame">',
    '<body background="https://example.invalid/tile.png"></body>',
  ])("rejects a legacy external reference: %s", (html) => {
    expect(() => assertSelfContainedHtml(html)).toThrowError(BundleBuildError);
  });

  it("refuses an artifact it cannot read as a document", () => {
    expect(() =>
      assertSelfContainedHtml(
        '<!doctype html><html><body><svg><script/></svg><script src="https://cdn.invalid/beacon.js"></script></body></html>',
      ),
    ).toThrowError("cannot be read as a document");
  });

  it("discovers nested static, dynamic, and CommonJS runtime imports", async () => {
    const sourceDirectory = await temporaryDirectory("presentation-imports-");
    const nestedDirectory = path.join(sourceDirectory, "nested");
    await mkdir(nestedDirectory);
    await writeFile(
      path.join(sourceDirectory, "entry.ts"),
      [
        'import React from "react";',
        'export const visibleLink = "https://example.invalid";',
        'export { createPortal } from "react-dom";',
      ].join("\n"),
    );
    await writeFile(
      path.join(nestedDirectory, "runtime.ts"),
      [
        'export async function load() { return import("react-dom/client"); }',
        'export function validate() { return require("zod"); }',
      ].join("\n"),
    );

    await expect(discoverRuntimePackageNames(sourceDirectory)).resolves.toEqual(
      ["react", "react-dom", "zod"],
    );
  });

  it("rejects nonliteral dynamic dependencies because they cannot be inventoried", async () => {
    const sourceDirectory = await temporaryDirectory("presentation-imports-");
    await writeFile(
      path.join(sourceDirectory, "runtime.ts"),
      "export async function load(name: string) { return import(name); }\n",
    );

    await expect(
      discoverRuntimePackageNames(sourceDirectory),
    ).rejects.toThrowError("Dynamic import must use a string literal");
  });

  it("fails explicitly when no Git checkout can provide provenance", async () => {
    const directory = await temporaryDirectory("presentation-no-git-");

    expect(() => resolveGitMetadata(directory)).toThrowError(
      "Unable to resolve Git revision",
    );
  });

  it("uses SOURCE_DATE_EPOCH when supplied and otherwise uses commit time", () => {
    expect(resolveBuildTimestamp(10, undefined)).toBe(
      "1970-01-01T00:00:10.000Z",
    );
    expect(resolveBuildTimestamp(10, "20")).toBe("1970-01-01T00:00:20.000Z");
    expect(() => resolveBuildTimestamp(10, "now")).toThrowError(
      BundleBuildError,
    );
  });
});

describe("customer bundle", () => {
  it("includes full notices only for runtime code emitted into the web deck", async () => {
    const notices = await buildThirdPartyNotices(
      presentationRoot,
      path.join(presentationRoot, "src"),
    );

    expect(notices).toContain("react@19.2.8");
    expect(notices).toContain("react-dom@19.2.8");
    expect(notices).toContain("scheduler@0.27.0");
    expect(notices).toContain("zod@4.5.4");
    expect(notices).toContain("MIT License");
    expect(notices).toContain("Copyright");
    expect(notices).not.toContain("pptxgenjs@");
    expect(notices).not.toContain("image-size@");
    expect(notices).not.toContain("vite@");
  });

  it("builds a deterministic contract-only bundle with stable checksums", async () => {
    const temporaryRoot = await temporaryDirectory("presentation-bundle-");
    const distDirectory = path.join(temporaryRoot, "dist");
    const outputDirectory = path.join(distDirectory, "customer-bundle");
    await mkdir(distDirectory, { recursive: true });
    await writeFile(
      path.join(distDirectory, "index.html"),
      '<!doctype html><html><body><script>document.body.dataset.ready="yes"</script></body></html>\n',
      "utf8",
    );
    await writeFile(
      path.join(distDirectory, pptxFileName),
      "pptx-fixture",
      "utf8",
    );

    const buildOptions = {
      distDirectory,
      outputDirectory,
      packageDirectory: presentationRoot,
      sourceDirectory: path.join(presentationRoot, "src"),
      gitMetadata: COMMITTED_GIT_METADATA,
      sourceDateEpoch: "1800000000",
      spec: presentation,
    } as const;
    const first = await buildCustomerBundle(buildOptions);
    const firstChecksums = await readFile(first.checksumsPath, "utf8");
    const second = await buildCustomerBundle(buildOptions);
    const secondChecksums = await readFile(second.checksumsPath, "utf8");

    expect(secondChecksums).toBe(firstChecksums);
    const manifest = JSON.parse(
      await readFile(second.manifestPath, "utf8"),
    ) as ManifestShape;
    expect(manifest.schema_version).toBe(2);
    expect(manifest.generated_at).toBe("2027-01-15T08:00:00.000Z");
    expect(manifest.source).toEqual({
      revision: COMMITTED_GIT_METADATA.revision,
      state: "committed",
      commit_sha: COMMITTED_GIT_METADATA.commitSha,
    });
    expect(manifest.deck.evidence_states).toEqual([
      "guide-contract",
      "scenario-contract",
    ]);
    expect(manifest.deck.guide_contract_source_revisions).toEqual([
      "d07b62cd4abb6ecb6d2edcdcb2d535f02bb2c199",
    ]);
    expect(manifest.deck.schema_version).toBe(2);
    expect(manifest.deck).not.toHaveProperty("evidence_state");
    expect(manifest.deck).not.toHaveProperty("guide_sha");
    expect(manifest.deck).not.toHaveProperty("guide_sha_reason");
    expect(manifest.deck).not.toHaveProperty("slide_ids");
    expect(manifest.deck.slide_count).toBe(presentation.slides.length);
    expect(manifest.deck.slides).toEqual(
      presentation.slides.map((slide) => ({
        id: slide.id,
        evidence_state: slide.evidenceState,
        source_revision: slide.sourceRevision ?? null,
      })),
    );
    expect(manifest.offline.self_contained_html).toBe(true);
    expect(manifest.offline.runtime_network_dependencies).toBe(false);
    // The block says what the checks establish: the artifact was read, not run.
    expect(manifest.offline.verified_by.browser_execution_observed).toBe(false);
    expect(
      manifest.offline.verified_by.source_files_scanned,
    ).toBeGreaterThanOrEqual(presentation.slides.length > 0 ? 1 : 0);
    expect(
      manifest.offline.verified_by.built_html_elements_read,
    ).toBeGreaterThan(0);
    expect(manifest.licensing).toEqual({
      repository_spdx_license: "Apache-2.0",
      repository_license_file: "LICENSE",
      repository_notice_file: "NOTICE",
      third_party_notices_file: "THIRD_PARTY_NOTICES.txt",
    });
    expect(manifest.artifacts.map((artifact) => artifact.path)).toEqual([
      "LICENSE",
      "NOTICE",
      "THIRD_PARTY_NOTICES.txt",
      "presentation.html",
      "presentation.pptx",
    ]);
    for (const artifact of manifest.artifacts) {
      const contents = await readFile(
        path.join(second.outputDirectory, artifact.path),
      );
      expect(artifact.bytes).toBe(contents.byteLength);
      expect(artifact.sha256).toBe(hash(contents));
    }

    const checksumLines = secondChecksums.trim().split("\n");
    const checksumPaths = checksumLines.map((line) => line.slice(66));
    expect(checksumPaths).toEqual([...checksumPaths].sort());
    expect(checksumPaths).toEqual([
      "LICENSE",
      "NOTICE",
      "THIRD_PARTY_NOTICES.txt",
      "build-manifest.json",
      "presentation.html",
      "presentation.pptx",
    ]);
    expect(checksumPaths).not.toContain("checksums.txt");
    for (const line of checksumLines) {
      const [expectedHash, relativePath] = line.split("  ");
      expect(expectedHash).toBe(
        hash(await readFile(path.join(second.outputDirectory, relativePath!))),
      );
    }

    const notices = await readFile(
      path.join(second.outputDirectory, "THIRD_PARTY_NOTICES.txt"),
      "utf8",
    );
    expect(notices).not.toContain("pptxgenjs@");
    expect(notices).not.toContain("image-size@");
    await expect(
      readFile(path.join(second.outputDirectory, "LICENSE")),
    ).resolves.toEqual(await readFile(path.join(repositoryRoot, "LICENSE")));
    await expect(
      readFile(path.join(second.outputDirectory, "NOTICE")),
    ).resolves.toEqual(await readFile(path.join(repositoryRoot, "NOTICE")));

    const alternateGuideRevision = "1".repeat(40);
    const mutatedSpec = structuredClone(presentation);
    for (const slide of mutatedSpec.slides) {
      if (slide.evidenceState === "guide-contract") {
        slide.sourceRevision = alternateGuideRevision;
      }
    }
    mutatedSpec.slides[0]!.evidenceState = "not-demonstrated";
    delete mutatedSpec.slides[0]!.sourceRevision;
    const mutated = await buildCustomerBundle({
      ...buildOptions,
      spec: mutatedSpec,
    });
    const mutatedManifest = JSON.parse(
      await readFile(mutated.manifestPath, "utf8"),
    ) as ManifestShape;
    expect(mutatedManifest.deck.guide_contract_source_revisions).toEqual([
      alternateGuideRevision,
    ]);
    expect(mutatedManifest.deck.slides[0]).toEqual({
      id: mutatedSpec.slides[0]!.id,
      evidence_state: "not-demonstrated",
      source_revision: null,
    });
  });

  it("refuses a same-named output directory outside the selected dist directory", async () => {
    const temporaryRoot = await temporaryDirectory("presentation-bundle-path-");
    const distDirectory = path.join(temporaryRoot, "dist");
    const outputDirectory = path.join(
      temporaryRoot,
      "other",
      "customer-bundle",
    );
    await mkdir(outputDirectory, { recursive: true });
    const sentinelPath = path.join(outputDirectory, "keep.txt");
    await writeFile(sentinelPath, "keep\n");

    await expect(
      buildCustomerBundle({
        distDirectory,
        outputDirectory,
        gitMetadata: COMMITTED_GIT_METADATA,
      }),
    ).rejects.toThrowError("must be exactly");
    await expect(readFile(sentinelPath, "utf8")).resolves.toBe("keep\n");
  });

  it("preserves an existing bundle when notice generation fails", async () => {
    const temporaryRoot = await temporaryDirectory(
      "presentation-bundle-notice-",
    );
    const distDirectory = path.join(temporaryRoot, "dist");
    const outputDirectory = path.join(distDirectory, "customer-bundle");
    const invalidPackageDirectory = path.join(temporaryRoot, "invalid-package");
    await mkdir(outputDirectory, { recursive: true });
    await mkdir(invalidPackageDirectory);
    await writeFile(path.join(outputDirectory, "keep.txt"), "known-good\n");
    await writeFile(
      path.join(distDirectory, "index.html"),
      "<!doctype html>\n",
    );
    await writeFile(path.join(distDirectory, pptxFileName), "pptx-fixture");

    await expect(
      buildCustomerBundle({
        distDirectory,
        outputDirectory,
        packageDirectory: invalidPackageDirectory,
        sourceDirectory: path.join(presentationRoot, "src"),
        gitMetadata: COMMITTED_GIT_METADATA,
      }),
    ).rejects.toThrowError("Unable to load");
    await expect(
      readFile(path.join(outputDirectory, "keep.txt"), "utf8"),
    ).resolves.toBe("known-good\n");
  });

  it.each(["LICENSE", "NOTICE"] as const)(
    "preserves an existing bundle when repository %s is absent",
    async (missingFileName) => {
      const temporaryRoot = await temporaryDirectory(
        "presentation-bundle-legal-",
      );
      const repositoryDirectory = path.join(temporaryRoot, "repository");
      const distDirectory = path.join(temporaryRoot, "dist");
      const outputDirectory = path.join(distDirectory, "customer-bundle");
      const retainedFileName =
        missingFileName === "LICENSE" ? "NOTICE" : "LICENSE";
      await mkdir(repositoryDirectory, { recursive: true });
      await mkdir(outputDirectory, { recursive: true });
      await writeFile(
        path.join(repositoryDirectory, retainedFileName),
        await readFile(path.join(repositoryRoot, retainedFileName)),
      );
      await writeFile(path.join(outputDirectory, "keep.txt"), "known-good\n");

      await expect(
        buildCustomerBundle({
          distDirectory,
          outputDirectory,
          repositoryDirectory,
          gitMetadata: COMMITTED_GIT_METADATA,
        }),
      ).rejects.toThrowError(`Repository ${missingFileName} is missing`);
      await expect(
        readFile(path.join(outputDirectory, "keep.txt"), "utf8"),
      ).resolves.toBe("known-good\n");
    },
  );

  it.each(["LICENSE", "NOTICE"] as const)(
    "preserves an existing bundle when repository %s is a symbolic link",
    async (linkedFileName) => {
      const temporaryRoot = await temporaryDirectory(
        "presentation-bundle-legal-link-",
      );
      const repositoryDirectory = path.join(temporaryRoot, "repository");
      const distDirectory = path.join(temporaryRoot, "dist");
      const outputDirectory = path.join(distDirectory, "customer-bundle");
      const externalFilePath = path.join(
        temporaryRoot,
        `external-${linkedFileName.toLowerCase()}`,
      );
      const retainedFileName =
        linkedFileName === "LICENSE" ? "NOTICE" : "LICENSE";
      await mkdir(repositoryDirectory, { recursive: true });
      await mkdir(outputDirectory, { recursive: true });
      await writeFile(
        externalFilePath,
        await readFile(path.join(repositoryRoot, linkedFileName)),
      );
      await symlink(
        externalFilePath,
        path.join(repositoryDirectory, linkedFileName),
      );
      await writeFile(
        path.join(repositoryDirectory, retainedFileName),
        await readFile(path.join(repositoryRoot, retainedFileName)),
      );
      await writeFile(path.join(outputDirectory, "keep.txt"), "known-good\n");

      await expect(
        buildCustomerBundle({
          distDirectory,
          outputDirectory,
          repositoryDirectory,
          gitMetadata: COMMITTED_GIT_METADATA,
        }),
      ).rejects.toThrowError(
        `Repository ${linkedFileName} must be a regular file, not a symbolic link`,
      );
      await expect(
        readFile(path.join(outputDirectory, "keep.txt"), "utf8"),
      ).resolves.toBe("known-good\n");
    },
  );

  it.each(["LICENSE", "NOTICE"] as const)(
    "preserves an existing bundle when repository %s is empty",
    async (emptyFileName) => {
      const temporaryRoot = await temporaryDirectory(
        "presentation-bundle-legal-empty-",
      );
      const repositoryDirectory = path.join(temporaryRoot, "repository");
      const distDirectory = path.join(temporaryRoot, "dist");
      const outputDirectory = path.join(distDirectory, "customer-bundle");
      const retainedFileName =
        emptyFileName === "LICENSE" ? "NOTICE" : "LICENSE";
      await mkdir(repositoryDirectory, { recursive: true });
      await mkdir(outputDirectory, { recursive: true });
      await writeFile(path.join(repositoryDirectory, emptyFileName), "");
      await writeFile(
        path.join(repositoryDirectory, retainedFileName),
        await readFile(path.join(repositoryRoot, retainedFileName)),
      );
      await writeFile(path.join(outputDirectory, "keep.txt"), "known-good\n");

      await expect(
        buildCustomerBundle({
          distDirectory,
          outputDirectory,
          repositoryDirectory,
          gitMetadata: COMMITTED_GIT_METADATA,
        }),
      ).rejects.toThrowError(`Repository ${emptyFileName} is empty`);
      await expect(
        readFile(path.join(outputDirectory, "keep.txt"), "utf8"),
      ).resolves.toBe("known-good\n");
    },
  );

  it("preserves an existing bundle when LICENSE is not Apache-2.0", async () => {
    const temporaryRoot = await temporaryDirectory(
      "presentation-bundle-legal-wrong-license-",
    );
    const repositoryDirectory = path.join(temporaryRoot, "repository");
    const distDirectory = path.join(temporaryRoot, "dist");
    const outputDirectory = path.join(distDirectory, "customer-bundle");
    await mkdir(repositoryDirectory, { recursive: true });
    await mkdir(outputDirectory, { recursive: true });
    await writeFile(
      path.join(repositoryDirectory, "LICENSE"),
      "A different license\n",
    );
    await writeFile(
      path.join(repositoryDirectory, "NOTICE"),
      await readFile(path.join(repositoryRoot, "NOTICE")),
    );
    await writeFile(path.join(outputDirectory, "keep.txt"), "known-good\n");

    await expect(
      buildCustomerBundle({
        distDirectory,
        outputDirectory,
        repositoryDirectory,
        gitMetadata: COMMITTED_GIT_METADATA,
      }),
    ).rejects.toThrowError("is not an Apache License 2.0 text");
    await expect(
      readFile(path.join(outputDirectory, "keep.txt"), "utf8"),
    ).resolves.toBe("known-good\n");
  });
});
