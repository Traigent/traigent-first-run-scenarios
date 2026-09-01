import { z } from "zod";

import scenarioManifestJson from "../../scenarios/incident-severity-triage/scenario.json";
import expectedOpeningJson from "../../scenarios/incident-severity-triage/verifier/expected-opening.json";
import { parsePresentation, type PresentationSpec } from "./model";

const scenarioManifestSchema = z
  .object({
    slug: z.literal("incident-severity-triage"),
    legacy_id: z.literal(46),
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
                calibration: z
                  .object({
                    path: z.string().min(1),
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
    caps: z.array(z.unknown()),
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

const scenario = scenarioManifestSchema.parse(scenarioManifestJson);
const expected = expectedOpeningSchema.parse(expectedOpeningJson);
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

function countsSummary(counts: Record<string, number>): string {
  return Object.entries(counts)
    .map(([label, count]) => `${count} ${humanize(label)}`)
    .join(" / ");
}

const splitSummary = countsSummary(dataset.splits.counts);
const difficultySummary = countsSummary(dataset.difficulty_strata.counts);
const calibrationCount =
  scenario.catalog.components.evaluator.calibration?.case_count ?? 0;
// The catalog states the label strings the rows carry and how many rows carry
// each. What the evaluator folds together is a property of the evaluator when
// it runs, which the manifest does not claim, so neither does this summary.
const labelSummary =
  dataset.label_shape.surface_label_count !== undefined &&
  dataset.label_shape.surface_label_count > 0
    ? `${dataset.label_shape.surface_label_count} distinct label strings across ${dataset.rows} rows`
    : humanize(dataset.label_shape.kind);
const expectedRouteSummary = `band ${expected.band} · status ${expected.status}${
  expected.status === "OK" ? " (not blocked)" : ""
} · action ${expected.recommended_action} · ${
  expected.caps.length === 0 ? "caps none" : `caps ${expected.caps.length}`
}`;
const contentOriginLabel =
  scenario.content.origin === "traigent-authored"
    ? "Traigent-authored"
    : sentenceCase(scenario.content.origin);

const customerPrompt =
  "Help me run my first Traigent optimization.\nClone https://github.com/Traigent/traigent-first-run and follow GUIDE.md.";

const guideRevision = "6ec2b9c161400cd91faea9c8cdb1c4e00d21c8d9";
const readinessEvidence = `Traigent/traigent-first-run@${guideRevision.slice(0, 8)} readiness scorer`;

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
  catalog: [
    {
      slug: scenario.slug,
      label: `Case ${scenario.legacy_id}: ${scenario.title}`,
      publication: "published",
      startingState: `${sentenceCase(scenario.catalog.starting_condition)}: the declared agent, dataset, and evaluator material are present.`,
      components: [
        `Agent (${scenario.catalog.components.agent.state}): ${scenario.catalog.components.agent.controls.length} tunable settings - ${scenario.catalog.components.agent.controls.map(humanize).join(", ")}`,
        `Dataset (${scenario.catalog.components.data.state}): ${dataset.rows} rows / ${dataset.unique_inputs} unique inputs`,
        `Evaluator (${scenario.catalog.components.evaluator.state}): ${humanize(scenario.catalog.components.evaluator.method ?? "not declared")}`,
        `Calibration material: ${calibrationCount} deterministic ${calibrationCount === 1 ? "case" : "cases"} supplied`,
      ],
      dataset: `${contentOriginLabel} content under ${scenario.content.license}; ${dataset.rows} rows (${dataset.unique_inputs} unique); ${splitSummary}; difficulty: ${difficultySummary}; ${labelSummary}. Limitations: ${dataset.limitations.map(humanize).join(", ")}. Row provenance values are the simulated user's declarations read by the readiness scorer, not source-origin claims.`,
      evaluator: `${sentenceCase(dataset.task ?? "task not declared")} with ${humanize(scenario.catalog.components.evaluator.method ?? "no evaluator method declared")}; ${calibrationCount} deterministic calibration ${calibrationCount === 1 ? "case is" : "cases are"} supplied, but no calibration execution or model accuracy is claimed.`,
      expectedRouting: `Case-specific opening contract: ${expectedRouteSummary}. Rationale: ${humanize(scenario.catalog.expected_route.rationale)}.`,
      testedLayer: `${scenario.catalog.evidence.demonstrates.map(sentenceCase).join("; ")}. No recorded coding-agent run is supplied in this release.`,
      notProven: scenario.catalog.evidence.does_not_demonstrate
        .map(sentenceCase)
        .map((value) =>
          value.replace(/\bworker\b/gi, (match) =>
            match[0] === "W" ? "Coding-agent" : "coding-agent",
          ),
        ),
    },
  ],
  slides: [
    {
      id: "ready-to-optimize",
      kind: "hero",
      eyebrow: "TRAIGENT FIRST RUN",
      title:
        "Start with the project you have. Leave with a justified next step.",
      accent: "justified next step",
      body: "The open-source guide helps a coding agent inspect what exists, preserve useful material, and choose the safest next action. Ready foundations move to baseline approval; gaps lead to a human decision, repair, or stronger evidence. When inspection identifies an evaluator path that would execute generated code or SQL, this guide run ends before candidate output executes. The starting state determines the route and ceiling - not a promised grade.",
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
      ],
    },
    {
      id: "shared-control",
      kind: "journey",
      eyebrow: "AGENT-LED, HUMAN-GOVERNED",
      title: "Five stages. Three actors. Human approval stays explicit.",
      body: "Every supported project enters Inspect. Gaps loop through a human choice, creation, repair, or review. Ready foundations move only after approval. When inspection identifies an evaluator path that would execute candidate code or SQL, this guide run ends before candidate output executes; containment and any restart are separate. The coding agent coordinates, the human governs, and Traigent runs only an approved, bounded enhanced search.",
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
        "Candidate code/SQL execution path: end this guide run before candidate output executes; containment design and any restart are separately reviewed outside the guide",
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
        "Evaluation - 35 points: checked on known-good and known-bad; right kind of check for this output; same answer every time; separates good answers from bad",
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
      ],
    },
    {
      id: "readiness-ceilings-foundations",
      kind: "matrix",
      eyebrow: "STAGE 2 OF 5 - FOUNDATION CAPS",
      title: "Broken measurement sets the lowest ceilings.",
      body: "A cap is a ceiling on the total score out of 100 - the maximum the evidence allows, applied after the three weighted areas are summed; it is not a deduction. The ready row matches the worked example; the other rows are shipped scorer rules whose example scenarios are planned; not yet published.",
      bullets: [],
      metrics: [],
      steps: [],
      matrix: [
        {
          startingPoint: "Agent, data, and evaluator are usable; no cap fires",
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
          startingPoint:
            "The evaluator is unvalidated, or nothing in the agent varies",
          safestNextStep:
            "Ceiling 45; validate the evaluator or wire a setting worth searching",
          coverage: "coverage-target",
        },
      ],
      evidenceState: "guide-contract",
      sourceRevision: guideRevision,
      evidence: [readinessEvidence],
      notes: [
        "A capped project is not a failed project. A truthful 65 with visible limits is more useful than an unsupported 90.",
        "Only the ready-reference route has a downloadable scenario here. Do not say the other rows passed a public scenario test.",
      ],
    },
    {
      id: "readiness-ceilings-evidence",
      kind: "matrix",
      eyebrow: "STAGE 2 OF 5 - EVIDENCE CAPS",
      title: "Generated data still runs - it only caps the top score.",
      body: "Nothing stops here: the run continues end to end. Rows declared as generated, or an answer key written by a model, only cap how high the score can go until real rows arrive - a caveat for the summary, not a blocker.",
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
          startingPoint:
            "Rows are declared real, but a model generated the answer key",
          safestNextStep:
            "Ceiling 74; compare cautiously and obtain human review before trusting the margin",
          coverage: "coverage-target",
        },
      ],
      evidenceState: "guide-contract",
      sourceRevision: guideRevision,
      evidence: [readinessEvidence],
      notes: [
        "A fully generated dataset caps at 65, so STRONG and EXCELLENT are arithmetically unreachable until the evidence changes.",
        "These caps read the fictional user's row declarations. Repository authorship is a separate contract: case 46 is Traigent-authored synthetic content whose in-world provenance values simulate a user declaration.",
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
        "The published scenario declares separate tuning and holdout pools",
      ],
      notes: [
        "Case 46 declares 100 tuning and 20 holdout rows. That is the public dataset inventory, not a claim that every paid first run uses all 120 rows; the run plan must record the selected row IDs and any bounded subset.",
        "Selecting the best of several configurations on the same tuning rows partly selects sample noise. Held-out scoring checks that risk; it does not eliminate it or prove generalization.",
        "When the coding agent has seen or authored the reserved rows, the guide calls the result held-back and non-blind - kept out of tuning but not hidden from the agent - rather than a sealed holdout.",
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
      title: "Anyone can re-run the example and check the result themselves.",
      body: "A fresh coding-agent session receives a clean copy of the customer-shaped project, including its evaluator, plus the guide and handoff. The scenario verifier, expected result, and previous outputs stay outside that session's assigned context.",
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
      body: `Every test scenario ships purpose-written synthetic data - authored for the test, never customer material - so runs are reproducible and safe to share. The example's rows are ${contentOriginLabel}, licensed under ${scenario.content.license}; no upstream dataset license travels with them, so you may run, copy and adapt the material under that license. The worked example shows the pattern; future scenarios will start from broken states on purpose.`,
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
      ],
    },
    {
      id: "case-46",
      kind: "evidence",
      eyebrow: "A WORKED EXAMPLE",
      title:
        "One excellent-readiness scenario: incident severity triage (scenario 46).",
      body: "A complete, known-good starting point: agent, labeled data, and evaluator all present, so its expected readiness grade is Excellent from the start. It exists to prove the whole flow end to end - the number 46 is just its catalog ID. Its expected result is specific to this scenario, not a score promised to other projects.",
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
        "Case 46 is a stable numeric alias for incident-severity-triage. It does not mean 46 scenarios are published here.",
        'If a prospect asks "will we get Excellent?", the honest answer is: show me your data, your evaluator, and whether anything in your agent varies - those three set your ceiling before we run anything.',
        `The ${dataset.rows} incident reports are Traigent-authored synthetic data under ${scenario.content.license}; they contain no customer or third-party dataset.`,
      ],
    },
    {
      id: "test-layers",
      kind: "matrix",
      eyebrow: "THREE DIFFERENT CHECKS",
      title: "Three checks, three different proofs.",
      body: "Passing one check proves only that check - never the next one. Today this repository ships the scenario files and the expected result to compare against; no recorded agent run is included yet. Nothing here requires a prior run: anyone can run all three from a fresh clone - the paid layer with their own approved keys and spend.",
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
        "Two ways to try it today: run the example, or point the guide at your project.",
      accent: "run the example",
      body: "The two paths are independent, and neither needs any prior run. Trying the example is not a prerequisite for using the guide on a real project, and neither path authorizes later paid work - provider calls, Traigent service use, and spend each need their own approval.",
      bullets: [
        "Try the example: check and prepare the example scenario; give a fresh coding agent only the printed instructions",
        "Then verify: save the readiness answer the agent produced and compare it with the expected result that ships in this repository",
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
        "The two available paths are alternatives: audit the public scenario, or try the guide on the customer's own project.",
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
      body: "The guide routes every condition below toward optimization, creating or repairing what is missing with the user's approval - every route works today. The next slide shows one worked example: a project that starts ready. The same flow carries a broken or half-ready project to the same finish line.",
      bullets: [
        "Ready → explain readiness; stop at baseline approval",
        "Missing or invalid material → preserve, resolve the human choice, create or repair, then re-check",
        "Weak evidence → bound the demonstration or request stronger material",
        "Evaluator unvalidated, invalid, or timing out → calibrate, repair or replace, or, on a timeout, ask the human how to proceed",
        "Unsafe execution path identified → end this guide run before candidate output executes",
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
        "Only case 46 is downloadable here today. The other routes ship in the guide, but their public context-isolated scenario tests are roadmap items.",
      ],
    },
    {
      id: "coverage-roadmap-material",
      kind: "matrix",
      eyebrow: "APPENDIX - TEST SCENARIO ROADMAP 1 OF 2",
      title: "Material and evidence routes remain separate test families.",
      body: "These are roadmap themes for future test scenarios - the routes themselves already work in the guide today. A theme can need multiple cases; publishing one case does not cover its whole theme.",
      bullets: [],
      metrics: [],
      steps: [],
      scenarioMatrix: [
        {
          family: "Ready reference",
          setup: `${dataset.rows} labeled synthetic incident reports (${splitSummary}); usable tunable settings; deterministic non-executing evaluator`,
          expectedRoute:
            "Recognize that the components are ready, explain the opening, and stop at baseline approval",
          coverage: "published",
        },
        {
          family: "Missing material",
          setup:
            "Agent, dataset, expected outputs, or evaluator absent while other customer material may still be usable",
          expectedRoute:
            "Preserve what exists; ask only for an unresolved human or domain choice; create or repair a required dependency; re-check before paid work",
          coverage: "coverage-target",
        },
        {
          family: "Dataset integrity",
          setup:
            "Malformed rows; missing answer labels; empty or overlapping tuning/held-out splits; duplicate rows leaking between them",
          expectedRoute:
            "Repair invalid comparison material; do not optimize against a split or answer key that cannot support the claim",
          coverage: "coverage-target",
        },
        {
          family: "Evidence strength",
          setup:
            "Small, synthetic, undeclared, or mixed-provenance rows; model-generated answer keys; small comparison sets, or coarse pass/fail-style outcomes",
          expectedRoute:
            "Label a bounded demonstration honestly, ask for human review where required, and limit the claim",
          coverage: "coverage-target",
        },
      ],
      evidenceState: "guide-contract",
      sourceRevision: guideRevision,
      evidence: [
        `Route contracts in Traigent/traigent-first-run@${guideRevision.slice(0, 8)}; scenario status in this repository`,
      ],
      notes: [
        "Ready reference is the only public scenario today. Every other row is a planned public scenario test, not a passed result.",
        "Repository origin and the fictional row provenance declarations are different facts; case 46 is Traigent-authored synthetic content.",
      ],
    },
    {
      id: "coverage-roadmap-gates",
      kind: "matrix",
      eyebrow: "APPENDIX - TEST SCENARIO ROADMAP 2 OF 2",
      title:
        "Evaluator, execution, and search-space gates need distinct tests.",
      body: "These roadmap themes can require multiple cases because their conditions lead to materially different actions. A repair route, a human timeout choice, and a hard safety stop must not be presented as the same tested behavior. As on the previous slide, these are public scenario-test themes, not additional product capability: each gate below ships in the guide today, and what is planned is the public case that lets you reproduce it.",
      bullets: [],
      metrics: [],
      steps: [],
      scenarioMatrix: [
        {
          family: "Evaluator quality",
          setup:
            "A present evaluator is unvalidated, opaque, inconsistent, invalid on known cases, or timing out",
          expectedRoute:
            "Calibrate, repair, or replace it; on a timeout, ask the human one bounded question - never call a slow evaluator broken",
          coverage: "coverage-target",
        },
        {
          family: "Execution safety",
          setup:
            "Inspection identifies a resolved path that would execute or import candidate code or SQL, shell out with it, or submit it to an execution engine",
          expectedRoute:
            "End this guide run before candidate output executes; containment design and any restart are separately human-governed",
          coverage: "coverage-target",
        },
        {
          family: "Search-space readiness",
          setup:
            "The agent has no meaningful varying tunable setting, or a declared setting is not wired into requests",
          expectedRoute:
            "Establish and locally verify real request variation before requesting approval for paid search",
          coverage: "coverage-target",
        },
      ],
      evidenceState: "guide-contract",
      sourceRevision: guideRevision,
      evidence: [
        `Route contracts in Traigent/traigent-first-run@${guideRevision.slice(0, 8)}; test scenarios planned`,
      ],
      notes: [
        "An evaluator timeout is not proof that the evaluator is broken. The guide presents a bounded human choice rather than silently changing the limit.",
        "The guide's offline isolated behavioral suite exercises the execution-safety stop contract without executing candidate output. That is a code/contract test, not a public coding-agent scenario run.",
        "The guide supplies neither containment design nor an automatic restart after the execution-safety stop.",
      ],
    },
    {
      id: "published-scenario-catalog",
      kind: "catalog",
      eyebrow: "SCENARIO CATALOG APPENDIX",
      title: "One scenario is released today, with its boundaries visible.",
      body: "The catalog records what each published test represents, what route it expects, and what it does not prove. New entries can be added without turning coverage targets into pass claims.",
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
        "This appendix answers what the published scenario actually contains.",
        "Synthetic describes repository origin. The row value provenance: real is simulated scorer metadata inside the scenario.",
        "Nothing here is observed accuracy or evidence of a live optimization.",
        `Calibration is a sample by design: ${calibrationCount} ${calibrationCount === 1 ? "case carries" : "cases carry"} four probes each - a correct answer, an equivalent answer spelled differently, a near-miss and a wrong one. That asks whether the scorer agrees with itself, which is a property of the scorer rather than of the row count, so running it over all ${dataset.rows} rows would cost more and would not change what the probes already establish. Where inputs are expensive - long documents in, prose out - a handful of probes is the only practical check, and it is sound for the same reason.`,
      ],
    },
    {
      id: "published-scenario-data",
      kind: "catalog",
      eyebrow: "SCENARIO CATALOG APPENDIX",
      title: "Synthetic origin and evaluation limits stay explicit.",
      body: "The published scenario makes data shape, evaluator behavior, expected routing, and unsupported claims visible without presenting synthetic rows as customer evidence.",
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
  "coverage-roadmap-material",
  "coverage-roadmap-gates",
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
export const presentation = parsePresentation({
  ...rawPresentation,
  slides: [...coreSlides, ...appendixSlides],
});
export { customerPrompt };
