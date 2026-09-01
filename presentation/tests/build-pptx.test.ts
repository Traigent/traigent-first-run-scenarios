import { readFile, readdir } from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";

import JSZip from "jszip";
import { describe, expect, it } from "vitest";

import { renderPptxBuffer } from "../scripts/build-pptx";
import { presentationRoot } from "../scripts/runtime";
import { presentation } from "../src/content";
import { evidenceLabel } from "../src/model";

function decodeXmlText(value: string): string {
  return value
    .replaceAll("&lt;", "<")
    .replaceAll("&gt;", ">")
    .replaceAll("&quot;", '"')
    .replaceAll("&apos;", "'")
    .replaceAll("&amp;", "&");
}

function textFromXml(xml: string): string {
  return [...xml.matchAll(/<a:t>([\s\S]*?)<\/a:t>/g)]
    .map((match) => decodeXmlText(match[1] ?? ""))
    .join("\n");
}

function numericPart(fileName: string): number {
  const match = fileName.match(/(\d+)\.xml$/);
  if (match === null) {
    throw new Error(`Expected a numbered XML part: ${fileName}`);
  }
  return Number(match[1]);
}

async function javascriptFiles(directory: string): Promise<string[]> {
  const entries = await readdir(directory, { withFileTypes: true });
  const files: string[] = [];
  for (const entry of entries) {
    const entryPath = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      files.push(...(await javascriptFiles(entryPath)));
    } else if (entry.isFile() && /\.[cm]?js$/.test(entry.name)) {
      files.push(entryPath);
    }
  }
  return files.sort();
}

function hasImageSizeRuntimeReference(source: string): boolean {
  return /(?:require|import)\s*\(\s*["']image-size["']\s*\)|\bfrom\s*["']image-size["']|\bimport\s*["']image-size["']/.test(
    source,
  );
}

describe("PowerPoint export", () => {
  it("preserves slide order, titles, and speaker notes with native editable shapes", async () => {
    const archive = await JSZip.loadAsync(await renderPptxBuffer());
    const slidePaths = Object.keys(archive.files)
      .filter((name) => /^ppt\/slides\/slide\d+\.xml$/.test(name))
      .sort((left, right) => numericPart(left) - numericPart(right));
    const notePaths = Object.keys(archive.files)
      .filter((name) => /^ppt\/notesSlides\/notesSlide\d+\.xml$/.test(name))
      .sort((left, right) => numericPart(left) - numericPart(right));

    expect(slidePaths).toHaveLength(presentation.slides.length);
    expect(notePaths).toHaveLength(presentation.slides.length);
    expect(
      Object.keys(archive.files).some(
        (name) => name.startsWith("ppt/media/") && name !== "ppt/media/",
      ),
    ).toBe(false);

    for (const [index, slideSpec] of presentation.slides.entries()) {
      const slideXml = await archive.file(slidePaths[index]!)!.async("string");
      const notesXml = await archive.file(notePaths[index]!)!.async("string");
      expect(textFromXml(slideXml)).toContain(slideSpec.title);
      expect(slideXml).toMatch(/<p:ph\b[^>]*\btype="title"/);
      expect(slideXml).toContain("<p:sp>");
      expect(slideXml).not.toContain("<p:pic>");
      const slideText = textFromXml(slideXml);
      expect(slideText).toContain(evidenceLabel(slideSpec.evidenceState));
      for (const evidenceReference of slideSpec.evidence) {
        expect(slideText).toContain(evidenceReference);
      }
      if (slideSpec.evidenceState === "guide-contract") {
        expect(slideText).toContain(slideSpec.sourceRevision!.slice(0, 8));
      }
      for (const row of slideSpec.matrix ?? []) {
        expect(slideText).toContain(row.startingPoint);
        expect(slideText).toContain(row.safestNextStep);
      }
      for (const row of slideSpec.testMatrix ?? []) {
        expect(slideText).toContain(row.layer);
        expect(slideText).toContain(row.passSupports);
        expect(slideText).toContain(row.doesNotProve);
      }
      for (const row of slideSpec.scenarioMatrix ?? []) {
        expect(slideText).toContain(row.family);
        expect(slideText).toContain(row.setup);
        expect(slideText).toContain(row.expectedRoute);
      }
      for (const note of slideSpec.notes) {
        expect(textFromXml(notesXml)).toContain(note);
      }
    }
  });

  it("is byte-reproducible for a fixed source epoch", async () => {
    const epochSeconds = 1_800_000_000;
    const first = await renderPptxBuffer(presentation, epochSeconds);
    const second = await renderPptxBuffer(presentation, epochSeconds);

    expect(second.equals(first)).toBe(true);
    const archive = await JSZip.loadAsync(second);
    const coreProperties = await archive
      .file("docProps/core.xml")!
      .async("string");
    expect(coreProperties).toContain("2027-01-15T08:00:00Z");
  });

  it("does not execute the vulnerable image-size parser from shipped PptxGenJS code", async () => {
    const distDirectory = path.join(
      presentationRoot,
      "node_modules",
      "pptxgenjs",
      "dist",
    );
    const references: string[] = [];
    for (const filePath of await javascriptFiles(distDirectory)) {
      const source = await readFile(filePath, "utf8");
      if (hasImageSizeRuntimeReference(source)) {
        references.push(filePath);
      }
    }

    expect(references).toEqual([]);
  });

  it("uses a parser-free replacement that fails closed if loaded", async () => {
    const guardDirectory = path.join(
      presentationRoot,
      "vendor",
      "image-size-disabled",
    );
    const guardFiles = (await readdir(guardDirectory)).sort();
    const guardSource = await readFile(
      path.join(guardDirectory, "index.cjs"),
      "utf8",
    );

    expect(guardFiles).toEqual([
      "LICENSE",
      "README.md",
      "index.cjs",
      "package.json",
    ]);
    expect(guardSource).toContain("Image parsing is disabled");
    expect(guardSource).not.toMatch(
      /\b(?:readFile|createReadStream|Buffer|Uint8Array|PNG|JPEG|GIF|WebP)\b/,
    );
    await expect(
      import(pathToFileURL(path.join(guardDirectory, "index.cjs")).href),
    ).rejects.toThrow("this presentation build supports no images");
  });
});
