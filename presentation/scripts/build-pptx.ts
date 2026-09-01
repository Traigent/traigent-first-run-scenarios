import { execFileSync } from "node:child_process";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

import JSZip from "jszip";
import PptxGenJS from "pptxgenjs";

import { brandBlue, brandName } from "../src/brand";
import { presentation } from "../src/content";
import {
  coverageLabel,
  displayEyebrow,
  evidenceLabel,
  type CatalogEntry,
  type PresentationSpec,
  type SlideSpec,
} from "../src/model";
import { theme, toneColor } from "../src/theme";
import { distRoot, isMainModule, repositoryRoot } from "./runtime";
import { validatePresentationContent } from "./validate-content";

export const pptxFileName = "traigent-first-run-scenarios.pptx";
export const defaultPptxPath = path.join(distRoot, pptxFileName);

const SLIDE_WIDTH = 13.333;
const SLIDE_HEIGHT = 7.5;
const CONTENT_X = 0.82;
const CONTENT_WIDTH = SLIDE_WIDTH - CONTENT_X * 2;
const CONTENT_TOP = 0.62;
const BODY_TOP = 2.38;
const DETAIL_TOP = 3.3;
const FOOTER_TOP = 6.94;
const MASTER_NAME = "TRAIGENT_ACCESSIBLE";
const TITLE_PLACEHOLDER_NAME = "slide-title";
const EARLIEST_ZIP_EPOCH_SECONDS = 315_532_800;

const EVIDENCE_COLORS = {
  "guide-contract": theme.colors.violet,
  "scenario-contract": theme.colors.blueBright,
  "verified-run": theme.colors.green,
  "not-demonstrated": theme.colors.amber,
} as const;

export class PptxBuildError extends Error {
  constructor(message: string, options?: ErrorOptions) {
    super(message, options);
    this.name = "PptxBuildError";
  }
}

function addBackground(pptx: PptxGenJS, slide: PptxGenJS.Slide): void {
  slide.background = { color: theme.colors.canvas };
  slide.addShape(pptx.ShapeType.rect, {
    x: 0,
    y: 0,
    w: SLIDE_WIDTH,
    h: SLIDE_HEIGHT,
    line: { color: theme.colors.canvas, transparency: 100 },
    fill: { color: theme.colors.surface, transparency: 2 },
  });
  slide.addShape(pptx.ShapeType.ellipse, {
    x: 9.15,
    y: -2.8,
    w: 6.2,
    h: 6.2,
    line: { color: theme.colors.blue, transparency: 100 },
    fill: { color: theme.colors.blue, transparency: 82 },
  });
  slide.addShape(pptx.ShapeType.line, {
    x: CONTENT_X,
    y: 0.42,
    w: CONTENT_WIDTH,
    h: 0,
    line: { color: theme.colors.border, transparency: 25, width: 0.8 },
  });
}

// The traigent.ai mark, re-drawn from native vector shapes because this build
// intentionally ships no raster media (its image parser is disabled as a
// supply-chain mitigation). Geometry is measured from the 155x125 header icon
// and expressed in icon pixels, scaled uniformly to the placed height.
const BRAND_MARK = {
  sourceWidth: 155,
  sourceHeight: 125,
  bars: [
    { x: 20, y: 14, w: 90, h: 24 },
    { x: 12, y: 54, w: 95, h: 24 },
    { x: 28, y: 94, w: 88, h: 24 },
  ],
  chevronArms: [
    { cx: 116, cy: 37, length: 75, thickness: 24, rotate: 42 },
    { cx: 116, cy: 88, length: 75, thickness: 24, rotate: -42 },
  ],
} as const;

function addBrand(pptx: PptxGenJS, slide: PptxGenJS.Slide): void {
  const markHeight = 0.26;
  const markTop = 0.09;
  const scale = markHeight / BRAND_MARK.sourceHeight;

  for (const bar of BRAND_MARK.bars) {
    slide.addShape(pptx.ShapeType.roundRect, {
      x: CONTENT_X + bar.x * scale,
      y: markTop + bar.y * scale,
      w: bar.w * scale,
      h: bar.h * scale,
      rectRadius: (bar.h * scale) / 2,
      line: { color: brandBlue, transparency: 100 },
      fill: { color: brandBlue },
    });
  }
  for (const arm of BRAND_MARK.chevronArms) {
    slide.addShape(pptx.ShapeType.roundRect, {
      x: CONTENT_X + (arm.cx - arm.length / 2) * scale,
      y: markTop + (arm.cy - arm.thickness / 2) * scale,
      w: arm.length * scale,
      h: arm.thickness * scale,
      rectRadius: (arm.thickness * scale) / 2,
      rotate: arm.rotate,
      line: { color: brandBlue, transparency: 100 },
      fill: { color: brandBlue },
    });
  }
  slide.addText(brandName, {
    x: CONTENT_X + BRAND_MARK.sourceWidth * scale + 0.12,
    y: markTop - 0.02,
    w: 2.2,
    h: markHeight + 0.04,
    margin: 0,
    color: theme.colors.text,
    fontFace: theme.fonts.sans,
    fontSize: 11,
    bold: true,
    charSpacing: 0.2,
    valign: "middle",
    breakLine: false,
  });
}

function addHeading(slide: PptxGenJS.Slide, slideSpec: SlideSpec): void {
  const titleFontSize = slideSpec.kind === "hero" ? 34 : 28;
  const eyebrow = displayEyebrow(slideSpec);

  slide.addText(eyebrow, {
    x: CONTENT_X,
    y: CONTENT_TOP,
    w: CONTENT_WIDTH,
    h: 0.3,
    margin: 0,
    color: theme.colors.blueBright,
    fontFace: theme.fonts.sans,
    fontSize: 10,
    bold: true,
    charSpacing: 2.1,
    breakLine: false,
  });
  slide.addText(slideSpec.title, {
    placeholder: TITLE_PLACEHOLDER_NAME,
    x: CONTENT_X,
    y: 1.02,
    w: 11.15,
    h: 1.18,
    margin: 0,
    color: theme.colors.text,
    fontFace: theme.fonts.sans,
    fontSize: titleFontSize,
    bold: true,
    align: "left",
    breakLine: false,
    valign: "middle",
  });
  slide.addText(slideSpec.body, {
    x: CONTENT_X,
    y: BODY_TOP,
    w: 11.15,
    h: 0.7,
    margin: 0,
    color: theme.colors.textSoft,
    fontFace: theme.fonts.sans,
    fontSize: 14.5,
    breakLine: false,
    valign: "top",
  });
}

function addQuote(
  pptx: PptxGenJS,
  slide: PptxGenJS.Slide,
  quote: string,
): void {
  slide.addShape(pptx.ShapeType.roundRect, {
    x: CONTENT_X,
    y: DETAIL_TOP,
    w: 11.7,
    h: 1.74,
    rectRadius: 0.08,
    line: { color: theme.colors.blueBright, transparency: 50, width: 1.2 },
    fill: { color: theme.colors.surfaceRaised, transparency: 4 },
  });
  slide.addText("PASTE INTO YOUR CODING AGENT", {
    x: CONTENT_X + 0.28,
    y: DETAIL_TOP + 0.22,
    w: 11.1,
    h: 0.22,
    margin: 0,
    color: theme.colors.blueBright,
    fontFace: theme.fonts.sans,
    fontSize: 7.5,
    bold: true,
    charSpacing: 1.4,
  });
  slide.addText(quote, {
    x: CONTENT_X + 0.28,
    y: DETAIL_TOP + 0.63,
    w: 11.1,
    h: 0.86,
    margin: 0,
    color: theme.colors.text,
    fontFace: theme.fonts.mono,
    fontSize: 11.5,
    breakLine: false,
    valign: "middle",
  });
}

function addBullets(
  pptx: PptxGenJS,
  slide: PptxGenJS.Slide,
  bullets: string[],
): void {
  const columns = bullets.length === 1 ? 1 : 2;
  const cardWidth = columns === 1 ? 11.7 : 5.7;
  const rowHeight = 0.78;

  bullets.forEach((bullet, index) => {
    const column = index % columns;
    const row = Math.floor(index / columns);
    const x = CONTENT_X + column * 6;
    const y = DETAIL_TOP + row * 0.92;

    slide.addShape(pptx.ShapeType.roundRect, {
      x,
      y,
      w: cardWidth,
      h: rowHeight,
      rectRadius: 0.04,
      line: { color: theme.colors.border, width: 0.8 },
      fill: { color: theme.colors.surfaceRaised, transparency: 8 },
    });
    slide.addShape(pptx.ShapeType.line, {
      x: x + 0.22,
      y: y + 0.34,
      w: 0.24,
      h: 0,
      line: { color: theme.colors.blueBright, width: 2.2 },
    });
    slide.addText(bullet, {
      x: x + 0.58,
      y: y + 0.08,
      w: cardWidth - 0.78,
      h: rowHeight - 0.14,
      margin: 0,
      color: theme.colors.textSoft,
      fontFace: theme.fonts.sans,
      fontSize: 12.5,
      valign: "middle",
    });
  });
}

function addMetrics(
  pptx: PptxGenJS,
  slide: PptxGenJS.Slide,
  slideSpec: SlideSpec,
): void {
  const gap = 0.22;
  const count = slideSpec.metrics.length;
  const cardWidth = (CONTENT_WIDTH - gap * (count - 1)) / count;

  slideSpec.metrics.forEach((metric, index) => {
    const x = CONTENT_X + index * (cardWidth + gap);
    const color = toneColor(metric.tone);
    slide.addShape(pptx.ShapeType.roundRect, {
      x,
      y: DETAIL_TOP,
      w: cardWidth,
      h: 1.75,
      rectRadius: 0.05,
      line: { color: theme.colors.border, width: 0.8 },
      fill: { color: theme.colors.surfaceRaised, transparency: 4 },
    });
    slide.addShape(pptx.ShapeType.line, {
      x: x + 0.03,
      y: DETAIL_TOP + 0.03,
      w: cardWidth - 0.06,
      h: 0,
      line: { color, width: 2.4 },
    });
    slide.addText(metric.label.toLocaleUpperCase("en"), {
      x: x + 0.2,
      y: DETAIL_TOP + 0.25,
      w: cardWidth - 0.4,
      h: 0.25,
      margin: 0,
      color: theme.colors.muted,
      fontFace: theme.fonts.sans,
      fontSize: 9,
      bold: true,
      charSpacing: 1,
    });
    slide.addText(metric.value, {
      x: x + 0.2,
      y: DETAIL_TOP + 0.59,
      w: cardWidth - 0.4,
      h: 0.55,
      margin: 0,
      color: theme.colors.text,
      fontFace: theme.fonts.mono,
      fontSize: 24,
      bold: true,
      valign: "middle",
    });
    slide.addText(metric.detail, {
      x: x + 0.2,
      y: DETAIL_TOP + 1.25,
      w: cardWidth - 0.4,
      h: 0.3,
      margin: 0,
      color: theme.colors.textSoft,
      fontFace: theme.fonts.sans,
      fontSize: 10,
      valign: "middle",
    });
  });
}

function addJourney(
  pptx: PptxGenJS,
  slide: PptxGenJS.Slide,
  slideSpec: SlideSpec,
): void {
  const columns = slideSpec.steps.length > 4 ? 3 : slideSpec.steps.length;
  const rows = Math.ceil(slideSpec.steps.length / columns);
  const gap = 0.2;
  const cardWidth = (CONTENT_WIDTH - gap * (columns - 1)) / columns;
  const cardHeight = rows === 1 ? 1.85 : 1.55;

  slideSpec.steps.forEach((step, index) => {
    const column = index % columns;
    const row = Math.floor(index / columns);
    const x = CONTENT_X + column * (cardWidth + gap);
    const y = DETAIL_TOP + row * (cardHeight + 0.18);
    const executorColor =
      step.executor === "Human operator"
        ? theme.colors.amber
        : step.executor === "Verifier"
          ? theme.colors.violet
          : step.executor === "Traigent service"
            ? theme.colors.green
            : theme.colors.blueBright;

    slide.addShape(pptx.ShapeType.roundRect, {
      x,
      y,
      w: cardWidth,
      h: cardHeight,
      rectRadius: 0.05,
      line: { color: theme.colors.border, width: 0.8 },
      fill: { color: theme.colors.surfaceRaised, transparency: 4 },
    });
    slide.addText(String(index + 1).padStart(2, "0"), {
      x: x + 0.2,
      y: y + 0.17,
      w: 0.45,
      h: 0.25,
      margin: 0,
      color: theme.colors.muted,
      fontFace: theme.fonts.mono,
      fontSize: 9,
      bold: true,
    });
    const roleRuns: PptxGenJS.TextProps[] = [
      {
        text: `${step.executor.toLocaleUpperCase("en")} EXECUTES`,
        options: { color: executorColor, bold: true },
      },
    ];
    if (step.humanGate !== undefined) {
      roleRuns.push({
        text: `  ·  ${step.humanGate.toLocaleUpperCase("en")}`,
        options: { color: theme.colors.amber, bold: true },
      });
    }
    slide.addText(roleRuns, {
      x: x + 0.72,
      y: y + 0.17,
      w: cardWidth - 0.92,
      h: 0.25,
      margin: 0,
      fontFace: theme.fonts.sans,
      fontSize: 9,
      charSpacing: 0.8,
    });
    slide.addText(step.label, {
      x: x + 0.2,
      y: y + 0.52,
      w: cardWidth - 0.4,
      h: 0.35,
      margin: 0,
      color: theme.colors.text,
      fontFace: theme.fonts.sans,
      fontSize: 14,
      bold: true,
    });
    slide.addText(step.detail, {
      x: x + 0.2,
      y: y + 0.91,
      w: cardWidth - 0.4,
      h: cardHeight - 1.01,
      margin: 0,
      color: theme.colors.textSoft,
      fontFace: theme.fonts.sans,
      fontSize: 10.5,
      valign: "top",
    });
  });
}

function addTableCell(
  pptx: PptxGenJS,
  slide: PptxGenJS.Slide,
  text: string,
  x: number,
  y: number,
  width: number,
  height: number,
  header = false,
  accent = false,
): void {
  slide.addShape(pptx.ShapeType.rect, {
    x,
    y,
    w: width,
    h: height,
    line: { color: theme.colors.border, width: 0.55 },
    fill: {
      color: header ? theme.colors.canvas : theme.colors.surfaceRaised,
      transparency: header ? 2 : 6,
    },
  });
  slide.addText(text, {
    x: x + 0.1,
    y: y + 0.07,
    w: width - 0.2,
    h: height - 0.12,
    margin: 0,
    color: accent
      ? theme.colors.blueBright
      : header
        ? theme.colors.muted
        : theme.colors.textSoft,
    fontFace: theme.fonts.sans,
    fontSize: header ? 8.5 : 10.3,
    bold: header || accent,
    charSpacing: header ? 0.45 : 0,
    valign: "middle",
    breakLine: false,
  });
}

function addStartingPointMatrix(
  pptx: PptxGenJS,
  slide: PptxGenJS.Slide,
  slideSpec: SlideSpec,
): void {
  if (slideSpec.matrix === undefined) return;
  const widths = [3.45, 5.05, 3.2];
  const headers = [
    "STARTING CONDITION",
    "SAFEST JUSTIFIED NEXT STEP",
    "COVERAGE TODAY",
  ];
  let x = CONTENT_X;
  headers.forEach((header, index) => {
    addTableCell(
      pptx,
      slide,
      header,
      x,
      DETAIL_TOP,
      widths[index]!,
      0.43,
      true,
    );
    x += widths[index]!;
  });
  slideSpec.matrix.forEach((row, rowIndex) => {
    const y = DETAIL_TOP + 0.43 + rowIndex * 0.55;
    const values = [
      row.startingPoint,
      row.safestNextStep,
      coverageLabel(row.coverage),
    ];
    let cellX = CONTENT_X;
    values.forEach((value, columnIndex) => {
      addTableCell(
        pptx,
        slide,
        value,
        cellX,
        y,
        widths[columnIndex]!,
        0.55,
        false,
        columnIndex === 2 && row.coverage === "published",
      );
      cellX += widths[columnIndex]!;
    });
  });
}

function addTestLayerMatrix(
  pptx: PptxGenJS,
  slide: PptxGenJS.Slide,
  slideSpec: SlideSpec,
): void {
  if (slideSpec.testMatrix === undefined) return;
  const widths = [1.45, 3.3, 3.65, 3.3];
  const headers = ["LAYER", "ACTION", "A PASS SUPPORTS", "DOES NOT PROVE"];
  let x = CONTENT_X;
  headers.forEach((header, index) => {
    addTableCell(
      pptx,
      slide,
      header,
      x,
      DETAIL_TOP,
      widths[index]!,
      0.43,
      true,
    );
    x += widths[index]!;
  });
  slideSpec.testMatrix.forEach((row, rowIndex) => {
    const y = DETAIL_TOP + 0.43 + rowIndex * 0.67;
    const values = [row.layer, row.action, row.passSupports, row.doesNotProve];
    let cellX = CONTENT_X;
    values.forEach((value, columnIndex) => {
      addTableCell(
        pptx,
        slide,
        value,
        cellX,
        y,
        widths[columnIndex]!,
        0.67,
        false,
        columnIndex === 0,
      );
      cellX += widths[columnIndex]!;
    });
  });
}

function addScenarioCoverageMatrix(
  pptx: PptxGenJS,
  slide: PptxGenJS.Slide,
  slideSpec: SlideSpec,
): void {
  if (slideSpec.scenarioMatrix === undefined) return;
  const widths = [1.7, 3.4, 4.3, 2.29];
  const headers = [
    "SCENARIO FAMILY",
    "MATERIAL AND DATASET ARCHETYPE",
    "BEHAVIOR THE SCENARIO SHOULD EXERCISE",
    "TEST SCENARIO STATUS",
  ];
  let x = CONTENT_X;
  headers.forEach((header, index) => {
    addTableCell(
      pptx,
      slide,
      header,
      x,
      DETAIL_TOP,
      widths[index]!,
      0.43,
      true,
    );
    x += widths[index]!;
  });
  slideSpec.scenarioMatrix.forEach((row, rowIndex) => {
    const y = DETAIL_TOP + 0.43 + rowIndex * 0.62;
    const values = [
      row.family,
      row.setup,
      row.expectedRoute,
      coverageLabel(row.coverage),
    ];
    let cellX = CONTENT_X;
    values.forEach((value, columnIndex) => {
      addTableCell(
        pptx,
        slide,
        value,
        cellX,
        y,
        widths[columnIndex]!,
        0.55,
        false,
        columnIndex === 3 && row.coverage === "published",
      );
      cellX += widths[columnIndex]!;
    });
  });
}

function addCatalogCard(
  pptx: PptxGenJS,
  slide: PptxGenJS.Slide,
  label: string,
  value: string,
  x: number,
  y: number,
  width: number,
  height: number,
): void {
  slide.addShape(pptx.ShapeType.roundRect, {
    x,
    y,
    w: width,
    h: height,
    rectRadius: 0.04,
    line: { color: theme.colors.border, width: 0.7 },
    fill: { color: theme.colors.surfaceRaised, transparency: 5 },
  });
  slide.addText(label.toLocaleUpperCase("en"), {
    x: x + 0.14,
    y: y + 0.1,
    w: width - 0.28,
    h: 0.18,
    margin: 0,
    color: theme.colors.blueBright,
    fontFace: theme.fonts.sans,
    fontSize: 7.5,
    bold: true,
    charSpacing: 0.55,
  });
  slide.addText(value, {
    x: x + 0.14,
    y: y + 0.33,
    w: width - 0.28,
    h: height - 0.42,
    margin: 0,
    color: theme.colors.textSoft,
    fontFace: theme.fonts.sans,
    fontSize: 10,
    valign: "top",
    breakLine: false,
  });
}

function addCatalog(
  pptx: PptxGenJS,
  slide: PptxGenJS.Slide,
  entry: CatalogEntry,
  view: "setup-and-route" | "data-and-limits",
): void {
  const gap = 0.2;
  const halfWidth = (CONTENT_WIDTH - gap) / 2;
  const rightX = CONTENT_X + halfWidth + gap;
  if (view === "setup-and-route") {
    addCatalogCard(
      pptx,
      slide,
      "Starting state",
      entry.startingState,
      CONTENT_X,
      DETAIL_TOP,
      halfWidth,
      1.34,
    );
    addCatalogCard(
      pptx,
      slide,
      "Present components",
      entry.components.join("\n"),
      rightX,
      DETAIL_TOP,
      halfWidth,
      1.34,
    );
    addCatalogCard(
      pptx,
      slide,
      "Expected route",
      entry.expectedRouting,
      CONTENT_X,
      DETAIL_TOP + 1.52,
      halfWidth,
      1.34,
    );
    addCatalogCard(
      pptx,
      slide,
      "Tested layer",
      entry.testedLayer,
      rightX,
      DETAIL_TOP + 1.52,
      halfWidth,
      1.34,
    );
    return;
  }
  addCatalogCard(
    pptx,
    slide,
    "Dataset",
    entry.dataset,
    CONTENT_X,
    DETAIL_TOP,
    CONTENT_WIDTH,
    1.3,
  );
  addCatalogCard(
    pptx,
    slide,
    "Evaluator",
    entry.evaluator,
    CONTENT_X,
    DETAIL_TOP + 1.48,
    halfWidth,
    1.38,
  );
  addCatalogCard(
    pptx,
    slide,
    "Not proven",
    entry.notProven.join("\n"),
    rightX,
    DETAIL_TOP + 1.48,
    halfWidth,
    1.38,
  );
}

function addFooter(
  pptx: PptxGenJS,
  slide: PptxGenJS.Slide,
  slideSpec: SlideSpec,
  slideNumber: number,
  slideCount: number,
): void {
  const badgeColor = EVIDENCE_COLORS[slideSpec.evidenceState];
  slide.addShape(pptx.ShapeType.roundRect, {
    x: CONTENT_X,
    y: FOOTER_TOP,
    w: 3.15,
    h: 0.3,
    rectRadius: 0.03,
    line: { color: badgeColor, transparency: 55, width: 0.7 },
    fill: { color: badgeColor, transparency: 86 },
  });
  slide.addText(evidenceLabel(slideSpec.evidenceState), {
    x: CONTENT_X + 0.08,
    y: FOOTER_TOP + 0.03,
    w: 2.99,
    h: 0.24,
    margin: 0,
    color: badgeColor,
    fontFace: theme.fonts.sans,
    fontSize: 9,
    bold: true,
    align: "center",
    valign: "middle",
  });
  slide.addText(slideSpec.evidence.join(" | "), {
    x: CONTENT_X + 3.35,
    y: FOOTER_TOP,
    w: 7.38,
    h: 0.3,
    margin: 0,
    color: theme.colors.muted,
    fontFace: theme.fonts.sans,
    fontSize: 9,
    valign: "middle",
  });
  slide.addText(
    `${slideSpec.section === "appendix" ? "APPENDIX" : "CORE"} · ${slideNumber} / ${slideCount}`,
    {
      x: 11.3,
      y: FOOTER_TOP,
      w: 1.8,
      h: 0.3,
      margin: 0,
      color: theme.colors.muted,
      fontFace: theme.fonts.mono,
      fontSize: 9,
      align: "right",
      valign: "middle",
    },
  );
}

function addSlideContent(
  pptx: PptxGenJS,
  slide: PptxGenJS.Slide,
  slideSpec: SlideSpec,
  catalog: CatalogEntry[],
): void {
  if (slideSpec.kind === "catalog") {
    const entry = catalog.find(
      (candidate) => candidate.slug === slideSpec.catalogSlug,
    );
    if (entry === undefined || slideSpec.catalogView === undefined) {
      throw new PptxBuildError(
        `Catalog slide ${slideSpec.id} has no matching entry`,
      );
    }
    addCatalog(pptx, slide, entry, slideSpec.catalogView);
    return;
  }
  if (slideSpec.matrix !== undefined) {
    addStartingPointMatrix(pptx, slide, slideSpec);
    return;
  }
  if (slideSpec.testMatrix !== undefined) {
    addTestLayerMatrix(pptx, slide, slideSpec);
    return;
  }
  if (slideSpec.scenarioMatrix !== undefined) {
    addScenarioCoverageMatrix(pptx, slide, slideSpec);
    return;
  }
  if (slideSpec.quote !== undefined) {
    addQuote(pptx, slide, slideSpec.quote);
    return;
  }
  if (slideSpec.metrics.length > 0) {
    addMetrics(pptx, slide, slideSpec);
    return;
  }
  if (slideSpec.steps.length > 0) {
    addJourney(pptx, slide, slideSpec);
    return;
  }
  if (slideSpec.bullets.length > 0) {
    addBullets(pptx, slide, slideSpec.bullets);
  }
}

export function createPptx(value: PresentationSpec = presentation): PptxGenJS {
  const validated = validatePresentationContent(value);
  const pptx = new PptxGenJS();
  pptx.defineLayout({
    name: "TRAIGENT_WIDE",
    width: SLIDE_WIDTH,
    height: SLIDE_HEIGHT,
  });
  pptx.layout = "TRAIGENT_WIDE";
  pptx.author = "Traigent Ltd";
  pptx.company = "Traigent Ltd";
  pptx.subject = validated.subtitle;
  pptx.title = validated.title;
  pptx.revision = "1";
  pptx.theme = {
    headFontFace: theme.fonts.sans,
    bodyFontFace: theme.fonts.sans,
  };
  pptx.defineSlideMaster({
    title: MASTER_NAME,
    background: { color: theme.colors.canvas },
    objects: [
      {
        placeholder: {
          options: {
            name: TITLE_PLACEHOLDER_NAME,
            type: "title",
            x: CONTENT_X,
            y: 1.02,
            w: 11.15,
            h: 1.18,
            margin: 0,
          },
          text: "",
        },
      },
    ],
  });

  validated.slides.forEach((slideSpec, index) => {
    const slide = pptx.addSlide({ masterName: MASTER_NAME });
    addBackground(pptx, slide);
    addBrand(pptx, slide);
    addHeading(slide, slideSpec);
    addSlideContent(pptx, slide, slideSpec, validated.catalog);
    addFooter(pptx, slide, slideSpec, index + 1, validated.slides.length);
    slide.addNotes(slideSpec.notes.join("\n\n"));
  });

  return pptx;
}

function parsePptxEpochSeconds(value: string, label: string): number {
  if (!/^\d+$/.test(value)) {
    throw new PptxBuildError(`${label} must be a non-negative integer`);
  }
  const parsed = Number(value);
  if (!Number.isSafeInteger(parsed)) {
    throw new PptxBuildError(`${label} is outside the safe integer range`);
  }
  if (parsed < EARLIEST_ZIP_EPOCH_SECONDS) {
    throw new PptxBuildError(
      `${label} must be on or after 1980-01-01 for ZIP output`,
    );
  }
  const timestamp = new Date(parsed * 1000);
  if (Number.isNaN(timestamp.valueOf())) {
    throw new PptxBuildError(`${label} is outside the supported date range`);
  }
  return parsed;
}

export function resolvePptxEpochSeconds(
  sourceDateEpoch = process.env.SOURCE_DATE_EPOCH,
): number {
  if (sourceDateEpoch !== undefined) {
    return parsePptxEpochSeconds(sourceDateEpoch, "SOURCE_DATE_EPOCH");
  }
  try {
    const commitEpoch = execFileSync(
      "git",
      ["show", "-s", "--format=%ct", "HEAD"],
      {
        cwd: repositoryRoot,
        encoding: "utf8",
        stdio: ["ignore", "pipe", "pipe"],
      },
    ).trim();
    return parsePptxEpochSeconds(commitEpoch, "Git commit timestamp");
  } catch (error: unknown) {
    if (error instanceof PptxBuildError) {
      throw error;
    }
    throw new PptxBuildError(
      "Unable to resolve a reproducible PowerPoint timestamp; use a Git checkout or set SOURCE_DATE_EPOCH",
      { cause: error },
    );
  }
}

function replaceCoreTimestamp(
  coreProperties: string,
  field: "created" | "modified",
  timestamp: string,
): string {
  const pattern = new RegExp(
    `(<dcterms:${field}\\b[^>]*>)[^<]*(</dcterms:${field}>)`,
  );
  if (!pattern.test(coreProperties)) {
    throw new PptxBuildError(`PowerPoint core properties are missing ${field}`);
  }
  return coreProperties.replace(pattern, `$1${timestamp}$2`);
}

async function normalizePptxArchive(
  bytes: Uint8Array,
  epochSeconds: number,
): Promise<Buffer> {
  const timestamp = new Date(epochSeconds * 1000);
  const archive = await JSZip.loadAsync(bytes);
  const coreFile = archive.file("docProps/core.xml");
  if (coreFile === null) {
    throw new PptxBuildError("PowerPoint archive is missing docProps/core.xml");
  }
  const isoTimestamp = timestamp.toISOString().replace(".000Z", "Z");
  const coreProperties = replaceCoreTimestamp(
    replaceCoreTimestamp(
      await coreFile.async("string"),
      "created",
      isoTimestamp,
    ),
    "modified",
    isoTimestamp,
  );

  archive.forEach((_relativePath, entry) => {
    entry.date = timestamp;
  });
  archive.file("docProps/core.xml", coreProperties, { date: timestamp });

  return archive.generateAsync({
    type: "nodebuffer",
    compression: "DEFLATE",
    compressionOptions: { level: 9 },
    platform: "UNIX",
  });
}

export async function renderPptxBuffer(
  value: PresentationSpec = presentation,
  sourceEpochSeconds = resolvePptxEpochSeconds(),
): Promise<Buffer> {
  const validatedEpochSeconds = parsePptxEpochSeconds(
    String(sourceEpochSeconds),
    "PowerPoint source epoch",
  );
  const output = await createPptx(value).write({
    outputType: "nodebuffer",
    compression: true,
  });
  if (!(output instanceof Uint8Array)) {
    throw new PptxBuildError("PptxGenJS returned a non-binary Node output");
  }
  return normalizePptxArchive(output, validatedEpochSeconds);
}

export async function buildPptx(
  outputPath = defaultPptxPath,
  sourceEpochSeconds = resolvePptxEpochSeconds(),
): Promise<string> {
  try {
    const bytes = await renderPptxBuffer(presentation, sourceEpochSeconds);
    await mkdir(path.dirname(outputPath), { recursive: true });
    await writeFile(outputPath, bytes);
    return outputPath;
  } catch (error: unknown) {
    if (error instanceof PptxBuildError) {
      throw error;
    }
    throw new PptxBuildError(`Unable to build PowerPoint at ${outputPath}`, {
      cause: error,
    });
  }
}

if (isMainModule(import.meta.url)) {
  const outputPath = await buildPptx();
  process.stdout.write(`Built editable PowerPoint: ${outputPath}\n`);
}
