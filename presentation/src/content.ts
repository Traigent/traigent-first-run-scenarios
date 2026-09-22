import { z } from "zod";

import bookingAssistantManifest from "../../scenarios/booking-assistant-next-action/scenario.json";
import bookingAssistantOpening from "../../scenarios/booking-assistant-next-action/verifier/expected-opening.json";
import chatbotVendorFlowManifest from "../../scenarios/chatbot-on-vendor-flow/scenario.json";
import chatbotVendorFlowOpening from "../../scenarios/chatbot-on-vendor-flow/verifier/expected-opening.json";
import clinicSqlExecManifest from "../../scenarios/clinic-scheduling-sql-exec/scenario.json";
import clinicSqlExecOpening from "../../scenarios/clinic-scheduling-sql-exec/verifier/expected-opening.json";
import contractClauseManifest from "../../scenarios/contract-clause-extractor/scenario.json";
import contractClauseOpening from "../../scenarios/contract-clause-extractor/verifier/expected-opening.json";
import freightQuoteManifest from "../../scenarios/freight-quote-estimator/scenario.json";
import freightQuoteOpening from "../../scenarios/freight-quote-estimator/verifier/expected-opening.json";
import helpdeskRouterManifest from "../../scenarios/helpdesk-queue-router/scenario.json";
import helpdeskRouterOpening from "../../scenarios/helpdesk-queue-router/verifier/expected-opening.json";
import incidentTriageManifest from "../../scenarios/incident-severity-triage/scenario.json";
import incidentTriageOpening from "../../scenarios/incident-severity-triage/verifier/expected-opening.json";
import meetingNotesManifest from "../../scenarios/meeting-notes-summarizer/scenario.json";
import meetingNotesOpening from "../../scenarios/meeting-notes-summarizer/verifier/expected-opening.json";
import policyHandbookManifest from "../../scenarios/policy-handbook-rag/scenario.json";
import policyHandbookOpening from "../../scenarios/policy-handbook-rag/verifier/expected-opening.json";
import regexRuleManifest from "../../scenarios/regex-rule-authoring/scenario.json";
import regexRuleOpening from "../../scenarios/regex-rule-authoring/verifier/expected-opening.json";
import returnsEmailManifest from "../../scenarios/returns-email-replies/scenario.json";
import returnsEmailOpening from "../../scenarios/returns-email-replies/verifier/expected-opening.json";
import toolDispatchManifest from "../../scenarios/tool-dispatch-selector/scenario.json";
import toolDispatchOpening from "../../scenarios/tool-dispatch-selector/verifier/expected-opening.json";
import warehouseSqlManifest from "../../scenarios/warehouse-text-to-sql/scenario.json";
import warehouseSqlOpening from "../../scenarios/warehouse-text-to-sql/verifier/expected-opening.json";
import {
  parsePresentation,
  type CatalogEntry,
  type PresentationSpec,
} from "./model";

// The route families the deck files scenarios under. They are deck authorship:
// the coverage slides group the bank by the behavior each scenario exercises,
// and the same labels head the rows there, so a family named here and absent
// from a coverage row - or the reverse - is caught by the derivation below.
const FAMILIES = [
  "Ready reference",
  "Missing material",
  "Dataset integrity",
  "Evidence strength",
  "Evaluator quality",
  "Execution safety",
  "Search-space readiness",
] as const;
type Family = (typeof FAMILIES)[number];

// The bank: every scenario the repository publishes, in case-number order.
// The manifest schema below accepts only these slugs, and the pair check under
// it refuses a manifest whose case number disagrees with this table, so a
// scenario added to `scenarios/` without a row here - or a row whose number
// drifts from its manifest - fails the build rather than missing the deck.
const SCENARIO_BANK = [
  {
    slug: "incident-severity-triage",
    legacyId: 46,
    family: "Ready reference",
    manifest: incidentTriageManifest,
    opening: incidentTriageOpening,
  },
  {
    slug: "helpdesk-queue-router",
    legacyId: 47,
    family: "Ready reference",
    manifest: helpdeskRouterManifest,
    opening: helpdeskRouterOpening,
  },
  {
    slug: "policy-handbook-rag",
    legacyId: 48,
    family: "Ready reference",
    manifest: policyHandbookManifest,
    opening: policyHandbookOpening,
  },
  {
    slug: "warehouse-text-to-sql",
    legacyId: 49,
    family: "Evaluator quality",
    manifest: warehouseSqlManifest,
    opening: warehouseSqlOpening,
  },
  {
    slug: "clinic-scheduling-sql-exec",
    legacyId: 50,
    family: "Execution safety",
    manifest: clinicSqlExecManifest,
    opening: clinicSqlExecOpening,
  },
  {
    slug: "booking-assistant-next-action",
    legacyId: 51,
    family: "Dataset integrity",
    manifest: bookingAssistantManifest,
    opening: bookingAssistantOpening,
  },
  {
    slug: "tool-dispatch-selector",
    legacyId: 52,
    family: "Search-space readiness",
    manifest: toolDispatchManifest,
    opening: toolDispatchOpening,
  },
  {
    slug: "meeting-notes-summarizer",
    legacyId: 53,
    family: "Evaluator quality",
    manifest: meetingNotesManifest,
    opening: meetingNotesOpening,
  },
  {
    slug: "contract-clause-extractor",
    legacyId: 54,
    family: "Evidence strength",
    manifest: contractClauseManifest,
    opening: contractClauseOpening,
  },
  {
    slug: "returns-email-replies",
    legacyId: 55,
    family: "Missing material",
    manifest: returnsEmailManifest,
    opening: returnsEmailOpening,
  },
  {
    slug: "freight-quote-estimator",
    legacyId: 56,
    family: "Evidence strength",
    manifest: freightQuoteManifest,
    opening: freightQuoteOpening,
  },
  {
    slug: "chatbot-on-vendor-flow",
    legacyId: 57,
    family: "Missing material",
    manifest: chatbotVendorFlowManifest,
    opening: chatbotVendorFlowOpening,
  },
  {
    slug: "regex-rule-authoring",
    legacyId: 58,
    family: "Dataset integrity",
    manifest: regexRuleManifest,
    opening: regexRuleOpening,
  },
] as const satisfies readonly {
  slug: string;
  legacyId: number;
  family: Family;
  manifest: unknown;
  opening: unknown;
}[];

const SCENARIO_SLUGS = SCENARIO_BANK.map((entry) => entry.slug) as [
  string,
  ...string[],
];

const scenarioManifestSchema = z
  .object({
    slug: z.enum(SCENARIO_SLUGS),
    legacy_id: z.number().int().positive(),
    title: z.string().min(1),
    summary: z.string().min(1),
    phase: z.literal("phase-a-opening"),
    content: z
      .object({
        origin: z.string().min(1),
        license: z.string().min(1),
      })
      .strict(),
    catalog: z
      .object({
        starting_condition: z.string().min(1),
        components: z
          .object({
            agent: z
              .object({
                state: z.string().min(1),
                path: z.string().min(1).nullable(),
                controls: z.array(z.string().min(1)),
              })
              .strict(),
            data: z
              .object({
                state: z.string().min(1),
                paths: z.array(z.string().min(1)),
              })
              .strict(),
            evaluator: z
              .object({
                state: z.string().min(1),
                path: z.string().min(1).nullable(),
                method: z.string().min(1).nullable(),
                // The `--evaluator-method` the guide was actually given when this
                // opening was measured, beside the catalog's own spelling of it.
                // Optional: the first scenario's pinned manifest predates it.
                guide_evaluator_method: z.string().min(1).optional(),
                calibration: z
                  .object({
                    path: z.string().min(1).nullable(),
                    case_count: z.number().int().nonnegative(),
                  })
                  .nullable(),
              })
              .strict(),
          })
          .strict(),
        datasets: z
          .array(
            z
              .object({
                id: z.string().min(1),
                state: z.string().min(1),
                path: z.string().min(1).nullable(),
                task: z.string().min(1).nullable(),
                // The guide's own word for the same task, recorded because the
                // declared kind changes what the readiness read reports. Optional:
                // the first scenario's pinned manifest predates it.
                guide_task_kind: z.string().min(1).optional(),
                format: z.string().min(1).nullable(),
                input_field: z.string().min(1).nullable(),
                label_field: z.string().min(1).nullable(),
                rows: z.number().int().nonnegative(),
                unique_inputs: z.number().int().nonnegative(),
                splits: z
                  .object({
                    field: z.string().min(1).nullable(),
                    counts: z.record(
                      z.string().min(1),
                      z.number().int().nonnegative(),
                    ),
                  })
                  .strict(),
                difficulty_strata: z
                  .object({
                    field: z.string().min(1).nullable(),
                    counts: z.record(
                      z.string().min(1),
                      z.number().int().nonnegative(),
                    ),
                  })
                  .strict(),
                label_shape: z
                  .object({
                    kind: z.string().min(1),
                    surface_label_count: z
                      .number()
                      .int()
                      .nonnegative()
                      .optional(),
                    label_counts: z
                      .record(z.string().min(1), z.number().int().nonnegative())
                      .optional(),
                  })
                  .passthrough(),
                // The catalog names every column a row carries, down to the
                // leaf; `passthrough_fields` is how it names the ones the task
                // does not use, so it is absent only when there are none.
                passthrough_fields: z.array(z.string().min(1)).optional(),
                limitations: z.array(z.string().min(1)),
              })
              .strict(),
          )
          .min(1),
        // Worker-visible project files that are not the dataset: a database,
        // a schema, a knowledge folder, a requirements file. Absent only when
        // the project is the dataset and the code alone.
        non_dataset_files: z.array(z.string().min(1)).optional(),
        expected_route: z
          .object({
            rationale: z.string().min(1),
            verifier_contract: z.string().min(1),
          })
          .strict(),
        evidence: z
          .object({
            demonstrates: z.array(z.string().min(1)),
            does_not_demonstrate: z.array(z.string().min(1)),
          })
          .strict(),
      })
      .strict(),
  })
  .passthrough();

const expectedOpeningSchema = z
  .object({
    schema_version: z.literal(1),
    scope: z.literal("phase-a-opening"),
    band: z.enum(["NOT READY", "PARTIAL", "WORKABLE", "STRONG", "EXCELLENT"]),
    status: z.enum(["OK", "BLOCKED"]),
    recommended_action: z.string().min(1),
    caps: z.array(z.string().min(1)),
    display: z
      .object({
        overall: z
          .object({
            score: z.number().min(0).max(100),
            confidence: z.number().min(0).max(1),
          })
          .strict(),
        pillars: z
          .object({
            agent: z
              .object({
                score: z.number().min(0).max(100),
                confidence: z.number().min(0).max(1),
              })
              .strict(),
            dataset: z
              .object({
                score: z.number().min(0).max(100),
                confidence: z.number().min(0).max(1),
              })
              .strict(),
            evaluation: z
              .object({
                score: z.number().min(0).max(100),
                confidence: z.number().min(0).max(1),
              })
              .strict(),
          })
          .strict(),
      })
      .strict(),
  })
  .strict();

type ScenarioManifest = z.infer<typeof scenarioManifestSchema>;
type ExpectedOpening = z.infer<typeof expectedOpeningSchema>;

interface BankScenario {
  slug: string;
  legacyId: number;
  family: Family;
  scenario: ScenarioManifest;
  expected: ExpectedOpening;
}

const bank: readonly BankScenario[] = SCENARIO_BANK.map((entry) => {
  const scenario = scenarioManifestSchema.parse(entry.manifest);
  const expected = expectedOpeningSchema.parse(entry.opening);
  if (scenario.slug !== entry.slug || scenario.legacy_id !== entry.legacyId) {
    throw new Error(
      `Scenario bank row ${entry.legacyId} ${entry.slug} does not match its manifest ${scenario.legacy_id} ${scenario.slug}`,
    );
  }
  return {
    slug: entry.slug,
    legacyId: entry.legacyId,
    family: entry.family,
    scenario,
    expected,
  };
});

if (new Set(bank.map((entry) => entry.legacyId)).size !== bank.length) {
  throw new Error("Scenario bank case numbers must be unique");
}

// The walkthrough slides keep one focal scenario: the ready reference that
// starts complete, so the route it shows is the shortest one.
const workedExample = bank.find((entry) => entry.legacyId === 46);
if (workedExample === undefined) {
  throw new Error("The worked example, case 46, is missing from the bank");
}
const scenario = workedExample.scenario;
const expected = workedExample.expected;
const dataset = scenario.catalog.datasets[0];

function humanize(value: string): string {
  return value
    .replaceAll("-", " ")
    .replace(/\btraigent authored\b/gi, "Traigent-authored")
    .replace(/\btraigent\b/gi, "Traigent")
    .replace(/\bphase a\b/gi, "Phase A");
}

function sentenceCase(value: string): string {
  const text = humanize(value);
  return `${text.slice(0, 1).toLocaleUpperCase("en")}${text.slice(1)}`;
}

function countsSummary(counts: Record<string, number>, absent: string): string {
  const entries = Object.entries(counts);
  return entries.length === 0
    ? absent
    : entries
        .map(([label, count]) => `${count} ${humanize(label)}`)
        .join(" / ");
}

function caseList(entries: readonly BankScenario[]): string {
  const numbers = entries.map((entry) => entry.legacyId);
  return numbers.length === 1
    ? `Case ${numbers[0]}`
    : `Cases ${numbers.join(", ")}`;
}

function casesInFamily(family: Family): readonly BankScenario[] {
  return bank.filter((entry) => entry.family === family);
}

function casesWithCap(...caps: readonly string[]): readonly BankScenario[] {
  return bank.filter((entry) =>
    entry.expected.caps.some((cap) => caps.includes(cap)),
  );
}

function casesWithoutCaps(): readonly BankScenario[] {
  return bank.filter((entry) => entry.expected.caps.length === 0);
}

function contentOriginLabel(manifest: ScenarioManifest): string {
  return manifest.content.origin === "traigent-authored"
    ? "Traigent-authored"
    : sentenceCase(manifest.content.origin);
}

function expectedRouteSummary(opening: ExpectedOpening): string {
  return `band ${opening.band} · status ${opening.status}${
    opening.status === "OK" ? " (not blocked)" : ""
  } · action ${opening.recommended_action} · ${
    opening.caps.length === 0 ? "caps none" : `caps ${opening.caps.join(", ")}`
  }`;
}

// The catalog states the label strings the rows carry and how many rows carry
// each. What the evaluator folds together is a property of the evaluator when
// it runs, which the manifest does not claim, so neither does this summary.
function labelSummaryFor(row: ScenarioManifest["catalog"]["datasets"][number]) {
  if (row.label_shape.kind === "absent") {
    return "no expected outputs on any row";
  }
  return row.label_shape.surface_label_count !== undefined &&
    row.label_shape.surface_label_count > 0
    ? `${row.label_shape.surface_label_count} distinct label strings across ${row.rows} rows`
    : `${humanize(row.label_shape.kind)} expected outputs`;
}

function catalogEntryFor(entry: BankScenario): CatalogEntry {
  const manifest = entry.scenario;
  const opening = entry.expected;
  const row = manifest.catalog.datasets[0];
  const { agent, data, evaluator } = manifest.catalog.components;
  const calibrationCount = evaluator.calibration?.case_count ?? 0;
  const splits = countsSummary(row.splits.counts, "no declared split");
  const difficulty = countsSummary(
    row.difficulty_strata.counts,
    "no difficulty strata",
  );
  return {
    slug: entry.slug,
    legacyId: entry.legacyId,
    label: `Case ${entry.legacyId}: ${manifest.title}`,
    publication: "published",
    family: entry.family,
    startingState: `${sentenceCase(manifest.catalog.starting_condition)}: agent ${humanize(agent.state)}, data ${humanize(data.state)}, evaluator ${humanize(evaluator.state)} - the states the manifest declares for the material the worker receives.`,
    components: [
      agent.state === "missing"
        ? `Agent (${agent.state}): no agent in the project`
        : agent.controls.length > 0
          ? `Agent (${agent.state}): ${agent.controls.length} tunable settings - ${agent.controls.map(humanize).join(", ")}`
          : `Agent (${agent.state}): no varying setting declared`,
      `Dataset (${data.state}): ${row.rows} rows / ${row.unique_inputs} unique inputs`,
      `Evaluator (${evaluator.state}): ${humanize(evaluator.method ?? "no evaluator method declared")}`,
      calibrationCount > 0
        ? `Calibration material: ${calibrationCount} deterministic ${calibrationCount === 1 ? "case" : "cases"} supplied`
        : "Calibration material: none supplied",
    ],
    dataset: `${contentOriginLabel(manifest)} content under ${manifest.content.license}; ${row.rows} rows (${row.unique_inputs} unique); ${splits}; difficulty: ${difficulty}; ${labelSummaryFor(row)}. Limitations: ${row.limitations.map(humanize).join(", ")}. Row provenance values are the simulated user's declarations read by the readiness scorer, not source-origin claims.`,
    evaluator:
      evaluator.method === null
        ? `${sentenceCase(row.task ?? "task not declared")} with no evaluator present; nothing scores a draft, and no calibration case is supplied.`
        : `${sentenceCase(row.task ?? "task not declared")} with ${humanize(evaluator.method)}; ${
            calibrationCount > 0
              ? `${calibrationCount} deterministic calibration ${calibrationCount === 1 ? "case is" : "cases are"} supplied, but no calibration execution or model accuracy is claimed.`
              : "no calibration case is supplied, and no calibration execution or model accuracy is claimed."
          }`,
    expectedBand: opening.band,
    expectedStatus: opening.status,
    expectedAction: opening.recommended_action,
    expectedCaps: [...opening.caps],
    expectedRouting: `Case-specific opening contract: ${expectedRouteSummary(opening)}. Rationale: ${humanize(manifest.catalog.expected_route.rationale)}.`,
    testedLayer: `${manifest.catalog.evidence.demonstrates.map(sentenceCase).join("; ")}. No recorded coding-agent run is supplied in this release.`,
    notProven: manifest.catalog.evidence.does_not_demonstrate
      .map(sentenceCase)
      .map((value) =>
        value.replace(/\bworker\b/gi, (match) =>
          match[0] === "W" ? "Coding-agent" : "coding-agent",
        ),
      ),
  };
}

const splitSummary = countsSummary(dataset.splits.counts, "no declared split");
const difficultySummary = countsSummary(
  dataset.difficulty_strata.counts,
  "no difficulty strata",
);
const calibrationCount =
  scenario.catalog.components.evaluator.calibration?.case_count ?? 0;
const labelSummary = labelSummaryFor(dataset);
const workedExampleOrigin = contentOriginLabel(scenario);
const gapScenarioCount = bank.filter(
  (entry) =>
    entry.scenario.catalog.starting_condition !== "all-components-ready",
).length;
const bankSize = bank.length;
const firstIndexHalf = bank.slice(0, Math.ceil(bankSize / 2));
const secondIndexHalf = bank.slice(firstIndexHalf.length);
const caseRange = (entries: readonly BankScenario[]) =>
  `${entries[0]!.legacyId} to ${entries[entries.length - 1]!.legacyId}`;
const NUMBER_WORDS = [
  "zero",
  "one",
  "two",
  "three",
  "four",
  "five",
  "six",
  "seven",
  "eight",
  "nine",
  "ten",
  "eleven",
  "twelve",
  "thirteen",
] as const;
const numberWord = (value: number): string =>
  NUMBER_WORDS[value] ?? String(value);

const readyCases = casesInFamily("Ready reference");
const missingMaterialCases = casesInFamily("Missing material");
const datasetIntegrityCases = casesInFamily("Dataset integrity");
const evidenceStrengthCases = casesInFamily("Evidence strength");
const evaluatorQualityCases = casesInFamily("Evaluator quality");
const executionSafetyCases = casesInFamily("Execution safety");
const searchSpaceCases = casesInFamily("Search-space readiness");
for (const family of FAMILIES) {
  if (casesInFamily(family).length === 0) {
    throw new Error(`Scenario family ${family} has no scenario in the bank`);
  }
}
const noCapCases = casesWithoutCaps();
const ceiling45Cases = casesWithCap(
  "evaluator-unvalidated",
  "agent-no-varying-knobs",
);
const generatedKeyCases = casesWithCap("dataset-generated-answer-key");
const unsoundAnswerCases = casesWithCap("dataset-unsound-expected-outputs");
const executionRefusalCases = casesWithCap("evaluator-calibration-refused");
for (const [label, cases] of [
  ["no-cap", noCapCases],
  ["ceiling-45", ceiling45Cases],
  ["generated-answer-key", generatedKeyCases],
  ["unsound-answers", unsoundAnswerCases],
  ["calibration-refused", executionRefusalCases],
] as const) {
  if (cases.length === 0) {
    throw new Error(`The deck names ${label} scenarios that the bank lacks`);
  }
}

const customerPrompt =
  "Help me run my first Traigent optimization.\nClone https://github.com/Traigent/traigent-first-run and follow GUIDE.md.";

const guideRevision = "d07b62cd4abb6ecb6d2edcdcb2d535f02bb2c199";
const readinessEvidence = `Traigent/traigent-first-run@${guideRevision.slice(0, 8)} readiness scorer`;
const bankEvidence = `${bankSize} scenario manifests and expected-opening contracts under scenarios/`;

const rawPresentation = {
  schemaVersion: 2,
  title: "Traigent First Run Scenarios",
  subtitle:
    "From varied component-readiness conditions to the safest evidenced next step within the supported first-run scope",
  scenario: {
    slug: scenario.slug,
    legacyId: scenario.legacy_id,
    title: scenario.title,
    expectedBand: expected.band,
    phase: scenario.phase,
  },
  catalog: bank.map(catalogEntryFor),
  slides: [
    {
      id: "ready-to-optimize",
      kind: "hero",
      eyebrow: "TRAIGENT FIRST RUN",
      title:
        "Start with the project you have. Leave with a justified next step.",
      accent: "justified next step",
      body: "The open-source guide helps a coding agent inspect what exists, preserve useful material, and choose the safest next action. Ready foundations move to baseline approval; gaps lead to a human decision, repair, or stronger evidence. When inspection identifies an evaluator path that would execute generated code or SQL, the guide declines to calibrate that scorer on its own initiative, records a containment warning, discloses the refusal on the readiness card, and continues. The starting state determines the route and ceiling - not a promised grade.",
      bullets: [],
      metrics: [],
      steps: [],
      evidenceState: "guide-contract",
      sourceRevision: guideRevision,
      evidence: [
        `Guided First Run contract at Traigent/traigent-first-run@${guideRevision.slice(0, 8)}; no fresh coding-agent run supplied`,
      ],
      notes: [
        "Lead with routing. Never promise a band - the customer's own material decides the ceiling before we run anything.",
        "The coding agent inspects and prepares. The human owns domain choices and approvals. The Traigent service is used only later for an explicitly approved enhanced run.",
        'Talk track: the deliverable of the first run is a truthful position and a next step, not a score. A project told "your evaluator is broken, fix it first" would still have received a useful answer without a paid optimization.',
        "An executing evaluator is a boundary of the guide, not a defect of the project: the guide will not run the customer's scorer against the customer's engine on its own initiative, says so on the card, and leaves the paid run a decision the customer takes with that disclosure in hand.",
      ],
    },
    {
      id: "shared-control",
      kind: "journey",
      eyebrow: "AGENT-LED, HUMAN-GOVERNED",
      title: "Five stages. Three actors. Human approval stays explicit.",
      body: "Every supported project enters Inspect. Gaps loop through a human choice, creation, repair, or review. Ready foundations move only after approval. When inspection identifies an evaluator path that would execute candidate code or SQL, the guide refuses to run that scorer itself, discloses the refusal, and continues; containment design stays outside the guide. The coding agent coordinates, the human governs, and Traigent runs only an approved, bounded enhanced search.",
      bullets: [],
      metrics: [],
      steps: [
        {
          label: "1 Inspect",
          detail:
            "Find the agent, dataset, and evaluator; preserve what is usable. Reads files locally only: no project code runs, no provider or Traigent calls.",
          executor: "Coding agent",
        },
        {
          label: "2 Readiness",
          detail:
            "Score the evidence, apply caps - score ceilings set by the material - and explain the safest next route. Stop before paid work when the evaluator cannot tell good from bad answers.",
          executor: "Coding agent",
          humanGate: "Human decides",
        },
        {
          label: "3 Baseline",
          detail:
            "Preserve and measure the existing baseline, or prepare a fixed 12-configuration grid only when none exists. The first model-provider stage.",
          executor: "Coding agent",
          humanGate: "Human approves",
        },
        {
          label: "4 Optimize",
          detail:
            "Search the approved space and compare it with the preserved baseline.",
          executor: "Traigent service",
          humanGate: "Human approves",
        },
        {
          label: "5 Results",
          detail:
            "Report the comparison, cost evidence, and limits, closing with one recommended next action; the human decides.",
          executor: "Coding agent",
          humanGate: "Human reviews",
        },
      ],
      evidenceState: "guide-contract",
      sourceRevision: guideRevision,
      evidence: [
        `First-run stages and approval boundaries at Traigent/traigent-first-run@${guideRevision.slice(0, 8)}`,
      ],
      notes: [
        "The boundary the presenter must draw: stages 1-2 make no calls to the customer's project-model provider or the Traigent service and incur no spend with either. The coding-agent service used to follow the guide may itself be remote and billed. Stage 3 is the first project-model stage, on the customer's approved key and cost boundary.",
        "The intention is to take every supported component-readiness state as far toward optimization as its evidence and approvals permit. It is not a promise that every project can optimize immediately or inside one session.",
        'A run that ends at stage 2 with "your evaluator scores a wrong answer above a right one, fix that first" is a successful run. Say so plainly rather than treating it as a partial outcome.',
        "Stage 4 is a separate approval from stage 3 on purpose: the baseline preserves the user's existing local space, or uses the guide's fixed 12-configuration grid only when a baseline is missing; the enhanced run is the broader search.",
      ],
    },
    {
      id: "one-customer-prompt",
      kind: "handoff",
      eyebrow: "FOR THE CUSTOMER'S REAL PROJECT",
      title:
        "Start with one prompt to the coding agent already on the project.",
      body: "The guide carries the workflow. The human keeps control of domain decisions, credentials, cost, data movement, and production-affecting actions.",
      quote: customerPrompt,
      bullets: [],
      metrics: [],
      steps: [],
      evidenceState: "guide-contract",
      sourceRevision: guideRevision,
      evidence: [
        `Published real-project handoff at Traigent/traigent-first-run@${guideRevision.slice(0, 8)}; outcome not demonstrated here`,
      ],
      notes: [
        "This clone prompt is for the customer's own project, not the context-isolated scenario audit.",
      ],
    },
    {
      id: "stage-inspect",
      kind: "statement",
      eyebrow: "STAGE 1 OF 5 - INSPECT",
      title:
        "Preserve the customer's useful work before proposing anything new.",
      body: "The coding agent performs read-only discovery of the project and identifies the selected agent, comparison data, evaluator, and meaningful tunable settings without importing or executing project code.",
      bullets: [
        "Input: the customer's project, stated task, and files already present",
        "Agent action: cite the discovered component paths and distinguish real components from temporary substitutes created for the walkthrough",
        "Human role: resolve ambiguous project intent or choose among multiple plausible components",
        "Stage output: a list of the components found, each marked present, limited, missing, or invalid",
        "Next route: continue to Readiness; do not replace usable material merely to make a demo easier",
      ],
      metrics: [],
      steps: [],
      evidenceState: "guide-contract",
      sourceRevision: guideRevision,
      evidence: [
        `Inspect-stage contract at Traigent/traigent-first-run@${guideRevision.slice(0, 8)}`,
      ],
      notes: [
        "Inspect is not a runtime test and does not prove model quality. It establishes what the project has before the guide changes anything.",
      ],
    },
    {
      id: "stage-readiness",
      kind: "statement",
      eyebrow: "STAGE 2 OF 5 - READINESS",
      title: "Turn the starting state into a route, not a sales score.",
      body: "The coding agent evaluates the agent, dataset, and evaluator. It may run the evaluator only after reading its code and confirming that exact path stays local, changes nothing outside the run, and never executes generated code or SQL. It then applies caps - score ceilings set by the material - and names the shortest justified next action.",
      bullets: [
        "Ready: explain the opening - the readiness answer produced before any paid work - and stop at the human's baseline approval",
        "Missing: derive what can be derived, ask only for an unresolved human or domain choice, create or repair the required dependency, then re-check",
        "Limited evidence: allow only a clearly bounded demonstration or request stronger material",
        "Evaluator quality: calibrate or defer an unvalidated evaluator; inspect, repair, or replace an invalid evaluator, then revalidate before any paid comparison",
        "Evaluator timeout: present the bounded human choice; do not call the evaluator broken merely because it was slow",
        "Candidate code/SQL execution path: decline to calibrate the original scorer, record a containment warning, disclose evaluator-calibration-refused on the card, and continue; the read-only question is put once, at pre-spend approval",
      ],
      metrics: [],
      steps: [],
      evidenceState: "guide-contract",
      sourceRevision: guideRevision,
      evidence: [
        `Readiness and routing contract at Traigent/traigent-first-run@${guideRevision.slice(0, 8)}`,
      ],
      notes: [
        "Readiness weights dataset, evaluation, and agent evidence, then applies caps so strength in one pillar cannot hide a broken foundation.",
        "The opening score describes the customer's starting point. A later re-score verifies that a remedy cleared its gate; it is not a new claim about the original project.",
        "The refusal on an executing path is a check the guide declines to perform, never one the customer is forbidden to make: a project's own complete passing result earns ordinary calibration credit, and the guide's contained copied-actor route can calibrate an eligible copy of the evaluator against a byte copy of a local database file - never the original target.",
      ],
    },
    {
      id: "readiness-scoring",
      kind: "statement",
      eyebrow: "STAGE 2 OF 5 - HOW THE SCORE IS BUILT",
      title: "Fourteen checks, three pillars, one number out of 100.",
      body: "Readiness runs 14 checks across the three things that decide success: your dataset, your evaluation method, and your agent. Each area carries a different weight - dataset the most, because an optimization cannot outrun the material it is measured on. The scorer itself makes no model-provider or Traigent calls.",
      bullets: [
        "Dataset - 40 points: answers to score against; examples to compare on; range of difficulty; repeated or dominant answers; where the rows came from",
        "Evaluation - 35 points: tried on answers already known right and wrong; right kind of check for this output; same answer every time; separates good answers from bad",
        "Agent - 25 points: settings-combinations to try; what the model is told and shown; whether the answer shape is pinned down; whether the agent is guaranteed to stop, and what stops it; tools it declares and can reach",
        "Bands: NOT READY 0-29; PARTIAL 30-54; WORKABLE 55-74; STRONG 75-89; EXCELLENT 90-100",
        "Thin-evidence rule: below 0.75 confidence overall or in any area, a score that would land STRONG or EXCELLENT is held at WORKABLE; lower bands are unchanged",
      ],
      metrics: [],
      steps: [],
      evidenceState: "guide-contract",
      sourceRevision: guideRevision,
      evidence: [readinessEvidence],
      notes: [
        "The weighting is the argument: 40 points on the dataset says plainly that optimization cannot outrun the data it is measured on.",
        "Each applicable check is measured, withheld, or not applicable. A withheld check keeps its weight and earns no points; it is not dropped from the denominator to flatter the score.",
        "Confidence is the share of check weight the scorer could actually measure - measurement coverage, not statistical confidence.",
        "The confidence rule is a ceiling, not a floor. It never promotes NOT READY or PARTIAL to WORKABLE.",
        "A second hold shares the same WORKABLE ceiling: until a read of the expected answers has entered - whether they answer their own questions - STRONG and EXCELLENT are withheld too. It is a hold on the band, not a number on the score, and the card reports each hold separately.",
      ],
    },
    {
      id: "readiness-ceilings-foundations",
      kind: "matrix",
      eyebrow: "STAGE 2 OF 5 - FOUNDATION CAPS",
      title: "Broken measurement sets the lowest ceilings.",
      body: "A cap is a ceiling on the total score out of 100 - the maximum the evidence allows, applied after the three weighted areas are summed; it is not a deduction. Where a row names a case, that scenario's expected-opening contract carries the cap; the invalid-evaluator row is a shipped scorer rule whose public scenario is still planned.",
      bullets: [],
      metrics: [],
      steps: [],
      matrix: [
        {
          startingPoint: `Agent, data, and evaluator are usable; no cap fires (${caseList(noCapCases)})`,
          safestNextStep:
            "No ceiling from a cap; explain readiness and stop at baseline approval",
          coverage: "published",
        },
        {
          startingPoint:
            "The evaluator rates a known-bad answer as highly as a known-good answer",
          safestNextStep:
            "Ceiling 25 and BLOCKED; repair and revalidate the evaluator first",
          coverage: "coverage-target",
        },
        {
          startingPoint: `The evaluator is unvalidated, or nothing in the agent varies (${caseList(ceiling45Cases)}: nothing varies)`,
          safestNextStep:
            "Ceiling 45; validate the evaluator or wire a setting worth searching",
          coverage: "published",
        },
      ],
      evidenceState: "guide-contract",
      sourceRevision: guideRevision,
      evidence: [readinessEvidence, bankEvidence],
      notes: [
        "A capped project is not a failed project. A truthful 65 with visible limits is more useful than an unsupported 90.",
        "A named case means the bank ships a scenario whose expected opening carries that cap, measured with the guide's own scripts over the project bytes. It is a contract to verify against, not a recorded coding-agent run and not a pass.",
        `No scenario in the bank exercises evaluator-invalid: ${caseList(ceiling45Cases)} shows the 45 ceiling through an agent with nothing to vary, not through an unvalidated evaluator.`,
      ],
    },
    {
      id: "readiness-ceilings-evidence",
      kind: "matrix",
      eyebrow: "STAGE 2 OF 5 - EVIDENCE CAPS",
      title: "Generated data still runs - it only caps the top score.",
      body: "Nothing stops here: the run continues end to end. Rows declared as generated, an answer key written by a model, or an answer a reader found does not answer its own question all cap how high the score can go until the evidence is settled - a caveat for the summary, not a blocker.",
      bullets: [],
      metrics: [],
      steps: [],
      matrix: [
        {
          startingPoint:
            "Every comparison row is declared generated rather than observed",
          safestNextStep:
            "Ceiling 65; label the demo honestly and connect real rows before a production claim",
          coverage: "coverage-target",
        },
        {
          startingPoint: `Rows are declared real, but a model generated the answer key (${caseList(generatedKeyCases)})`,
          safestNextStep:
            "Ceiling 74; compare cautiously and obtain human review before trusting the margin",
          coverage: "published",
        },
        {
          startingPoint: `The answers were read, and one of them does not answer its own question (${caseList(unsoundAnswerCases)})`,
          safestNextStep:
            "Ceiling 70; put the row and the reason to the customer, and edit nothing until they answer",
          coverage: "published",
        },
      ],
      evidenceState: "guide-contract",
      sourceRevision: guideRevision,
      evidence: [readinessEvidence, bankEvidence],
      notes: [
        "A fully generated dataset caps at 65, so STRONG and EXCELLENT are arithmetically unreachable until the evidence changes. No scenario in the bank declares every row generated; that row stays a coverage target.",
        "These caps read the fictional user's row declarations. Repository authorship is a separate contract: every scenario in the bank is Traigent-authored synthetic content whose in-world provenance values simulate a user declaration.",
        `The 70 ceiling is the one cap on this slide that no declaration can raise: it comes from the coding assistant's own read of five drawn rows, so ${caseList(unsoundAnswerCases)} reaches it only because something actually read a row and said what was wrong with it.`,
      ],
    },
    {
      id: "stage-baseline",
      kind: "statement",
      eyebrow: "STAGE 3 OF 5 - BASELINE",
      title:
        "Measure the current configuration before searching for a better one.",
      body: "Only after the readiness route and explicit human approval does the coding agent run the customer's existing local baseline exactly as defined, or, when none exists, prepare the guide's fixed grid of 12 configurations, each run once locally. It uses the approved provider credential, dataset, evaluator, and cost limit.",
      bullets: [
        "Human approves the provider, credential path, data boundary, expected calls, and cost cap",
        "A user-owned baseline keeps its exact configuration space and selection logic; it is never padded. When it is too large for the approved budget, the guide proposes a smaller representative subset - disclosed and approved, never silent",
        "Only a missing baseline gets the guide's generated 12-configuration local grid",
        "The run records quality plus available cost and latency evidence for that exact setup",
        "Provider errors, missing credentials, or cost-boundary failures stop loudly; access is never invented",
        "Stage output: the saved baseline result and a separate decision on whether the enhanced run is justified",
      ],
      metrics: [],
      steps: [],
      evidenceState: "guide-contract",
      sourceRevision: guideRevision,
      evidence: [
        `Baseline-stage contract at Traigent/traigent-first-run@${guideRevision.slice(0, 8)}; no live baseline supplied`,
      ],
      notes: [
        "The coding-agent service itself may already be remote or billed. Baseline is specifically the first model-provider execution stage in this workflow.",
        "An existing baseline is never replaced: even a one-row baseline is preserved unchanged and measured as it stands. Only a truly missing baseline gets the generated grid - an exact, pre-declared 12 configurations, each run once, with count and cost approved before any spend; it can shrink only by approved disclosure and never grows.",
        "With more than 100 usable rows the guide selects a bounded first-run subset - 18 rows by default, spread across difficulty bands and drawn within each split - estimates cost from that subset, and reports both subset and full sizes.",
      ],
    },
    {
      id: "stage-optimize",
      kind: "statement",
      eyebrow: "STAGE 4 OF 5 - OPTIMIZE",
      title:
        "A first taste of optimization - two small runs, not the full engine.",
      body: "After the baseline, one bounded enhanced run starts under its own approval: Traigent tests up to 12 configurations from the approved space, inside a small budget and time box. Results appear in your Traigent portal; the run closes with a recommended next step, and finding no winner is a reported outcome, not a failure.",
      bullets: [
        "Human separately approves Traigent access, provider use, data movement, the trial bound (maximum number of configurations tested), and spend",
        "Only tunable settings proven to change the request actually sent to the model belong in the search space",
        "The baseline result stays unchanged as the reference; every candidate is compared on the same dataset and evaluator",
        "Credential, service, provider, or budget failures stop; no mock or random result replaces them",
        "Stage output: the exact search space submitted, every configuration tested, and its measured scores",
      ],
      metrics: [],
      steps: [],
      evidenceState: "guide-contract",
      sourceRevision: guideRevision,
      evidence: [
        `Optimization-stage contract at Traigent/traigent-first-run@${guideRevision.slice(0, 8)}; no enhanced run supplied`,
      ],
      notes: [
        "Baseline approval does not pre-authorize optimization. The second gate is deliberate because the number of calls and the data boundary can change.",
      ],
    },
    {
      id: "selection-and-heldout",
      kind: "journey",
      eyebrow: "STAGES 3 TO 5 - HONEST COMPARISON",
      title:
        "Choose on tuning evidence; check one recommendation on held-out rows.",
      body: "Two small runs, two spaces: the baseline runs your current configuration (or the fixed 12-configuration grid when none exists); the enhanced run tests up to 12 configurations Traigent picks from a larger approved space. One pick comes from the tuning evidence; the held-out rows then score that single pick once - a check of the winner, never part of choosing it.",
      bullets: [],
      metrics: [],
      steps: [
        {
          label: "Measure the baseline",
          detail:
            "Preserve the user's existing local baseline exactly, or use the guide's 12-configuration default only when missing; any reduction from that target is disclosed and approved first.",
          executor: "Coding agent",
          humanGate: "Human approves spend",
        },
        {
          label: "Run the enhanced search",
          detail:
            "Traigent tests up to 12 configurations from the approved larger space, using the same tuning rows and evaluator.",
          executor: "Traigent service",
          humanGate: "Human separately approves",
        },
        {
          label: "Lock one recommendation",
          detail:
            "Compare baseline and enhanced-run tuning evidence; include the accuracy-versus-cost trade-off (the frontier) when cost is measured; then select without reading held-out scores.",
          executor: "Coding agent",
        },
        {
          label: "Check held-out rows once",
          detail:
            "Score the locked recommendation once on rows no search evaluated; small held-out sets mean low statistical confidence - the report discloses it.",
          executor: "Coding agent",
          humanGate: "Human reviews evidence",
        },
      ],
      evidenceState: "guide-contract",
      sourceRevision: guideRevision,
      evidence: [
        `Traigent/traigent-first-run@${guideRevision.slice(0, 8)} comparison contract`,
        "The worked example, case 46, declares separate tuning and holdout pools",
      ],
      notes: [
        "Case 46 declares 100 tuning and 20 holdout rows. That is the public dataset inventory, not a claim that every paid first run uses all 120 rows; the run plan must record the selected row IDs and any bounded subset.",
        "Selecting the best of several configurations on the same tuning rows partly selects sample noise. Held-out scoring checks that risk; it does not eliminate it or prove generalization.",
        "When the coding agent has seen or authored the reserved rows, the guide calls the result held-back and non-blind - kept out of tuning but not hidden from the agent - rather than a sealed holdout.",
        `${caseList(datasetIntegrityCases)} is the bank's counter-example: its holdout side repeats tuning transcripts, and its expected opening blocks on that overlap before any comparison is run.`,
      ],
    },
    {
      id: "stage-results",
      kind: "statement",
      eyebrow: "STAGE 5 OF 5 - RESULTS",
      title:
        "Report what changed, what it cost, and what the evidence cannot support.",
      body: "The coding agent compares the approved search with the baseline, identifies the supported trade-offs, retains the exact run record, and gives the human a decision rather than an unexplained winning score.",
      bullets: [
        "Compare the recommended configuration with the best baseline; show the quality-cost frontier when cost was measured",
        "Report the one held-out check with its sample-size and non-blind limits; retain the exact run evidence and failures",
        "Human chooses adoption, more evidence, another bounded search, or no change; nothing is applied automatically",
        "State what the run cannot prove: universal quality, production safety, generalization, or a guaranteed business result",
      ],
      metrics: [],
      steps: [],
      evidenceState: "guide-contract",
      sourceRevision: guideRevision,
      evidence: [
        `Results-stage contract at Traigent/traigent-first-run@${guideRevision.slice(0, 8)}; no live result artifact supplied`,
      ],
      notes: [
        "The end goal is an explainable decision. A result without its baseline, evidence boundary, and limitations is not a valid first-run outcome.",
        "If the recommended configuration is the one already in use, that is a useful result: the current settings were not shown to be the problem.",
      ],
    },
    {
      id: "credible-reproduction",
      kind: "statement",
      eyebrow: "OPEN AND REPRODUCIBLE",
      title: "Anyone can re-run a scenario and check the result themselves.",
      body: `A fresh coding-agent session receives a clean copy of the customer-shaped project, including its evaluator, plus the guide and handoff. The scenario verifier, expected result, and previous outputs stay outside that session's assigned context. The same protocol applies to each of the ${numberWord(bankSize)} scenarios.`,
      bullets: [
        "Everything needed to re-run it is in this repository - no Traigent account, model key, or prior run required, only a coding agent",
        "The coding-agent session is not given the expected result or the verifier kept by the test operator",
        "Open means inspectable; we do not claim the expected answers are hidden from someone who deliberately looks them up",
      ],
      metrics: [],
      steps: [],
      evidenceState: "scenario-contract",
      evidence: ["Scenario isolation methodology"],
      notes: [
        "Customer language: public means inspectable; context-isolated means the coding-agent session does not receive the expected answer.",
      ],
    },
    {
      id: "dataset-origin",
      kind: "statement",
      eyebrow: "TEST DATA - EVERY SCENARIO",
      title:
        "Synthetic test data is useful when its origin and limits stay visible.",
      body: `Every test scenario ships purpose-written synthetic data - authored for the test, never customer material - so runs are reproducible and safe to share. The example's rows are ${workedExampleOrigin}, licensed under ${scenario.content.license}; no upstream dataset license travels with them, so you may run, copy and adapt the material under that license. The worked example shows the pattern; ${gapScenarioCount} of the ${bankSize} scenarios start from a gap on purpose.`,
      bullets: [
        `In the example: ${dataset.rows} authored incident reports, ${dataset.unique_inputs} unique inputs; the declared pool is ${splitSummary}`,
        `Even difficulty coverage: ${difficultySummary}, so the row pool does not win its score by concentrating only on easy cases`,
        `Output shape: ${labelSummary}; the deterministic evaluator maps equivalent surface labels before comparison - evaluator behavior, not a validated catalog claim`,
        "A row value such as provenance: real is part of the scenario's fiction - the simulated user's declaration read by the readiness scorer - not a claim about the repository file, whose own origin and license are pinned by scenario.py check against its constants",
        "The scenario and expected result are open for anyone to inspect; the fresh coding-agent session receives neither the expected result nor the operator-kept verifier",
        "The 100/20 split demonstrates separate tuning and holdout pools; a paid run must still record the exact bounded rows it actually uses",
      ],
      metrics: [],
      steps: [],
      evidenceState: "scenario-contract",
      evidence: [
        "scenarios/incident-severity-triage/scenario.json",
        "Apache-2.0 repository license",
      ],
      notes: [
        "Repository origin and in-world row provenance are two different contracts. Never describe these rows as collected customer incidents.",
        "Public inspectability makes the test explainable. Context isolation keeps the expected result out of the assigned coding-agent context; it does not claim secrecy against deliberate lookup.",
        "The gap scenarios are gaps by construction - a leaky split, an unrunnable grader, a missing evaluator, an absent agent - written so the guide's route through each can be checked against a contract, not defects that crept in.",
      ],
    },
    {
      id: "case-46",
      kind: "evidence",
      eyebrow: "A WORKED EXAMPLE",
      title:
        "One excellent-readiness scenario: incident severity triage (scenario 46).",
      body: "A complete, known-good starting point: agent, labeled data, and evaluator all present, so its expected readiness grade is Excellent from the start. It is the bank's worked example because it shows the shortest route end to end - the number 46 is its catalog case number. Its expected result is specific to this scenario, not a score promised to other projects.",
      bullets: [],
      metrics: [
        {
          label: "Rows",
          value: String(dataset.rows),
          detail: splitSummary,
          tone: "blue",
        },
        {
          label: "Agent settings",
          value: String(scenario.catalog.components.agent.controls.length),
          detail: scenario.catalog.components.agent.controls
            .map(humanize)
            .join(", "),
          tone: "violet",
        },
        {
          label: "Evaluator",
          value: "Exact",
          detail: humanize(
            scenario.catalog.components.evaluator.method ?? "not declared",
          ),
          tone: "blue",
        },
        {
          label: "Expected route",
          value: sentenceCase(expected.recommended_action),
          detail: "Published opening contract; no recorded run",
          tone: "amber",
        },
      ],
      steps: [],
      evidenceState: "scenario-contract",
      evidence: [
        "scenarios/incident-severity-triage/scenario.json",
        "scenarios/incident-severity-triage/verifier/expected-opening.json",
      ],
      notes: [
        "Talk track: this is the ready-components route in the matrix, not evidence that gap repair has passed.",
        "Expected top band because this case starts complete. It is a reference, not a product success threshold.",
        `Case 46 is a stable numeric alias for incident-severity-triage. The bank numbers its ${bankSize} cases ${caseRange(bank)}; the numbers are aliases, not a count of anything.`,
        'If a prospect asks "will we get Excellent?", the honest answer is: show me your data, your evaluator, and whether anything in your agent varies - those three set your ceiling before we run anything.',
        `The ${dataset.rows} incident reports are Traigent-authored synthetic data under ${scenario.content.license}; they contain no customer or third-party dataset.`,
      ],
    },
    {
      id: "test-layers",
      kind: "matrix",
      eyebrow: "THREE DIFFERENT CHECKS",
      title: "Three checks, three different proofs.",
      body: `Passing one check proves only that check - never the next one. Today this repository ships ${bankSize} scenarios in full, each with the expected opening to compare against; no recorded agent run is included. Nothing here requires a prior run: anyone can run all three from a fresh clone - the paid layer with their own approved keys and spend.`,
      bullets: [],
      metrics: [],
      testMatrix: [
        {
          layer: "Catalog check",
          action:
            "Validate the files and the expected-result contract (scenario.py check)",
          passSupports: "Package is structurally ready to prepare",
          doesNotProve: "Agent behavior or live value",
        },
        {
          layer: "Phase A (free opening)",
          action: "Fresh coding-agent session performs Inspect and Readiness",
          passSupports:
            "The agent's captured readiness matched the published expected result",
          doesNotProve: "Paid baseline or optimization",
        },
        {
          layer: "Phase B (paid optimization)",
          action: "Approved Baseline, Optimize, and Results",
          passSupports: "Live evidence for that approved run",
          doesNotProve: "Universal outcome or production safety",
        },
      ],
      steps: [],
      evidenceState: "scenario-contract",
      evidence: ["Published verification and phase boundaries"],
      notes: [
        "Catalog check validates the package; it does not run a coding agent.",
        "Phase A covers Inspect and Readiness. Phase B covers approved Baseline, Optimize, and Results.",
        "No prior run is needed for any layer; each one can be run today from a fresh clone.",
        "An expected opening is a captain measurement of the guide's own scripts over the project bytes at the pinned revision. It says what the readiness card should read; it does not say a coding agent has produced that card.",
      ],
    },
    {
      id: "prepare-and-verify",
      kind: "journey",
      eyebrow: "REPRODUCE ON A CUSTOMER PC",
      title: "One safe preparation flow, one independent result check.",
      body: "Start at https://github.com/Traigent/traigent-first-run-scenarios and follow docs/customer-pc-runbook.md. The CLI creates a disposable project copy without verifier material; the test operator then compares the saved readiness answer with the published expected result for the exact scenario version recorded in run.json.",
      bullets: [],
      metrics: [],
      steps: [
        {
          label: "Check",
          detail: "Validate the complete scenario package.",
          executor: "Human operator",
        },
        {
          label: "Prepare",
          detail: "Copy the project with a pinned local guide checkout.",
          executor: "Human operator",
        },
        {
          label: "Run",
          detail: "Give the printed handoff to a fresh coding agent.",
          executor: "Coding agent",
          humanGate: "Human starts isolated run",
        },
        {
          label: "Verify",
          detail:
            "Confirm run.json records the exact scenario version that was run, then compare the captured readiness fields with the published contract.",
          executor: "Verifier",
        },
      ],
      evidenceState: "scenario-contract",
      evidence: ["Scenario CLI and customer-PC runbook"],
      notes: [
        "The public verifier remains with the test operator, outside the coding agent's project copy.",
        "The same four steps apply to any case number in the bank; the runbook uses case 46 as its example.",
      ],
    },
    {
      id: "trust-boundary",
      kind: "statement",
      eyebrow: "VISIBLE HUMAN CONTROL",
      title:
        "Phase A, the free opening, covers inspection and readiness only; optimization is separate.",
      body: "Credentials, paid calls to your model provider or Traigent, moving data out of your environment, installing software, changing production, and optimization each remain separate approval gates. A Phase A result does not authorize Phase B.",
      bullets: [
        "Phase A stops at the first material human decision",
        "Access codes and API keys belong to Phase B, the separately approved paid optimization",
        "No claim of quality, cost, or latency improvement",
        "No production mutation or data movement beyond the approved coding-agent context",
        "The coding-agent service itself may be remote and billed; the human approves that service and the context it receives",
      ],
      metrics: [],
      steps: [],
      evidenceState: "guide-contract",
      sourceRevision: guideRevision,
      evidence: [
        `Phase A and Phase B boundary at Traigent/traigent-first-run@${guideRevision.slice(0, 8)}`,
      ],
      notes: [
        "This is the security and procurement slide. Keep the boundary concrete.",
      ],
    },
    {
      id: "next-step",
      kind: "statement",
      eyebrow: "TWO WAYS TO USE THIS MATERIAL",
      title:
        "Two ways to try it today: run a scenario, or point the guide at your project.",
      accent: "run a scenario",
      body: "The two paths are independent, and neither needs any prior run. Trying a scenario is not a prerequisite for using the guide on a real project, and neither path authorizes later paid work - provider calls, Traigent service use, and spend each need their own approval.",
      bullets: [
        `Try a scenario: check and prepare any of the ${bankSize} cases; give a fresh coding agent only the printed instructions`,
        "Then verify: save the readiness answer the agent produced and compare it with the expected opening that ships in this repository",
        "Your project: paste the clone prompt from earlier into the coding agent already working in your repository",
        "Shared boundary: neither path authorizes later provider calls, Traigent service use, managed search, or spend",
        "After a first result, the guide offers the SDK skills: npx skills add Traigent/traigent-skills --list",
      ],
      metrics: [],
      steps: [],
      evidenceState: "guide-contract",
      sourceRevision: guideRevision,
      evidence: [
        `Published guide and scenario handoff boundaries at Traigent/traigent-first-run@${guideRevision.slice(0, 8)}; no live outcome claimed`,
      ],
      notes: [
        "The two available paths are alternatives: audit a public scenario, or try the guide on the customer's own project.",
        "The context-isolated audit uses the separate handoff printed by prepare, while the real project uses the clone prompt.",
        "The SDK skills are Apache-2.0 documentation; the SDK they drive is licensed separately (AGPL-3.0-only or commercial). Installing skills authorizes nothing - Phase B still needs its own approval.",
      ],
    },
    {
      id: "different-starting-points",
      kind: "statement",
      eyebrow: "FROM STARTING STATE TO NEXT ACTION",
      title:
        "The goal is justified movement toward optimization - not the same score for everyone.",
      body: "The guide routes every condition below toward optimization, creating or repairing what is missing with the user's approval - every route is implemented at the pinned guide revision. The next slide shows one worked example: a project that starts ready. The same flow carries a broken or half-ready project to the same finish line.",
      bullets: [
        "Ready → explain readiness; stop at baseline approval",
        "Missing or invalid material → preserve, resolve the human choice, create or repair, then re-check",
        "Weak evidence → bound the demonstration or request stronger material",
        "Evaluator unvalidated, invalid, or timing out → calibrate, repair or replace, or, on a timeout, ask the human how to proceed",
        "Executing evaluator path identified → decline to calibrate it here, disclose the refusal on the card, and continue",
        "No meaningful request variation → wire and locally prove a tunable setting",
      ],
      metrics: [],
      steps: [],
      evidenceState: "guide-contract",
      sourceRevision: guideRevision,
      evidence: [
        `Route behavior at Traigent/traigent-first-run@${guideRevision.slice(0, 8)}`,
      ],
      notes: [
        "Do not promise an Excellent opening. A gap, cap, repair, or stop can be the correct and useful outcome for the material the customer brought.",
        "The six bullets summarize next-action families; they are not an exhaustive taxonomy of every project condition.",
        `Every family here has at least one downloadable scenario in the bank of ${bankSize}, each shipping an expected opening measured from the guide's scripts - not a recorded coding-agent run. Not every condition inside a family has one: no scenario exercises an invalid evaluator or an evaluator timeout.`,
      ],
    },
    {
      id: "scenario-families-material",
      kind: "matrix",
      eyebrow: "APPENDIX - SCENARIO FAMILIES 1 OF 2",
      title: "Material and evidence routes remain separate test families.",
      body: "Each family below has at least one published scenario in the bank. A family can need multiple cases, and publishing one case does not cover its whole family. The status column says the case exists with an expected opening to verify against - not that a coding agent has run it.",
      bullets: [],
      metrics: [],
      steps: [],
      scenarioMatrix: [
        {
          family: "Ready reference",
          setup: `${caseList(readyCases)}: labeled synthetic rows with tuning and holdout pools; usable tunable settings; a deterministic non-executing evaluator with calibration probes`,
          expectedRoute:
            "Recognize that the components are ready, explain the opening, and stop at baseline approval",
          coverage: "published",
        },
        {
          family: "Missing material",
          setup: `${caseList(missingMaterialCases)}: inbound emails with no expected replies and no evaluator (55); a hosted vendor flow where no local agent exists (57)`,
          expectedRoute:
            "Preserve what exists; ask only for an unresolved human or domain choice; create or repair a required dependency; re-check before paid work",
          coverage: "published",
        },
        {
          family: "Dataset integrity",
          setup: `${caseList(datasetIntegrityCases)}: a review set that repeats six tuning transcripts on the holdout side`,
          expectedRoute:
            "Repair invalid comparison material; do not optimize against a split or answer key that cannot support the claim",
          coverage: "published",
        },
        {
          family: "Evidence strength",
          setup: `${caseList(evidenceStrengthCases)}: an answer key drafted by a model and never reviewed (54); 24 worked quotes, too few for a fine-grained comparison (56)`,
          expectedRoute:
            "Label a bounded demonstration honestly, ask for human review where required, and limit the claim",
          coverage: "published",
        },
      ],
      evidenceState: "guide-contract",
      sourceRevision: guideRevision,
      evidence: [
        `Route contracts in Traigent/traigent-first-run@${guideRevision.slice(0, 8)}; ${bankEvidence}`,
      ],
      notes: [
        "Published means the scenario ships in full with an expected opening measured from the guide's own scripts over the project bytes. Do not say any row passed: no recorded coding-agent run exists for any case.",
        "Repository origin and the fictional row provenance declarations are different facts; every case in the bank is Traigent-authored synthetic content.",
        "Conditions the family covers but the bank does not yet exercise stay open: malformed rows, an empty split, and a fully generated dataset have no scenario.",
      ],
    },
    {
      id: "scenario-families-gates",
      kind: "matrix",
      eyebrow: "APPENDIX - SCENARIO FAMILIES 2 OF 2",
      title:
        "Evaluator, execution, and search-space gates need distinct tests.",
      body: "These families can require multiple cases because their conditions lead to materially different actions. A repair route, a human timeout choice, and a disclosed refusal to run an executing scorer must not be presented as the same tested behavior. Each gate ships in the guide today; the case named is the public scenario that lets you reproduce it.",
      bullets: [],
      metrics: [],
      steps: [],
      scenarioMatrix: [
        {
          family: "Evaluator quality",
          setup: `${caseList(evaluatorQualityCases)}: SQL compared as normalized text, which the card flags as a task-fit warning without a cap (49); grading delegated to a package nobody can run (53)`,
          expectedRoute:
            "Calibrate, repair, or replace it; on a timeout, ask the human one bounded question - never call a slow evaluator broken",
          coverage: "published",
        },
        {
          family: "Execution safety",
          setup: `${caseList(executionSafetyCases)}: the evaluator scores by running the generated SQL against the shipped clinic database`,
          expectedRoute:
            "Decline to calibrate the original scorer; record a containment warning; disclose evaluator-calibration-refused on the card; continue, with the read-only question put once at pre-spend approval",
          coverage: "published",
        },
        {
          family: "Search-space readiness",
          setup: `${caseList(searchSpaceCases)}: one fixed model and instruction, so no setting varies between requests`,
          expectedRoute:
            "Establish and locally verify real request variation before requesting approval for paid search",
          coverage: "published",
        },
      ],
      evidenceState: "guide-contract",
      sourceRevision: guideRevision,
      evidence: [
        `Route contracts in Traigent/traigent-first-run@${guideRevision.slice(0, 8)}; ${bankEvidence}`,
      ],
      notes: [
        "An evaluator timeout is not proof that the evaluator is broken. The guide presents a bounded human choice rather than silently changing the limit. No scenario in the bank exercises a timeout or an evaluator that fails on known cases.",
        `${caseList(executionRefusalCases)} carries evaluator-calibration-refused, which does not block: the card says the check was declined and why, claims neither that the evaluator is sound nor that it is broken, and the run continues on that disclosure.`,
        "The guide supplies no containment design for the original target; its contained copied-actor route calibrates an eligible copy against a byte copy of a local database file, and a manual containment review stays available outside the guide.",
      ],
    },
    {
      id: "scenario-bank-1",
      kind: "catalog",
      eyebrow: "SCENARIO CATALOG 1 OF 2",
      title: `${sentenceCase(numberWord(bankSize))} scenarios, one contract each: cases ${caseRange(firstIndexHalf)}.`,
      body: "Each row is a scenario the repository ships in full, with the opening its expected-opening contract records - band, status, action, and caps, the four fields the verifier compares. The captain measured them with the guide's own scripts over the project bytes at the pinned revision; no row is a recorded coding-agent run.",
      bullets: [],
      metrics: [],
      steps: [],
      catalogView: "index",
      catalogSlugs: firstIndexHalf.map((entry) => entry.slug),
      evidenceState: "scenario-contract",
      evidence: [bankEvidence],
      notes: [
        "Read the family column as the deck's grouping and the other columns as the manifest's and the contract's own values.",
        `The ready references are ${numberWord(readyCases.length)} because a ready project is the shortest route; the bank exists for the other ${numberWord(gapScenarioCount)}.`,
        "Case 49 is a ready-looking opening with a warning inside it: the card flags SQL compared as text as a task-fit concern without capping the score, which is why the deck files it under evaluator quality.",
      ],
    },
    {
      id: "scenario-bank-2",
      kind: "catalog",
      eyebrow: "SCENARIO CATALOG 2 OF 2",
      title: `Cases ${caseRange(secondIndexHalf)}: the gaps a project usually arrives with.`,
      body: "Every row on this slide starts from a gap by construction. Blocked rows stop at a human decision or a repair; the others continue with a cap or a disclosure. The action and caps are the exact identifiers the readiness card prints and the verifier compares.",
      bullets: [],
      metrics: [],
      steps: [],
      catalogView: "index",
      catalogSlugs: secondIndexHalf.map((entry) => entry.slug),
      evidenceState: "scenario-contract",
      evidence: [bankEvidence],
      notes: [
        "A BLOCKED status is a routing outcome, not a failed test: the scenario exists to check that the guide stops where its contract says it stops.",
        "Case 57 has no local agent at all; its score is the lowest in the bank because the agent pillar cannot be measured, not because the data or evaluator are weak.",
      ],
    },
    {
      id: "published-scenario-catalog",
      kind: "catalog",
      eyebrow: "WORKED EXAMPLE IN FULL",
      title: "One entry in full: what case 46 contains and expects.",
      body: `The catalog records what each published scenario represents, what route it expects, and what it does not prove. The two index slides list all ${numberWord(bankSize)}; these two show the worked example's entry in full.`,
      bullets: [],
      metrics: [],
      steps: [],
      catalogView: "setup-and-route",
      catalogSlug: scenario.slug,
      evidenceState: "scenario-contract",
      evidence: [
        "scenarios/incident-severity-triage/scenario.json",
        "Published dataset and expected opening result",
      ],
      notes: [
        "This appendix answers what the worked example actually contains; every other case has the same fields in its own scenario.json and README.",
        "Synthetic describes repository origin. The row value provenance: real is simulated scorer metadata inside the scenario.",
        "Nothing here is observed accuracy or evidence of a live optimization.",
        `Calibration is a sample by design: ${calibrationCount} ${calibrationCount === 1 ? "case carries" : "cases carry"} four probes each - a correct answer, an equivalent answer spelled differently, a near-miss and a wrong one. That asks whether the scorer agrees with itself, which is a property of the scorer rather than of the row count, so running it over all ${dataset.rows} rows would cost more and would not change what the probes already establish. Where inputs are expensive - long documents in, prose out - a handful of probes is the only practical check, and it is sound for the same reason.`,
      ],
    },
    {
      id: "published-scenario-data",
      kind: "catalog",
      eyebrow: "WORKED EXAMPLE IN FULL",
      title: "Synthetic origin and evaluation limits stay explicit.",
      body: "The worked example makes data shape, evaluator behavior, expected routing, and unsupported claims visible without presenting synthetic rows as customer evidence. The same limits apply to every case in the bank.",
      bullets: [],
      metrics: [],
      steps: [],
      catalogView: "data-and-limits",
      catalogSlug: scenario.slug,
      evidenceState: "scenario-contract",
      evidence: [
        "scenarios/incident-severity-triage/scenario.json",
        "Published dataset and expected opening result",
      ],
      notes: [
        `${dataset.unique_inputs} unique inputs; ${splitSummary}; difficulty: ${difficultySummary}.`,
        `${labelSummary} before deterministic exact/binary scoring.`,
        "Repository origin is Traigent-authored synthetic; provenance: real is simulated row metadata for the readiness scorer.",
        `Written for this scenario, not sampled or adapted from a public benchmark, so no upstream dataset license applies. ${scenario.content.license} with NOTICE: run it, copy it, adapt it.`,
      ],
    },
  ],
} satisfies PresentationSpec;

const coreSlideIds = [
  "ready-to-optimize",
  "shared-control",
  "one-customer-prompt",
  "different-starting-points",
  "case-46",
  "test-layers",
  "prepare-and-verify",
  "trust-boundary",
  "next-step",
] as const;

const appendixSlideIds = [
  "stage-inspect",
  "stage-readiness",
  "readiness-scoring",
  "readiness-ceilings-foundations",
  "readiness-ceilings-evidence",
  "stage-baseline",
  "stage-optimize",
  "selection-and-heldout",
  "stage-results",
  "credible-reproduction",
  "dataset-origin",
  "scenario-families-material",
  "scenario-families-gates",
  "scenario-bank-1",
  "scenario-bank-2",
  "published-scenario-catalog",
  "published-scenario-data",
] as const;

const sourceSlides: PresentationSpec["slides"] = rawPresentation.slides;
const slidesById = new Map(sourceSlides.map((slide) => [slide.id, slide]));
const slideForId = (id: string): PresentationSpec["slides"][number] => {
  const slide = slidesById.get(id);
  if (slide === undefined) {
    throw new Error(`Presentation order references missing slide ${id}`);
  }
  return slide;
};
const orderedSlideIds = [...coreSlideIds, ...appendixSlideIds];
const orderedSlideIdSet = new Set<string>(orderedSlideIds);
if (
  orderedSlideIdSet.size !== sourceSlides.length ||
  sourceSlides.some((slide) => !orderedSlideIdSet.has(slide.id))
) {
  throw new Error("Presentation order must include every slide exactly once");
}
const coreSlides = coreSlideIds.map((id) => ({
  ...slideForId(id),
  section: "core" as const,
}));
const appendixSlides = appendixSlideIds.map((id) => ({
  ...slideForId(id),
  section: "appendix" as const,
}));

export const coreSlideCount = coreSlides.length;
export const scenarioBankSize = bankSize;
export const presentation = parsePresentation({
  ...rawPresentation,
  slides: [...coreSlides, ...appendixSlides],
});
export { customerPrompt };
