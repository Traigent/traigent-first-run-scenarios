import { z } from "zod";

const evidenceStateSchema = z.enum([
  "guide-contract",
  "scenario-contract",
  "verified-run",
  "not-demonstrated",
]);

const metricSchema = z
  .object({
    label: z.string().min(1),
    value: z.string().min(1),
    detail: z.string().min(1),
    tone: z.enum(["blue", "green", "amber", "violet"]).default("blue"),
  })
  .strict();

const stepSchema = z
  .object({
    label: z.string().min(1),
    detail: z.string().min(1),
    executor: z.enum([
      "Coding agent",
      "Human operator",
      "Traigent service",
      "Verifier",
    ]),
    humanGate: z.string().min(1).optional(),
  })
  .strict();

const matrixRowSchema = z
  .object({
    startingPoint: z.string().min(1),
    safestNextStep: z.string().min(1),
    coverage: z.enum(["published", "coverage-target"]),
  })
  .strict();

const testLayerRowSchema = z
  .object({
    layer: z.string().min(1),
    action: z.string().min(1),
    passSupports: z.string().min(1),
    doesNotProve: z.string().min(1),
  })
  .strict();

const scenarioCoverageRowSchema = z
  .object({
    family: z.string().min(1),
    setup: z.string().min(1),
    expectedRoute: z.string().min(1),
    coverage: z.enum(["published", "coverage-target"]),
  })
  .strict();

const catalogEntrySchema = z
  .object({
    slug: z.string().min(1),
    label: z.string().min(1),
    publication: z.literal("published"),
    startingState: z.string().min(1),
    components: z.array(z.string().min(1)).min(1).max(4),
    dataset: z.string().min(1),
    evaluator: z.string().min(1),
    expectedRouting: z.string().min(1),
    testedLayer: z.string().min(1),
    notProven: z.array(z.string().min(1)).min(1).max(4),
  })
  .strict();

export const slideSchema = z
  .object({
    id: z.string().regex(/^[a-z0-9]+(?:-[a-z0-9]+)*$/),
    kind: z.enum([
      "hero",
      "statement",
      "journey",
      "evidence",
      "handoff",
      "matrix",
      "catalog",
    ]),
    section: z.enum(["core", "appendix"]).optional(),
    eyebrow: z.string().min(1),
    title: z.string().min(1),
    body: z.string().min(1),
    accent: z.string().min(1).optional(),
    quote: z.string().min(1).optional(),
    bullets: z.array(z.string().min(1)).max(6).default([]),
    metrics: z.array(metricSchema).max(4).default([]),
    steps: z.array(stepSchema).max(6).default([]),
    matrix: z.array(matrixRowSchema).min(1).max(5).optional(),
    testMatrix: z.array(testLayerRowSchema).min(1).max(4).optional(),
    scenarioMatrix: z.array(scenarioCoverageRowSchema).min(1).max(5).optional(),
    catalogView: z.enum(["setup-and-route", "data-and-limits"]).optional(),
    catalogSlug: z.string().min(1).optional(),
    evidenceState: evidenceStateSchema,
    sourceRevision: z
      .string()
      .regex(/^[0-9a-f]{40}$/)
      .optional(),
    evidence: z.array(z.string().min(1)).min(1),
    notes: z.array(z.string().min(1)).min(1),
  })
  .strict();

export const presentationSchema = z
  .object({
    schemaVersion: z.literal(2),
    title: z.string().min(1),
    subtitle: z.string().min(1),
    scenario: z
      .object({
        slug: z.string().min(1),
        legacyId: z.number().int().positive(),
        title: z.string().min(1),
        expectedBand: z.enum([
          "NOT READY",
          "PARTIAL",
          "WORKABLE",
          "STRONG",
          "EXCELLENT",
        ]),
        phase: z.literal("phase-a-opening"),
      })
      .strict(),
    catalog: z.array(catalogEntrySchema).min(1),
    slides: z.array(slideSchema).min(1),
  })
  .strict()
  .superRefine((value, context) => {
    const ids = new Set<string>();
    const titles = new Set<string>();
    const catalogSlugs = new Set<string>();
    for (const [entryIndex, entry] of value.catalog.entries()) {
      if (catalogSlugs.has(entry.slug)) {
        context.addIssue({
          code: "custom",
          message: `duplicate catalog slug ${entry.slug}`,
          path: ["catalog", entryIndex, "slug"],
        });
      }
      catalogSlugs.add(entry.slug);
    }

    for (const [index, slide] of value.slides.entries()) {
      if (ids.has(slide.id)) {
        context.addIssue({
          code: "custom",
          message: `duplicate slide id ${slide.id}`,
          path: ["slides", index, "id"],
        });
      }
      ids.add(slide.id);

      const normalizedTitle = slide.title.trim().toLocaleLowerCase("en");
      if (titles.has(normalizedTitle)) {
        context.addIssue({
          code: "custom",
          message: `duplicate slide title ${slide.title}`,
          path: ["slides", index, "title"],
        });
      }
      titles.add(normalizedTitle);

      if (
        slide.evidenceState === "guide-contract" &&
        slide.sourceRevision === undefined
      ) {
        context.addIssue({
          code: "custom",
          message: "guide-contract slides require an exact source revision",
          path: ["slides", index, "sourceRevision"],
        });
      }
      if (
        slide.evidenceState !== "guide-contract" &&
        slide.sourceRevision !== undefined
      ) {
        context.addIssue({
          code: "custom",
          message: "only guide-contract slides may declare a source revision",
          path: ["slides", index, "sourceRevision"],
        });
      }

      if (
        slide.catalogSlug !== undefined &&
        !catalogSlugs.has(slide.catalogSlug)
      ) {
        context.addIssue({
          code: "custom",
          message: `catalog slide references unknown slug ${slide.catalogSlug}`,
          path: ["slides", index, "catalogSlug"],
        });
      }
    }

    for (const [entryIndex, entry] of value.catalog.entries()) {
      const views = new Set(
        value.slides
          .filter((slide) => slide.catalogSlug === entry.slug)
          .map((slide) => slide.catalogView),
      );
      for (const requiredView of [
        "setup-and-route",
        "data-and-limits",
      ] as const) {
        if (!views.has(requiredView)) {
          context.addIssue({
            code: "custom",
            message: `catalog entry ${entry.slug} is missing ${requiredView} slide coverage`,
            path: ["catalog", entryIndex, "slug"],
          });
        }
      }
    }
  });

export type EvidenceState = z.infer<typeof evidenceStateSchema>;
export type Metric = z.infer<typeof metricSchema>;
export type JourneyStep = z.infer<typeof stepSchema>;
export type MatrixRow = z.infer<typeof matrixRowSchema>;
export type TestLayerRow = z.infer<typeof testLayerRowSchema>;
export type ScenarioCoverageRow = z.infer<typeof scenarioCoverageRowSchema>;
export type CatalogEntry = z.infer<typeof catalogEntrySchema>;
export type SlideSpec = z.infer<typeof slideSchema>;
export type PresentationSpec = z.infer<typeof presentationSchema>;

export function parsePresentation(value: unknown): PresentationSpec {
  return presentationSchema.parse(value);
}

export function coverageLabel(
  coverage: "published" | "coverage-target",
): string {
  return coverage === "published"
    ? "Published here: the ready scenario"
    : "Works in the guide today; test scenario planned";
}

export function displayEyebrow(slide: SlideSpec): string {
  return slide.section === "appendix" &&
    !slide.eyebrow.toLocaleUpperCase("en").startsWith("APPENDIX")
    ? `APPENDIX · ${slide.eyebrow}`
    : slide.eyebrow;
}

export function evidenceLabel(state: EvidenceState): string {
  switch (state) {
    case "guide-contract":
      return "Guide contract · no recorded run";
    case "scenario-contract":
      return "Scenario contract · no recorded run";
    case "verified-run":
      return "Verified run evidence";
    case "not-demonstrated":
      return "Not demonstrated in this deck";
  }
}
