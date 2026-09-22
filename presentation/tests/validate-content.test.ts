import { readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { coreSlideCount, presentation, scenarioBankSize } from "../src/content";
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

    expect(validated.slides).toHaveLength(26);
    expect(coreSlideCount).toBe(9);
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
    expect(scenarioBankSize).toBe(13);
    expect(validated.catalog).toHaveLength(13);
    expect(validated.catalog.map((entry) => entry.legacyId)).toEqual([
      46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58,
    ]);
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
    const baselineIndex = ids.indexOf("stage-baseline");

    expect([
      readinessIndex,
      scoringIndex,
      foundationCapsIndex,
      evidenceCapsIndex,
      baselineIndex,
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

  it("introduces the five-stage route before the prompt and keeps scores out of the core", () => {
    const coreSlides = presentation.slides.slice(0, coreSlideCount);

    expect(coreSlides.slice(0, 6).map((slide) => slide.id)).toEqual([
      "ready-to-optimize",
      "shared-control",
      "one-customer-prompt",
      "different-starting-points",
      "case-46",
      "test-layers",
    ]);
    expect(coreSlides[coreSlideCount - 1]?.id).toBe("next-step");
    expect(
      coreSlides
        .flatMap((slide) => slide.metrics)
        .map((metric) => metric.label),
    ).not.toContain("Expected opening");
  });

  it("marks every scenario family published and names its cases", () => {
    const matrix = presentation.slides
      .filter((slide) => slide.id.startsWith("scenario-families-"))
      .flatMap((slide) => slide.scenarioMatrix ?? []);

    expect(matrix).toHaveLength(7);
    expect(matrix.every((row) => row.coverage === "published")).toBe(true);
    expect(matrix.map((row) => row.setup.split(":")[0])).toEqual([
      "Cases 46, 47, 48",
      "Cases 55, 57",
      "Cases 51, 58",
      "Cases 54, 56",
      "Cases 49, 53",
      "Case 50",
      "Case 52",
    ]);
    expect(presentation.catalog[0]?.slug).toBe("incident-severity-triage");
    expect(presentation.scenario.slug).toBe("incident-severity-triage");
  });

  it("keeps the two caps no scenario exercises as coverage targets", () => {
    const rows = presentation.slides
      .filter((slide) => slide.id.startsWith("readiness-ceilings-"))
      .flatMap((slide) => slide.matrix ?? []);

    expect(rows).toHaveLength(6);
    const byCeiling = (ceiling: string) =>
      rows.find((row) => row.safestNextStep.includes(ceiling))!;
    expect(byCeiling("Ceiling 25").coverage).toBe("coverage-target");
    expect(byCeiling("Ceiling 65").coverage).toBe("coverage-target");
    expect(byCeiling("Ceiling 45").coverage).toBe("published");
    expect(byCeiling("Ceiling 45").startingPoint).toContain("Case 52");
    expect(byCeiling("Ceiling 74").coverage).toBe("published");
    expect(byCeiling("Ceiling 74").startingPoint).toContain("Case 54");
    expect(byCeiling("Ceiling 70").coverage).toBe("published");
    expect(byCeiling("Ceiling 70").startingPoint).toContain("Case 58");
    expect(rows[0]!.coverage).toBe("published");
    expect(rows[0]!.startingPoint).toContain("Cases 46, 47, 48, 49");
  });

  it("lists every catalog entry exactly once across the index slides", () => {
    const indexSlides = presentation.slides.filter(
      (slide) => slide.catalogView === "index",
    );
    const listed = indexSlides.flatMap((slide) => slide.catalogSlugs ?? []);

    expect(indexSlides.map((slide) => slide.id)).toEqual([
      "scenario-bank-1",
      "scenario-bank-2",
    ]);
    expect(listed).toEqual(presentation.catalog.map((entry) => entry.slug));
    expect(new Set(listed).size).toBe(listed.length);
    for (const entry of presentation.catalog) {
      expect(entry.expectedRouting).toContain(`band ${entry.expectedBand}`);
      expect(entry.expectedRouting).toContain(`status ${entry.expectedStatus}`);
      expect(entry.expectedRouting).toContain(`action ${entry.expectedAction}`);
      for (const cap of entry.expectedCaps) {
        expect(entry.expectedRouting).toContain(cap);
      }
    }
  });

  it("rejects a catalog entry that no index slide lists", () => {
    const candidate = copyPresentation();
    const index = candidate.slides.find(
      (slide) => slide.catalogView === "index",
    )!;
    const dropped = index.catalogSlugs!.pop()!;

    expectValidationIssue(
      candidate,
      `catalog entry ${dropped} is missing from every index slide`,
    );
  });

  it("rejects a catalog entry listed on two index slides", () => {
    const candidate = copyPresentation();
    const [first, second] = candidate.slides.filter(
      (slide) => slide.catalogView === "index",
    );
    second!.catalogSlugs!.push(first!.catalogSlugs![0]!);

    expectValidationIssue(candidate, "is listed on more than one index slide");
  });

  it("rejects a worked example that is not in the catalog", () => {
    const candidate = copyPresentation();
    candidate.scenario.slug = "not-in-the-catalog";

    expectValidationIssue(
      candidate,
      "worked example not-in-the-catalog is not a catalog entry",
    );
  });

  it("states the execution-safety route as a disclosed refusal, not a run end", () => {
    const text = presentation.slides
      .flatMap((slide) => [
        slide.body,
        ...slide.bullets,
        ...slide.notes,
        ...(slide.scenarioMatrix ?? []).map((row) => row.expectedRoute),
      ])
      .join("\n");

    expect(text).not.toMatch(/guide run ends/i);
    expect(text).not.toMatch(/hard safety stop/i);
    expect(text).not.toMatch(/end this guide run/i);
    expect(text).toContain("evaluator-calibration-refused");
    expect(text).toContain("containment warning");
  });

  it("never says a scenario passed or that a run was recorded", () => {
    const rendered = JSON.stringify(presentation);

    expect(rendered).not.toMatch(/only (?:case 46|one scenario)/i);
    expect(rendered).not.toMatch(/one scenario is released/i);
    expect(rendered).not.toMatch(/scenario(?:s)? passed/i);
    expect(rendered).not.toMatch(/ready reference is the only/i);
    expect(rendered).not.toMatch(/downloadable here today/i);
    expect(rendered).not.toMatch(/6ec2b9c1/);
  });

  it("pins every published-guide claim to the full reviewed revision", () => {
    const guideSlides = presentation.slides.filter(
      (slide) => slide.evidenceState === "guide-contract",
    );

    expect(guideSlides.length).toBeGreaterThan(0);
    expect(
      guideSlides.every(
        (slide) =>
          slide.sourceRevision === "d07b62cd4abb6ecb6d2edcdcb2d535f02bb2c199",
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
    const selection = presentation.slides.find(
      (slide) => slide.id === "selection-and-heldout",
    )!;
    const optimizeStep = selection.steps.find(
      (step) => step.label === "Run the enhanced search",
    )!;

    expect(optimizeStep.detail).toContain("tests up to 12");
    expect(selection.body).toContain("up to 12 configurations");
    expect(selection.body).toContain("larger approved space");
    expect(selection.body).toContain("score that single pick once");
    expect(selection.body).toContain("never part of choosing it");
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
      "verified-run slides are disabled until retained evidence validates revisions, worker and session identity",
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
      expect(document).not.toMatch(/Expected\s+scenario\s+contract/i);
    }

    const runEvidenceDocuments = [
      "GUIDE.md",
      "docs/customer-pc-runbook.md",
      "docs/methodology.md",
      "presentation/README.md",
      "skills/traigent-first-run-scenarios/SKILL.md",
    ].map((relativePath) =>
      readFileSync(path.join(repositoryRoot, relativePath), "utf8"),
    );
    for (const document of runEvidenceDocuments) {
      expect(document).toMatch(
        /A run record,\s+result\s+JSON,\s+and\s+`PASS`\s+alone\s+are\s+insufficient/i,
      );
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

  it.each([
    [
      "slide footer evidence",
      (candidate: PresentationSpec, claim: string) => {
        candidate.slides[0]!.evidence.push(claim);
      },
    ],
    [
      "speaker notes",
      (candidate: PresentationSpec, claim: string) => {
        candidate.slides[0]!.notes.push(claim);
      },
    ],
    [
      "a catalog card",
      (candidate: PresentationSpec, claim: string) => {
        candidate.catalog[0]!.expectedRouting = `${candidate.catalog[0]!.expectedRouting} ${claim}`;
      },
    ],
    [
      "a journey step",
      (candidate: PresentationSpec, claim: string) => {
        const slide = candidate.slides.find((item) => item.steps.length > 0)!;
        slide.steps[0]!.detail = claim;
      },
    ],
    [
      "a matrix row",
      (candidate: PresentationSpec, claim: string) => {
        const slide = candidate.slides.find(
          (item) => item.testMatrix !== undefined,
        )!;
        slide.testMatrix![0]!.passSupports = claim;
      },
    ],
  ])("catches a positive run claim rendered in %s", (_surface, plant) => {
    const candidate = copyPresentation();
    plant(candidate, "We achieved a 41% cost reduction.");

    expectValidationIssue(
      candidate,
      "positive run claims require evidenceState verified-run",
    );
  });

  it("catches a positive run claim in the deck subtitle", () => {
    const candidate = copyPresentation();
    candidate.subtitle = `${candidate.subtitle} We achieved a 41% cost reduction.`;

    expectValidationIssue(
      candidate,
      "positive run claims require evidenceState verified-run, which deck-level text cannot carry",
    );
  });

  it("walks nested content rather than a hand-written field list", () => {
    const candidate = copyPresentation();
    candidate.catalog[0]!.dataset = `${candidate.catalog[0]!.dataset} We observed a measured improvement.`;

    expectValidationIssue(
      candidate,
      "positive run claims require evidenceState verified-run",
    );
  });

  it.each([
    [
      "a not-proven catalog line",
      (candidate: PresentationSpec) => {
        candidate.catalog[0]!.notProven[0] =
          "That we measured a cost reduction on live traffic";
      },
    ],
    [
      "a does-not-prove matrix cell",
      (candidate: PresentationSpec) => {
        const slide = candidate.slides.find(
          (item) => item.testMatrix !== undefined,
        )!;
        slide.testMatrix![0]!.doesNotProve =
          "That quality improved by any amount";
      },
    ],
    [
      "a speaker note that denies the claim",
      (candidate: PresentationSpec) => {
        candidate.slides[0]!.notes.push(
          "Never say we achieved a result; say what the contract states.",
        );
      },
    ],
    [
      "an evidence line that denies the claim",
      (candidate: PresentationSpec) => {
        candidate.slides[0]!.evidence.push(
          "No verified run exists for this deck",
        );
      },
    ],
  ])(
    "accepts %s, which states what the deck does not claim",
    (_surface, plant) => {
      const candidate = copyPresentation();
      plant(candidate);

      expect(() => validatePresentationContent(candidate)).not.toThrow();
    },
  );

  it("still catches a claim that follows a denial in a separate sentence", () => {
    const candidate = copyPresentation();
    candidate.slides[0]!.notes.push(
      "This deck records no run. We achieved a 41% cost reduction.",
    );

    expectValidationIssue(
      candidate,
      "positive run claims require evidenceState verified-run",
    );
  });

  it.each([
    "No customer data leaves the laptop, and we measured a 41% quality improvement.",
    "Without leaving the laptop, we measured a 41% quality improvement.",
    "None of this is a benchmark, but cost fell by 30% in our run.",
  ])(
    "still catches a claim after a denial in the same sentence: %s",
    (line) => {
      // A negator disclaims what it governs, and it stops governing at the
      // comma. Treating the whole sentence as disclaimed exempted exactly the
      // phrasings a local-only deck reaches for - an honest clause about where
      // the data stays, followed by a result nobody measured.
      const candidate = copyPresentation();
      candidate.slides[0]!.notes.push(line);

      expectValidationIssue(
        candidate,
        "positive run claims require evidenceState verified-run",
      );
    },
  );

  it.each([
    "This deck does not say we measured a 41% quality improvement.",
    "No verified run exists, so no result is claimed.",
    "Nothing here is a benchmark and no verified run exists.",
  ])("still accepts a genuine denial: %s", (line) => {
    const candidate = copyPresentation();
    candidate.slides[0]!.notes.push(line);

    expect(() => validatePresentationContent(candidate)).not.toThrow();
  });

  it("does not refuse honest contract copy on the widened surfaces", () => {
    const candidate = copyPresentation();
    const slide = candidate.slides[0]!;
    slide.evidence.push(
      "Scenario contract at case 46; no recorded coding-agent run supplied",
    );
    slide.notes.push(
      "Talk track: the deliverable is a truthful position and a next step, not a score.",
    );
    candidate.catalog[0]!.notProven[0] =
      "That a coding-agent run reached the published opening";
    candidate.catalog[0]!.dataset = `${candidate.catalog[0]!.dataset} Cost, quality, and latency are the axes a managed search would trade off.`;

    expect(() => validatePresentationContent(candidate)).not.toThrow();
  });
});
