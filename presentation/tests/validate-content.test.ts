import { readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { coreSlideCount, presentation } from "../src/content";
import { evidenceLabel, type PresentationSpec } from "../src/model";
import { repositoryRoot } from "../scripts/runtime";
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
  it("accepts the canonical contract-only deck and public catalog", () => {
    const validated = validatePresentationContent(presentation);

    expect(validated.slides).toHaveLength(28);
    expect(coreSlideCount).toBe(10);
    expect(
      validated.slides
        .slice(0, coreSlideCount)
        .every((slide) => slide.section === "core"),
    ).toBe(true);
    expect(
      validated.slides
        .slice(coreSlideCount)
        .every((slide) => slide.section === "appendix"),
    ).toBe(true);
    expect(validated.catalog).toHaveLength(1);
    expect(validated.slides.every((slide) => slide.notes.length > 0)).toBe(
      true,
    );
    expect(validated.slides.every((slide) => slide.evidence.length > 0)).toBe(
      true,
    );
  });

  it("places scoring and ceiling detail inside the Readiness appendix sequence", () => {
    const ids = presentation.slides.map((slide) => slide.id);
    const readinessIndex = ids.indexOf("stage-readiness");
    const scoringIndex = ids.indexOf("readiness-scoring");
    const foundationCapsIndex = ids.indexOf("readiness-ceilings-foundations");
    const evidenceCapsIndex = ids.indexOf("readiness-ceilings-evidence");
    const expectedOpeningIndex = ids.indexOf("expected-opening");

    expect([
      readinessIndex,
      scoringIndex,
      foundationCapsIndex,
      evidenceCapsIndex,
      expectedOpeningIndex,
    ]).toEqual([
      readinessIndex,
      readinessIndex + 1,
      readinessIndex + 2,
      readinessIndex + 3,
      readinessIndex + 4,
    ]);
    expect(readinessIndex).toBeGreaterThanOrEqual(coreSlideCount);

    const scoring = presentation.slides[scoringIndex]!;
    expect(scoring.bullets.join("\n")).toContain("Dataset - 40 points");
    expect(scoring.bullets.join("\n")).toContain("Evaluation - 35 points");
    expect(scoring.bullets.join("\n")).toContain("Agent - 25 points");
    expect(scoring.bullets.join("\n")).toContain("below 0.75");
    expect(scoring.bullets.join("\n")).toContain("lower bands are unchanged");

    const capRows = [foundationCapsIndex, evidenceCapsIndex].flatMap(
      (index) => presentation.slides[index]?.matrix ?? [],
    );
    const capText = capRows.map((row) => row.safestNextStep).join("\n");
    expect(capText).toContain("Ceiling 25");
    expect(capText).toContain("Ceiling 45");
    expect(capText).toContain("Ceiling 65");
    expect(capText).toContain("Ceiling 74");
  });

  it("keeps coverage targets distinct from the one published scenario", () => {
    const matrix = presentation.slides
      .filter((slide) => slide.id.startsWith("coverage-roadmap-"))
      .flatMap((slide) => slide.scenarioMatrix ?? []);

    expect(matrix).toHaveLength(7);
    expect(matrix.filter((row) => row.coverage === "published")).toHaveLength(
      1,
    );
    expect(
      matrix.filter((row) => row.coverage === "coverage-target"),
    ).toHaveLength(6);
    expect(presentation.catalog[0]?.slug).toBe("incident-severity-triage");
  });

  it("pins every published-guide claim to the full reviewed revision", () => {
    const guideSlides = presentation.slides.filter(
      (slide) => slide.evidenceState === "guide-contract",
    );

    expect(guideSlides.length).toBeGreaterThan(0);
    expect(
      guideSlides.every(
        (slide) =>
          slide.sourceRevision === "6ec2b9c161400cd91faea9c8cdb1c4e00d21c8d9",
      ),
    ).toBe(true);
  });

  it("rejects a guide-contract slide without an exact source revision", () => {
    const candidate = copyPresentation();
    const guideSlide = candidate.slides.find(
      (slide) => slide.evidenceState === "guide-contract",
    )!;
    delete guideSlide.sourceRevision;

    expectValidationIssue(
      candidate,
      "guide-contract slides require an exact source revision",
    );
  });

  it("explains the bounded search and held-out selection without claiming an exhaustive run", () => {
    const searchSpace = presentation.slides.find(
      (slide) => slide.id === "case-46-search-space",
    )!;
    const selection = presentation.slides.find(
      (slide) => slide.id === "selection-and-heldout",
    )!;
    const optimizeStep = selection.steps.find(
      (step) => step.label === "Run managed search",
    )!;

    expect(searchSpace.title).toContain("54 candidate configurations");
    expect(searchSpace.body).toContain(
      "does not establish the final approved search space",
    );
    expect(searchSpace.body).not.toContain("up to 12");
    expect(optimizeStep.detail).toContain("tests up to 12");
    expect(selection.body).toContain("Only that locked recommendation");
    expect(selection.body).toContain("never choose it");
    expect(selection.notes.join("\n")).toContain(
      "not a claim that every paid first run uses all 120 rows",
    );
  });

  it("requires matrix slides to provide exactly one table dataset", () => {
    const candidate = copyPresentation();
    const slide = candidate.slides.find((item) => item.matrix !== undefined)!;
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

  it("fails closed on verified-run slides until retained evidence has a strict schema", () => {
    const candidate = copyPresentation();
    const slide = candidate.slides[0]!;
    slide.evidenceState = "verified-run";
    delete slide.sourceRevision;

    expectValidationIssue(
      candidate,
      "verified-run slides are disabled until retained evidence validates revisions",
    );
  });

  it("keeps the four public evidence labels consistent across documentation", () => {
    const vocabularyDocuments = [
      "GUIDE.md",
      "docs/methodology.md",
      "presentation/README.md",
    ].map((relativePath) =>
      readFileSync(path.join(repositoryRoot, relativePath), "utf8"),
    );
    const labels = [
      evidenceLabel("guide-contract"),
      evidenceLabel("scenario-contract"),
      evidenceLabel("verified-run"),
      evidenceLabel("not-demonstrated"),
    ];
    for (const document of vocabularyDocuments) {
      for (const label of labels) {
        expect(document).toContain(label);
      }
    }
    const legacyLabelDocuments = [
      readFileSync(path.join(repositoryRoot, "README.md"), "utf8"),
      ...vocabularyDocuments,
    ];
    for (const document of legacyLabelDocuments) {
      expect(document).not.toMatch(/Expected\s+scenario\s+contract/);
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
