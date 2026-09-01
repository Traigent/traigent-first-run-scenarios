import { ZodError } from "zod";

import { presentation } from "../src/content";
import {
  parsePresentation,
  type CatalogEntry,
  type PresentationSpec,
  type SlideSpec,
} from "../src/model";
import { isMainModule } from "./runtime";

const POSITIVE_RUN_CLAIMS = [
  /\bwe (?:achieved|measured|observed|reduced|improved|increased)\b/i,
  /\b(?:achieved|measured|observed) (?:an? )?(?:live |optimization )?(?:result|improvement|gain|reduction)\b/i,
  /\b(?:quality|latency|cost) (?:improved|decreased|increased|reduced) by\b/i,
  /\b(?:quality|latency|cost) (?:fell|rose|dropped|improved|decreased|increased|reduced)\b/i,
  /\bverified (?:live )?(?:run|result|optimization|improvement)\b/i,
] as const;

// Fields the deck renders beneath "Not proven" and "Does not prove". Naming a
// result there is the opposite of claiming it.
const DISCLAIMED_FIELDS = new Set(["notProven", "doesNotProve"]);

// A claim phrase inside a sentence that denies it is not a claim. Speaker
// notes and evidence lines are where the deck says what it is not asserting,
// so refusing those sentences would push authors away from the plain wording
// the deck exists to use.
const CLAIM_NEGATORS =
  /\b(?:no|not|never|without|cannot|can't|don't|doesn't|didn't|isn't|aren't|wasn't|weren't|none|nothing|neither|nor|un(?:proven|verified)|absent)\b/i;

// Clause boundaries count, not only sentence boundaries. A negator only
// disclaims what it governs, and it stops governing at the comma: "No customer
// data leaves the laptop, and we measured a 41% quality improvement" is a real
// claim wearing a denial's opening. Those are the phrasings a local-only deck
// reaches for, so treating the whole sentence as disclaimed exempted exactly
// the sentences most likely to overclaim.
const CLAUSE_BOUNDARY = /[.!?;,:\n]/;

export class ContentValidationError extends Error {
  readonly issues: readonly string[];

  constructor(issues: readonly string[], options?: ErrorOptions) {
    super(
      `Presentation content validation failed:\n- ${issues.join("\n- ")}`,
      options,
    );
    this.name = "ContentValidationError";
    this.issues = issues;
  }
}

function uniqueIssues(values: readonly string[], label: string): string[] {
  const normalized = new Set<string>();
  const issues: string[] = [];

  for (const value of values) {
    const key = value.trim().toLocaleLowerCase("en");
    if (normalized.has(key)) {
      issues.push(`${label} contains a duplicate value: ${value}`);
    }
    normalized.add(key);
  }

  return issues;
}

/**
 * Collect every string the content model carries, at any depth.
 *
 * The honesty rule has to hold on every surface a reader sees, and the deck
 * renders far more than a slide's body: the footer prints `evidence`, the
 * speaker-note pane and the PowerPoint notes page print `notes`, catalog
 * slides print the catalog entry, and the deck subtitle becomes the
 * PowerPoint subject. Enumerating fields by hand left four of those surfaces
 * unchecked, so the scan walks the parsed model instead. A field added to the
 * schema is covered the day it is added, without editing a list here.
 */
function collectRenderedStrings(value: unknown, collected: string[]): void {
  if (typeof value === "string") {
    collected.push(value);
    return;
  }
  if (Array.isArray(value)) {
    for (const item of value) {
      collectRenderedStrings(item, collected);
    }
    return;
  }
  if (typeof value === "object" && value !== null) {
    for (const [key, item] of Object.entries(value)) {
      // These fields render under a heading that states the deck does not
      // claim what they contain, so a result named there is a disclaimer.
      if (!DISCLAIMED_FIELDS.has(key)) {
        collectRenderedStrings(item, collected);
      }
    }
  }
}

function visibleClaimText(...values: readonly unknown[]): string {
  const collected: string[] = [];
  for (const value of values) {
    collectRenderedStrings(value, collected);
  }
  return collected.join("\n");
}

/** The text preceding a match, back to the start of its own clause. */
function clauseLeadIn(claimText: string, matchStart: number): string {
  const window = claimText.slice(Math.max(0, matchStart - 160), matchStart);
  let boundary = -1;
  for (let index = window.length - 1; index >= 0; index -= 1) {
    if (CLAUSE_BOUNDARY.test(window[index]!)) {
      boundary = index;
      break;
    }
  }
  return window.slice(boundary + 1);
}

function hasPositiveRunClaim(claimText: string): boolean {
  for (const pattern of POSITIVE_RUN_CLAIMS) {
    const scan = new RegExp(pattern.source, `${pattern.flags}g`);
    for (
      let match = scan.exec(claimText);
      match !== null;
      match = scan.exec(claimText)
    ) {
      if (!CLAIM_NEGATORS.test(clauseLeadIn(claimText, match.index))) {
        return true;
      }
    }
  }
  return false;
}

function renderedCatalogEntry(
  slide: SlideSpec,
  catalog: readonly CatalogEntry[],
): CatalogEntry | undefined {
  return slide.catalogSlug === undefined
    ? undefined
    : catalog.find((entry) => entry.slug === slide.catalogSlug);
}

function validateTemplateContract(slide: SlideSpec): string[] {
  const issues: string[] = [];

  if (slide.kind === "handoff" && slide.quote === undefined) {
    issues.push("handoff slides require a quote");
  }
  if (slide.kind !== "handoff" && slide.quote !== undefined) {
    issues.push("only handoff slides may define a quote");
  }
  if (slide.kind === "journey" && slide.steps.length === 0) {
    issues.push("journey slides require at least one step");
  }
  if (slide.kind === "evidence" && slide.metrics.length === 0) {
    issues.push("evidence slides require at least one metric");
  }
  if (
    slide.kind === "matrix" &&
    [slide.matrix, slide.testMatrix, slide.scenarioMatrix].filter(
      (dataset) => dataset !== undefined,
    ).length !== 1
  ) {
    issues.push("matrix slides require exactly one matrix dataset");
  }
  if (
    slide.kind !== "matrix" &&
    (slide.matrix !== undefined ||
      slide.testMatrix !== undefined ||
      slide.scenarioMatrix !== undefined)
  ) {
    issues.push("only matrix slides may define matrix data");
  }
  if (
    slide.kind === "catalog" &&
    (slide.catalogView === undefined || slide.catalogSlug === undefined)
  ) {
    issues.push("catalog slides require a catalog slug and view");
  }
  if (
    slide.kind !== "catalog" &&
    (slide.catalogView !== undefined || slide.catalogSlug !== undefined)
  ) {
    issues.push("only catalog slides may define catalog routing");
  }
  if (slide.accent !== undefined) {
    const title = slide.title.toLocaleLowerCase("en");
    const accent = slide.accent.toLocaleLowerCase("en");
    if (!title.includes(accent)) {
      issues.push(`accent is not present in the slide title: ${slide.accent}`);
    }
  }

  return issues;
}

function validateEvidenceContract(
  slide: SlideSpec,
  catalog: readonly CatalogEntry[],
): string[] {
  const issues: string[] = [];
  const claimText = visibleClaimText(
    slide,
    renderedCatalogEntry(slide, catalog),
  );

  if (
    hasPositiveRunClaim(claimText) &&
    slide.evidenceState !== "verified-run"
  ) {
    issues.push("positive run claims require evidenceState verified-run");
  }
  if (slide.evidenceState === "verified-run") {
    issues.push(
      "verified-run slides are disabled until retained evidence validates revisions, worker and session identity, environment and isolation boundary, exact handoff and response, captured JSON, complete commands and final statuses, verifier output, and stop point",
    );
  }
  if (
    slide.evidenceState !== "verified-run" &&
    slide.metrics.some((metric) => metric.tone === "green")
  ) {
    issues.push("green metric tones require evidenceState verified-run");
  }
  if (slide.evidenceState === "not-demonstrated" && slide.metrics.length > 0) {
    issues.push("not-demonstrated slides cannot present metrics");
  }

  return issues;
}

function validateSlide(
  slide: SlideSpec,
  catalog: readonly CatalogEntry[],
): string[] {
  const issues = [
    ...validateTemplateContract(slide),
    ...validateEvidenceContract(slide, catalog),
    ...uniqueIssues(slide.bullets, "bullets"),
    ...uniqueIssues(slide.evidence, "evidence"),
    ...uniqueIssues(slide.notes, "notes"),
    ...uniqueIssues(
      slide.metrics.map((metric) => metric.label),
      "metric labels",
    ),
    ...uniqueIssues(
      slide.steps.map((step) => step.label),
      "step labels",
    ),
  ];

  return issues.map((issue) => `slide ${slide.id}: ${issue}`);
}

function schemaIssues(error: ZodError): string[] {
  return error.issues.map((issue) => {
    const path =
      issue.path.length === 0 ? "presentation" : issue.path.join(".");
    return `${path}: ${issue.message}`;
  });
}

function validateDeckContract(spec: PresentationSpec): string[] {
  // Deck-level text renders on every slide and in the PowerPoint document
  // properties, and carries no evidence state of its own, so it can never
  // reach the verified-run state a positive run claim would require.
  return hasPositiveRunClaim(
    visibleClaimText(spec.title, spec.subtitle, spec.scenario),
  )
    ? [
        "deck: positive run claims require evidenceState verified-run, which deck-level text cannot carry",
      ]
    : [];
}

export function validatePresentationContent(value: unknown): PresentationSpec {
  let parsed: PresentationSpec;
  try {
    parsed = parsePresentation(value);
  } catch (error: unknown) {
    if (error instanceof ZodError) {
      throw new ContentValidationError(schemaIssues(error), { cause: error });
    }
    throw error;
  }

  const issues = [
    ...validateDeckContract(parsed),
    ...parsed.slides.flatMap((slide) => validateSlide(slide, parsed.catalog)),
  ];
  if (issues.length > 0) {
    throw new ContentValidationError(issues);
  }

  return parsed;
}

export function validateCurrentPresentation(): PresentationSpec {
  return validatePresentationContent(presentation);
}

if (isMainModule(import.meta.url)) {
  const validated = validateCurrentPresentation();
  process.stdout.write(
    `Validated ${validated.slides.length} presentation slides for scenario ${validated.scenario.slug}.\n`,
  );
}
