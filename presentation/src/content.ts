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
      body: "The public guide helps a coding agent inspect what exists, preserve useful material, and choose the safest next action. Ready foundations move to baseline approval; gaps lead to a human decision, repair, or stronger evidence. When inspection identifies an evaluator path that would execute generated code or SQL, this guide run ends before candidate output executes. The starting state determines the route and ceiling - not a promised grade.",
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
        "The coding agent inspects and prepares. The human owns domain choices and approvals. The Traigent service is used only later for an explicitly approved managed search.",
        'Talk track: the deliverable of the first run is a truthful position and a next step, not a score. A project told "your evaluator is broken, fix it first" would still have received a useful answer without a paid optimization.',
      ],
    },
    {
      id: "shared-control",
      kind: "journey",
      eyebrow: "AGENT-LED, HUMAN-GOVERNED",
      title: "Five stages. Three actors. Human approval stays explicit.",
      body: "Every supported project enters Inspect. Gaps loop through a human choice, creation, repair, or review. Ready foundations move only after approval. When inspection identifies an evaluator path that would execute candidate code or SQL, this guide run ends before candidate output executes; containment and any restart are separate. The coding agent coordinates, the human governs, and Traigent executes only an approved managed search.",
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
            "Score evidence, apply evidence ceilings (caps), and explain the safest next route. Stop before paid work when the evaluator cannot tell good from bad answers.",
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
        "Stage 4 is a separate approval from stage 3 on purpose: the baseline preserves the user's existing local space, or uses the guide's fixed 12-configuration grid only when a baseline is missing; managed optimization is the broader search.",
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
      body: "The coding agent evaluates the agent, dataset, and evaluator. It may run an evaluator only after static inspection admits that exact local, side-effect-free path and identifies no candidate-code or SQL execution. It then applies evidence ceilings and names the shortest justified next action.",
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
      body: "Readiness groups 14 checks into three weighted pillars. Dataset carries the most weight because an optimization cannot outrun the material it is measured on. The readiness scorer itself makes no model-provider or Traigent-service calls.",
      bullets: [
        "Dataset - 40 points: answers to score against; examples to compare on; range of difficulty; repeated or dominant answers; where the rows came from",
        "Evaluation - 35 points: checked on known-good and known-bad; right kind of check for this output; same answer every time; separates good answers from bad",
        "Agent - 25 points: settings-combinations to try; what the model is told and shown; whether the answer shape is pinned down; whether the agent is guaranteed to stop, and what stops it; tools it declares and can reach",
        "Bands: NOT READY 0-29; PARTIAL 30-54; WORKABLE 55-74; STRONG 75-89; EXCELLENT 90-100",
        "Thin-evidence rule: below 0.75 confidence overall or in any pillar, a score that would land STRONG or EXCELLENT is held at WORKABLE; lower bands are unchanged",
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
      body: "A cap is the highest overall score a specific evidence condition permits, not a deduction. Only the ready row has a complete public scenario here - case 46. The other rows are published scorer rules whose public scenario tests are planned.",
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
      title: "Generated evidence limits the claim before paid work.",
      body: "The scorer reads the user's declared row provenance and answer-key origin. Those in-project declarations set a ceiling; they are separate from who authored the public scenario files.",
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
        "A user-owned baseline keeps its exact configuration space, row count, and how it selects rows and configurations; it is never padded or weakened for the walkthrough",
        "Only a missing baseline gets the guide's generated 12-configuration local grid",
        "The run records quality plus available cost and latency evidence for that exact setup",
        "Provider errors, missing credentials, or cost-boundary failures stop loudly; access is never invented",
        "Stage output: the saved baseline result and a separate decision on whether managed search is justified",
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
      ],
    },
    {
      id: "stage-optimize",
      kind: "statement",
      eyebrow: "STAGE 4 OF 5 - OPTIMIZE",
      title: "Search only the space the customer understands and approves.",
      body: "Managed Traigent search starts under its own approval after the baseline. The coding agent submits the bounded configuration space, monitors the declared limits, and keeps the baseline result unchanged as the reference every candidate is compared against. The aim is a configuration that beats the preserved baseline on the approved objectives, within the approved space and spend; finding none is a reported outcome, not a failure.",
      bullets: [
        "Human separately approves Traigent access, provider use, data movement, the trial bound (maximum number of configurations tested), and spend",
        "Only tunable settings proven to change the request actually sent to the model belong in the search space",
        "The search compares configurations against the same dataset and evaluator contract",
        "Credential, service, provider, or budget failures stop; no mock or random result replaces them",
        "Stage output: the exact search space submitted, every configuration tested, and its measured scores",
      ],
      metrics: [],
      steps: [],
      evidenceState: "guide-contract",
      sourceRevision: guideRevision,
      evidence: [
        `Optimization-stage contract at Traigent/traigent-first-run@${guideRevision.slice(0, 8)}; no managed run supplied`,
      ],
      notes: [
        "Baseline approval does not pre-authorize optimization. The second gate is deliberate because the number of calls and the data boundary can change.",
      ],
    },
    {
      id: "case-46-search-space",
      kind: "evidence",
      eyebrow: "CASE 46 - THE FOUR TUNABLE SETTINGS",
      title:
        "Four declared tunable settings create 54 candidate configurations.",
      body: "That multiplication describes case 46's static settings inventory. It is not a recorded paid run and does not establish the final approved search space, how many configurations a later run would submit, or what Traigent would test.",
      bullets: [],
      metrics: [
        {
          label: "Which model",
          value: "3",
          detail: "gpt-4o-mini, gpt-4o, claude-3-5-haiku-latest",
          tone: "blue",
        },
        {
          label: "How it is asked",
          value: "3",
          detail: "plain, step_by_step, rubric",
          tone: "violet",
        },
        {
          label: "Past context",
          value: "3",
          detail: "0, 2, or 4 earlier incidents",
          tone: "blue",
        },
        {
          label: "Answer shape",
          value: "2",
          detail: "label or JSON",
          tone: "violet",
        },
      ],
      steps: [],
      evidenceState: "scenario-contract",
      evidence: ["scenarios/incident-severity-triage/project/agent.py"],
      notes: [
        "Say the multiplication aloud: three models x three prompt styles x three retrieval depths x two output formats = 54 possible configurations.",
        "The model control spans OpenAI and Anthropic in this public simulation. Do not claim current prices; no price evidence is bundled here.",
        "The code defaults are gpt-4o-mini, plain, retrieval 0, and label. Those defaults describe one initial configuration, not proof that a customer's preserved baseline has only one row.",
        "The managed first-run search chooses which configurations to try as it goes, from a materially larger space than the baseline grid",
      ],
    },
    {
      id: "selection-and-heldout",
      kind: "journey",
      eyebrow: "STAGES 3 TO 5 - HONEST COMPARISON",
      title:
        "Choose on tuning evidence; check one recommendation on held-out rows.",
      body: "The baseline and managed run use the same tuning data, evaluator, objectives, and agent path. A recommendation is selected from tuning evidence across both runs. Only that locked recommendation is then scored on held-out rows, which check it but never choose it.",
      bullets: [],
      metrics: [],
      steps: [
        {
          label: "Measure the baseline",
          detail:
            "Preserve the user's existing local baseline exactly, or use the guide's 12-configuration default only when missing; any reduction from that target is disclosed and approved first.",
          executor: "Coding agent",
          humanGate: "Human approves provider spend",
        },
        {
          label: "Run managed search",
          detail:
            "Traigent tests up to 12 configurations from the approved larger space, using the same tuning rows and evaluator.",
          executor: "Traigent service",
          humanGate: "Human separately approves",
        },
        {
          label: "Lock one recommendation",
          detail:
            "Compare baseline and managed-search tuning evidence; include the accuracy-versus-cost trade-off (the frontier) when cost is measured; then select without reading held-out scores.",
          executor: "Coding agent",
        },
        {
          label: "Check held-out rows once",
          detail:
            "Score only the locked recommendation on rows no candidate search evaluated; disclose the result and its sample-size limit.",
          executor: "Coding agent",
          humanGate: "Human reviews evidence",
        },
      ],
      evidenceState: "guide-contract",
      sourceRevision: guideRevision,
      evidence: [
        `Traigent/traigent-first-run@${guideRevision.slice(0, 8)} comparison contract`,
        "Case 46 declares separate tuning and holdout pools",
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
      eyebrow: "PUBLIC AND REPRODUCIBLE",
      title: "The scenario is public. The individual run is context-isolated.",
      body: "A fresh coding-agent session receives a clean copy of the customer-shaped project, including its evaluator, plus the guide and handoff. The scenario verifier, expected result, and previous outputs stay outside that session's assigned context.",
      bullets: [
        "Anyone can inspect and reproduce the scenario",
        "The coding-agent session is not given the expected result or the verifier kept by the test operator",
        "Public means inspectable; we do not claim the expected answers are hidden from someone who deliberately looks them up",
      ],
      metrics: [],
      steps: [],
      evidenceState: "scenario-contract",
      evidence: ["Public scenario isolation methodology"],
      notes: [
        "Customer language: public means inspectable; context-isolated means the coding-agent session does not receive the expected answer.",
      ],
    },
    {
      id: "dataset-origin",
      kind: "statement",
      eyebrow: "DATASET ORIGIN - CASE 46",
      title:
        "Synthetic test data is useful when its origin and limits stay visible.",
      body: `The published case-46 material is ${contentOriginLabel}, licensed under ${scenario.content.license}, and contains no customer or third-party dataset. It is designed to exercise readiness routing reproducibly, not to stand in for production evidence.`,
      bullets: [
        `${dataset.rows} authored incident reports and ${dataset.unique_inputs} unique inputs; the declared pool is ${splitSummary}`,
        `Even difficulty coverage: ${difficultySummary}, so the public pool does not win its score by concentrating only on easy cases`,
        `Output shape: ${labelSummary}; the shipped evaluator resolves equivalent spellings before comparison, which is evaluator behaviour rather than a validated catalog claim`,
        "A row value such as provenance: real is fictional user-declared scorer input, not a statement about where the repository file came from",
        "The scenario and expected result are public for inspection; the fresh coding-agent session receives neither the expected result nor the operator-kept verifier",
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
      eyebrow: "ONE PUBLIC READY-REFERENCE TODAY",
      title: "One public ready-reference: incident severity triage.",
      body: `Case 46 is a complete, known-good starting point for the ready-components route. Its ${dataset.rows} incident reports are Traigent-authored synthetic data under ${scenario.content.license}; they contain no customer or third-party dataset. Its expected opening is case-specific, not a score promised to other projects.`,
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
      ],
    },
    {
      id: "repository-map",
      kind: "statement",
      eyebrow: "REPOSITORY ORGANIZATION",
      title:
        "Each public scenario is complete, inspectable, and independently resettable.",
      body: "The repository keeps customer-shaped project files, operator-side expectations, methodology, and presentation tooling in explicit locations. Scenarios are not assembled from hidden fragments, and another repository's Git history is not carried into this one.",
      bullets: [
        "scenarios/<slug>/project: files copied into the fresh coding-agent session",
        "scenarios/<slug>/scenario.json: identity, component state, dataset facts, expected route, and evidence limits",
        "scenarios/<slug>/verifier: the test operator's expected-result contract (what the run should conclude); never copied into the session's project",
        "scenario.py: list, show, check, prepare, and verify without importing scenario code",
        "docs and GUIDE.md: evidence model plus customer-PC operating procedure",
        "presentation: one validated content source rendered as browser HTML and editable PowerPoint",
      ],
      metrics: [],
      steps: [],
      evidenceState: "scenario-contract",
      evidence: ["Published repository layout and CLI contract"],
      notes: [
        "A new public scenario must carry its own project, manifest, and verifier contract. Shared authoring helpers may reduce maintenance, but a run must never depend on selectively assembled hidden fixture fragments.",
      ],
    },
    {
      id: "expected-opening",
      kind: "statement",
      eyebrow: "CASE-SPECIFIC EXPECTED RESULT",
      title: "Case 46 expects 92/100 and no caps. That is not a promise.",
      body: "An opening is the readiness answer before any paid work. The band summarizes the starting point, the action names the next route, and each cap is a maximum. Confidence means the share of applicable check weight the scorer could measure - not statistical certainty.",
      bullets: [
        `Expected here: ${expectedRouteSummary}`,
        `Expected score ${expected.display.overall.score}/100 with ${expected.display.overall.confidence.toFixed(2)} overall confidence; weakest pillar confidence ${Math.min(...Object.values(expected.display.pillars).map((pillar) => pillar.confidence)).toFixed(2)}`,
        "No cap fires here; another project's material can set a lower ceiling or a different route",
        "Published expectation only: no captured coding-agent run, baseline, or optimization result",
      ],
      metrics: [],
      steps: [],
      evidenceState: "scenario-contract",
      evidence: ["Published case-46 expected opening contract"],
      notes: [
        'If a prospect asks "will we get Excellent?", the honest answer is: show me your data, your evaluator, and whether anything in your agent varies - those three set your ceiling before we run anything.',
        "Do not sell the band. Sell the routing: the value is being told where you are and what to fix before calls or spend with the customer's project-model provider or Traigent service. The coding-agent service may itself be remote and billed.",
        "The expected result is specific to this public scenario, not a benchmark other projects are measured against.",
      ],
    },
    {
      id: "test-layers",
      kind: "matrix",
      eyebrow: "THREE DIFFERENT CHECKS",
      title: "Each test layer supports a different claim.",
      body: "A pass at one layer never stands in for the next. This release supplies the case-46 package and expected contract only; it does not include a captured Phase A or Phase B run.",
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
          layer: "Phase A",
          action: "Fresh coding-agent session performs Inspect and Readiness",
          passSupports:
            "Captured readiness matched the public contract in that recorded run",
          doesNotProve: "Paid baseline or optimization",
        },
        {
          layer: "Phase B",
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
      ],
    },
    {
      id: "prepare-and-verify",
      kind: "journey",
      eyebrow: "REPRODUCE ON A CUSTOMER PC",
      title: "One safe preparation flow, one independent result check.",
      body: "Start at https://github.com/Traigent/traigent-first-run-scenarios and follow docs/customer-pc-runbook.md. The CLI creates a disposable project copy without verifier material; the test operator then checks saved readiness JSON against the contract and scenario revision in run.json.",
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
      evidence: ["Public scenario CLI and customer-PC runbook"],
      notes: [
        "The public verifier remains with the test operator, outside the coding agent's project copy.",
      ],
    },
    {
      id: "trust-boundary",
      kind: "statement",
      eyebrow: "VISIBLE HUMAN CONTROL",
      title:
        "A Phase A opening covers inspection and readiness behavior only; it says nothing about managed optimization.",
      body: "Credentials, project-provider or Traigent paid calls, additional data egress, installation, mutation, and optimization remain separate approval gates. A Phase A result does not authorize Phase B.",
      bullets: [
        "Phase A stops at the first material human decision",
        "Access codes and API keys belong to separately approved Phase B",
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
      title: "Choose the evidence path before you start.",
      accent: "evidence path",
      body: "The two paths are independent, with different instructions and evidence. Auditing case 46 is not a prerequisite for using the guide on a real project, and neither path pre-authorizes later baseline or optimization work, provider calls, Traigent service use, or spend.",
      bullets: [
        "Public-scenario audit: check and prepare case 46; give a fresh coding agent only the printed instructions",
        "Audit verification: save the machine-readable readiness answer; compare it with the published expected result identified in the run metadata",
        "Real-project inspection: paste the public clone prompt into the coding agent already working in the repository",
        "Shared boundary: neither path authorizes later provider calls, Traigent service use, managed search, or spend",
        "After a first result, the guide offers the public SDK skills: npx skills add Traigent/traigent-skills --list",
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
      body: "The public guide defines the route for each supported condition below. This repository publishes one context-isolated scenario today: the ready reference, case 46. Public scenario tests for the other routes are planned, not passed.",
      bullets: [
        "Ready → explain readiness; stop at baseline approval (public case 46)",
        "Missing or invalid material → preserve, resolve the human choice, create or repair, then re-check",
        "Weak evidence → bound the demonstration or request stronger material",
        "Evaluator unvalidated, invalid, or timing out → calibrate, repair or replace, or ask the bounded timeout choice",
        "Unsafe execution path identified → end this guide run before candidate output executes",
        "No meaningful request variation → wire and locally prove a tunable setting",
      ],
      metrics: [],
      steps: [],
      evidenceState: "guide-contract",
      sourceRevision: guideRevision,
      evidence: [
        `Route contracts in Traigent/traigent-first-run@${guideRevision.slice(0, 8)}; one public scenario in this repository`,
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
      eyebrow: "APPENDIX - PUBLIC SCENARIO ROADMAP 1 OF 2",
      title: "Material and evidence routes remain separate test families.",
      body: "These are public scenario-test roadmap themes, not additional product capability and not passed runs. A theme can need multiple cases or subcases; passing one case does not pass the theme.",
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
            "Malformed or unknown row shapes; missing labels; empty or overlapping splits; duplicates or leakage",
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
      eyebrow: "APPENDIX - PUBLIC SCENARIO ROADMAP 2 OF 2",
      title:
        "Evaluator, execution, and search-space gates need distinct tests.",
      body: "These roadmap themes can require multiple cases because their conditions lead to materially different actions. A repair route, a human timeout choice, and a hard safety stop must not be presented as the same tested behavior.",
      bullets: [],
      metrics: [],
      steps: [],
      scenarioMatrix: [
        {
          family: "Evaluator quality",
          setup:
            "A present evaluator is unvalidated, opaque, inconsistent, invalid on known cases, or timing out",
          expectedRoute:
            "Calibrate it, inspect and repair or replace it, or pause for a bounded timeout decision; never call a slow evaluator broken",
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
        `Route contracts in Traigent/traigent-first-run@${guideRevision.slice(0, 8)}; public scenario tests planned`,
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
      eyebrow: "PUBLIC CATALOG APPENDIX",
      title: "One scenario is released today, with its boundaries visible.",
      body: "The catalog records what each public test represents, what route it expects, and what it does not prove. New entries can be added without turning coverage targets into pass claims.",
      bullets: [],
      metrics: [],
      steps: [],
      catalogView: "setup-and-route",
      catalogSlug: scenario.slug,
      evidenceState: "scenario-contract",
      evidence: [
        "scenarios/incident-severity-triage/scenario.json",
        "Published case-46 dataset and expected opening contract",
      ],
      notes: [
        "This appendix answers what the published scenario actually contains.",
        "Synthetic describes repository origin. The row value provenance: real is simulated scorer metadata inside the scenario.",
        "Nothing here is observed accuracy or evidence of a live optimization.",
      ],
    },
    {
      id: "published-scenario-data",
      kind: "catalog",
      eyebrow: "PUBLIC CATALOG APPENDIX",
      title: "Synthetic origin and evaluation limits stay explicit.",
      body: "Case 46 makes data shape, evaluator behavior, expected routing, and unsupported claims visible without presenting synthetic rows as customer evidence.",
      bullets: [],
      metrics: [],
      steps: [],
      catalogView: "data-and-limits",
      catalogSlug: scenario.slug,
      evidenceState: "scenario-contract",
      evidence: [
        "scenarios/incident-severity-triage/scenario.json",
        "Published case-46 dataset and expected opening contract",
      ],
      notes: [
        `${dataset.unique_inputs} unique inputs; ${splitSummary}; difficulty: ${difficultySummary}.`,
        `${labelSummary} before deterministic exact/binary scoring.`,
        "Repository origin is Traigent-authored synthetic; provenance: real is simulated row metadata for the readiness scorer.",
      ],
    },
    {
      id: "choose-next-step",
      kind: "hero",
      eyebrow: "A CONTROLLED FIRST MOVE",
      title: "Reproduce what is public. Then decide what to authorize.",
      accent: "decide what to authorize",
      body: "Audit case 46 for transparency, or bring the first-run guide to a real project for inspection. Baseline and optimization remain explicit later decisions.",
      bullets: [],
      metrics: [],
      steps: [],
      evidenceState: "not-demonstrated",
      evidence: ["Customer chooses audit, real-project inspection, or neither"],
      notes: [
        "The close is a choice: reproduce the public contract or inspect a real project; neither path pre-approves paid work.",
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
  "next-step",
  "test-layers",
  "prepare-and-verify",
  "trust-boundary",
  "choose-next-step",
] as const;

const appendixSlideIds = [
  "stage-inspect",
  "stage-readiness",
  "readiness-scoring",
  "readiness-ceilings-foundations",
  "readiness-ceilings-evidence",
  "expected-opening",
  "stage-baseline",
  "stage-optimize",
  "case-46-search-space",
  "selection-and-heldout",
  "stage-results",
  "credible-reproduction",
  "dataset-origin",
  "repository-map",
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
