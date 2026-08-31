import { describe, expect, it } from "vitest";

import { presentation } from "../src/content";
import type { PresentationSpec } from "../src/model";
import {
  ContentValidationError,
  validatePresentationContent,
} from "../scripts/validate-content";

function copyPresentation(): PresentationSpec {
  return structuredClone(presentation);
}

function expectValidationIssue(
  candidate: PresentationSpec,
  expectedMessage: string,
): void {
  expect(() => validatePresentationContent(candidate)).toThrowError(
    ContentValidationError,
  );
  expect(() => validatePresentationContent(candidate)).toThrowError(
    expectedMessage,
  );
}

describe("presentation content validation", () => {
  it("accepts the canonical expected-contract deck and public catalog", () => {
    const validated = validatePresentationContent(presentation);

    expect(validated.slides).toHaveLength(25);
    expect(validated.catalog).toHaveLength(1);
    expect(validated.slides.every((slide) => slide.notes.length > 0)).toBe(
      true,
    );
    expect(validated.slides.every((slide) => slide.evidence.length > 0)).toBe(
      true,
    );
  });

  it("places source-verified scoring and ceiling explanations inside Readiness", () => {
    const ids = presentation.slides.map((slide) => slide.id);
    const readinessIndex = ids.indexOf("stage-readiness");
    const scoringIndex = ids.indexOf("readiness-scoring");
    const ceilingsIndex = ids.indexOf("readiness-ceilings");
    const baselineIndex = ids.indexOf("stage-baseline");

    expect([
      readinessIndex,
      scoringIndex,
      ceilingsIndex,
      baselineIndex,
    ]).toEqual([
      readinessIndex,
      readinessIndex + 1,
      readinessIndex + 2,
      readinessIndex + 3,
    ]);

    const scoring = presentation.slides[scoringIndex]!;
    expect(scoring.bullets.join("\n")).toContain("Dataset - 40 points");
    expect(scoring.bullets.join("\n")).toContain("Evaluation - 35 points");
    expect(scoring.bullets.join("\n")).toContain("Agent - 25 points");
    expect(scoring.bullets.join("\n")).toContain("below 0.75");
    expect(scoring.bullets.join("\n")).toContain("a lower band stays lower");

    const ceilings = presentation.slides[ceilingsIndex]?.matrix;
    expect(ceilings?.map((row) => row.safestNextStep).join("\n")).toContain(
      "Ceiling 25",
    );
    expect(ceilings?.map((row) => row.safestNextStep).join("\n")).toContain(
      "Ceiling 45",
    );
    expect(ceilings?.map((row) => row.safestNextStep).join("\n")).toContain(
      "Ceiling 65",
    );
    expect(ceilings?.map((row) => row.safestNextStep).join("\n")).toContain(
      "Ceiling 74",
    );
  });

  it("keeps coverage targets distinct from the one published scenario", () => {
    const matrix = presentation.slides.find(
      (slide) => slide.id === "different-starting-points",
    )?.scenarioMatrix;

    expect(matrix).toHaveLength(5);
    expect(matrix?.filter((row) => row.coverage === "published")).toHaveLength(
      1,
    );
    expect(
      matrix?.filter((row) => row.coverage === "coverage-target"),
    ).toHaveLength(4);
    expect(presentation.catalog[0]?.slug).toBe("incident-severity-triage");
  });

  it("explains the bounded search and held-out selection without claiming an exhaustive run", () => {
    const searchSpace = presentation.slides.find(
      (slide) => slide.id === "case-46-search-space",
    )!;
    const selection = presentation.slides.find(
      (slide) => slide.id === "selection-and-heldout",
    )!;

    expect(searchSpace.title).toContain("54 candidate configurations");
    expect(searchSpace.body).toContain("tests up to 12");
    expect(searchSpace.body).toContain("approved space with its own count");
    expect(selection.body).toContain("Only that locked recommendation");
    expect(selection.body).toContain("never choose it");
    expect(selection.notes.join("\n")).toContain(
      "not a claim that every paid first run uses all 120 rows",
    );
  });

  it("requires matrix slides to provide exactly one table dataset", () => {
    const candidate = copyPresentation();
    const slide = candidate.slides.find((item) => item.kind === "matrix")!;
    slide.testMatrix = [
      {
        layer: "extra",
        action: "extra",
        passSupports: "extra",
        doesNotProve: "extra",
      },
    ];

    expectValidationIssue(
      candidate,
      "matrix slides require exactly one matrix dataset",
    );
  });

  it("rejects a catalog slide that references an unknown scenario", () => {
    const candidate = copyPresentation();
    const slide = candidate.slides.find((item) => item.kind === "catalog")!;
    slide.catalogSlug = "not-in-the-catalog";

    expectValidationIssue(candidate, "catalog slide references unknown slug");
  });

  it("rejects duplicate identifiers through the canonical schema", () => {
    const candidate = copyPresentation();
    candidate.slides[1]!.id = candidate.slides[0]!.id;

    expectValidationIssue(candidate, "duplicate slide id");
  });

  it("rejects a handoff slide without its customer-visible quote", () => {
    const candidate = copyPresentation();
    const handoff = candidate.slides.find((slide) => slide.kind === "handoff");
    expect(handoff).toBeDefined();
    delete handoff!.quote;

    expectValidationIssue(candidate, "handoff slides require a quote");
  });

  it("rejects an accent that the title cannot render", () => {
    const candidate = copyPresentation();
    candidate.slides[0]!.accent = "not in the title";

    expectValidationIssue(
      candidate,
      "accent is not present in the slide title",
    );
  });

  it("rejects positive run claims without verified-run evidence", () => {
    const candidate = copyPresentation();
    candidate.slides[0]!.body =
      "We achieved a measurable optimization improvement.";

    expectValidationIssue(
      candidate,
      "positive run claims require evidenceState verified-run",
    );
  });

  it("rejects green metric tones on expected-only slides", () => {
    const candidate = copyPresentation();
    const metricsSlide = candidate.slides.find(
      (slide) => slide.metrics.length > 0,
    );
    expect(metricsSlide).toBeDefined();
    metricsSlide!.metrics[0]!.tone = "green";

    expectValidationIssue(
      candidate,
      "green metric tones require evidenceState verified-run",
    );
  });

  it("requires verified-run slides to cite a JSON run artifact", () => {
    const candidate = copyPresentation();
    const slide = candidate.slides[0]!;
    slide.evidenceState = "verified-run";
    slide.evidence = ["A verbal recollection of a prior run"];

    expectValidationIssue(
      candidate,
      "verified-run slides require a JSON run artifact reference",
    );
  });

  it("accepts green metrics only with a readable JSON run artifact", () => {
    const repositoryDirectory = mkdtempSync(
      path.join(tmpdir(), "presentation-evidence-"),
    );
    mkdirSync(path.join(repositoryDirectory, "runs"));
    writeFileSync(
      path.join(repositoryDirectory, "runs", "release-evidence.json"),
      "{}\n",
      "utf8",
    );
    const candidate = copyPresentation();
    const slide = candidate.slides.find((item) => item.metrics.length > 0)!;
    slide.evidenceState = "verified-run";
    slide.evidence = ["runs/release-evidence.json"];
    slide.metrics[0]!.tone = "green";

    try {
      expect(() =>
        validatePresentationContent(candidate, { repositoryDirectory }),
      ).not.toThrow();
    } finally {
      rmSync(repositoryDirectory, { recursive: true, force: true });
    }
  });

  it("rejects a verified-run reference whose JSON artifact is absent", () => {
    const repositoryDirectory = mkdtempSync(
      path.join(tmpdir(), "presentation-evidence-"),
    );
    const candidate = copyPresentation();
    const slide = candidate.slides.find((item) => item.metrics.length > 0)!;
    slide.evidenceState = "verified-run";
    slide.evidence = ["runs/missing.json"];
    slide.metrics[0]!.tone = "green";

    try {
      expect(() =>
        validatePresentationContent(candidate, { repositoryDirectory }),
      ).toThrowError("does not resolve to a readable file");
    } finally {
      rmSync(repositoryDirectory, { recursive: true, force: true });
    }
  });

  it("treats plain-language cost movement as a positive run claim", () => {
    const candidate = copyPresentation();
    candidate.slides[0]!.body = "Cost fell 30% in the latest run.";

    expectValidationIssue(
      candidate,
      "positive run claims require evidenceState verified-run",
    );
  });

  it("rejects metrics that claim a not-demonstrated result", () => {
    const candidate = copyPresentation();
    const slide = candidate.slides.find((item) => item.metrics.length > 0)!;
    slide.evidenceState = "not-demonstrated";

    expectValidationIssue(
      candidate,
      "not-demonstrated slides cannot present metrics",
    );
  });
});
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
