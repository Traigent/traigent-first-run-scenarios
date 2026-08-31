import { ZodError } from "zod";

import { presentation } from "../src/content";
import {
  parsePresentation,
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

function visibleClaimText(slide: SlideSpec): string {
  return [
    slide.eyebrow,
    slide.title,
    slide.body,
    slide.quote ?? "",
    ...slide.bullets,
    ...slide.metrics.flatMap((metric) => [
      metric.label,
      metric.value,
      metric.detail,
    ]),
    ...slide.steps.flatMap((step) => [
      step.label,
      step.detail,
      step.executor,
      step.humanGate ?? "",
    ]),
    ...(slide.matrix ?? []).flatMap((row) => [
      row.startingPoint,
      row.safestNextStep,
    ]),
    ...(slide.testMatrix ?? []).flatMap((row) => [
      row.layer,
      row.action,
      row.passSupports,
      row.doesNotProve,
    ]),
    ...(slide.scenarioMatrix ?? []).flatMap((row) => [
      row.family,
      row.setup,
      row.expectedRoute,
    ]),
  ].join("\n");
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

function validateEvidenceContract(slide: SlideSpec): string[] {
  const issues: string[] = [];
  const claimText = visibleClaimText(slide);
  const hasPositiveRunClaim = POSITIVE_RUN_CLAIMS.some((pattern) =>
    pattern.test(claimText),
  );

  if (hasPositiveRunClaim && slide.evidenceState !== "verified-run") {
    issues.push("positive run claims require evidenceState verified-run");
  }
  if (slide.evidenceState === "verified-run") {
    issues.push(
      "verified-run slides are disabled until retained evidence validates revisions, semantic verification, exit status, handoff, environment, and stop point",
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

function validateSlide(slide: SlideSpec): string[] {
  const issues = [
    ...validateTemplateContract(slide),
    ...validateEvidenceContract(slide),
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

  const issues = parsed.slides.flatMap((slide) => validateSlide(slide));
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
