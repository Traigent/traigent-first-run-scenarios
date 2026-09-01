import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import {
  copyFile,
  lstat,
  mkdir,
  open,
  readFile,
  readdir,
  realpath,
  rename,
  rm,
  stat,
  writeFile,
} from "node:fs/promises";
import path from "node:path";

import {
  createScanner,
  LanguageVariant,
  SyntaxKind,
} from "typescript/unstable/ast";

import { presentation } from "../src/content";
import type { PresentationSpec } from "../src/model";
import { defaultPptxPath } from "./build-pptx";
import { HtmlParseError, readHtml, type HtmlElement } from "./html";
import { findNetworkTargets, findSourceCapabilities } from "./javascript";
import {
  distRoot,
  isMainModule,
  presentationRoot,
  repositoryRoot,
} from "./runtime";
import { validatePresentationContent } from "./validate-content";

const BUNDLE_DIRECTORY_NAME = "customer-bundle";
const HTML_FILE_NAME = "presentation.html";
const POWERPOINT_FILE_NAME = "presentation.pptx";
const MANIFEST_FILE_NAME = "build-manifest.json";
const CHECKSUMS_FILE_NAME = "checksums.txt";
const NOTICES_FILE_NAME = "THIRD_PARTY_NOTICES.txt";
const REPOSITORY_LICENSE_FILE_NAME = "LICENSE";
const REPOSITORY_NOTICE_FILE_NAME = "NOTICE";
// Every file under the presentation source tree is classified, and an
// extension this scanner does not know is an error rather than a file it
// quietly walks past. An allow-list of two extensions made a `.js` module - or
// the same TypeScript file named `.TS` - invisible to the offline scan while
// the bundler still compiled it into the customer artifact.
const SCRIPT_EXTENSIONS = new Set([
  ".cjs",
  ".cts",
  ".js",
  ".jsx",
  ".mjs",
  ".mts",
  ".ts",
  ".tsx",
]);
const STYLE_EXTENSIONS = new Set([".css"]);
const MARKUP_EXTENSIONS = new Set([".svg"]);
// Files a bundler can inline but that carry no behavior of their own. They are
// recorded so the walk stays complete, and are not scanned for code.
const INERT_EXTENSIONS = new Set([
  ".avif",
  ".gif",
  ".ico",
  ".jpeg",
  ".jpg",
  ".json",
  ".jsonl",
  ".md",
  ".otf",
  ".png",
  ".ttf",
  ".txt",
  ".webp",
  ".woff",
  ".woff2",
]);
// Editor and file-manager droppings that no bundler resolves.
const IGNORED_FILE_NAMES = new Set([
  ".DS_Store",
  ".gitignore",
  ".gitkeep",
  ".npmignore",
  "Thumbs.db",
]);
// Extensions a bare module specifier may be spelled without.
const MODULE_RESOLUTION_EXTENSIONS = [
  ".ts",
  ".tsx",
  ".mts",
  ".cts",
  ".js",
  ".jsx",
  ".mjs",
  ".cjs",
  ".json",
  ".css",
  ".svg",
];

type SourceFileKind = "script" | "style" | "markup" | "inert";

interface ClassifiedSourceFile {
  readonly path: string;
  readonly kind: SourceFileKind;
}

const FORBIDDEN_SOURCE_PATTERNS = [
  { label: "dangerouslySetInnerHTML", pattern: /\bdangerouslySetInnerHTML\b/ },
  { label: "eval", pattern: /\beval\s*\(/ },
  { label: "Function constructor", pattern: /\bnew\s+Function\s*\(/ },
  { label: "fetch", pattern: /\bfetch\b/ },
  { label: "XMLHttpRequest", pattern: /\bXMLHttpRequest\b/ },
  { label: "WebSocket", pattern: /\bWebSocket\b/ },
  { label: "EventSource", pattern: /\bEventSource\b/ },
  { label: "sendBeacon", pattern: /\bsendBeacon\b/ },
  {
    label: "remote module import",
    pattern: /(?:from\s*|import\s*\()\s*["'](?:https?:)?\/\//i,
  },
] as const;

interface ExternalReferenceRule {
  readonly label: string;
  readonly elements: readonly string[];
  // Attributes whose value the browser requests. Omitted when the element is
  // itself an external surface and is refused on sight.
  readonly attributes?: readonly string[];
  // Whether an inline `data:` payload or a same-document fragment is a
  // self-contained answer for this attribute.
  readonly allowsInlineValue?: boolean;
}

// A reference is decided from the parsed markup: which element carries which
// attribute. Searching the serialized document for the same shapes made deck
// copy that quotes a tag fail the gate, and could not see a reference an
// unusual but valid serialization wrote differently.
const EXTERNAL_REFERENCE_RULES: readonly ExternalReferenceRule[] = [
  { label: "external script", elements: ["script"], attributes: ["src"] },
  {
    label: "external link resource",
    elements: ["link"],
    attributes: ["href"],
    allowsInlineValue: true,
  },
  { label: "base URL", elements: ["base"], attributes: ["href"] },
  {
    label: "embedded active resource",
    elements: ["iframe", "object", "embed", "frame", "frameset", "portal"],
  },
  {
    label: "background image",
    elements: ["body", "table", "td", "th", "tr"],
    attributes: ["background"],
    allowsInlineValue: true,
  },
  {
    label: "external media source",
    elements: ["img", "source", "video", "audio", "track", "input"],
    attributes: ["src"],
    allowsInlineValue: true,
  },
  {
    label: "responsive media source",
    elements: ["img", "source"],
    attributes: ["srcset"],
  },
  {
    label: "external video poster",
    elements: ["video"],
    attributes: ["poster"],
    allowsInlineValue: true,
  },
  {
    label: "external SVG resource",
    elements: ["image", "use"],
    attributes: ["href", "xlink:href"],
    allowsInlineValue: true,
  },
  {
    label: "form submission target",
    elements: ["form", "button", "input"],
    attributes: ["action", "formaction"],
  },
  { label: "hyperlink beacon", elements: ["a"], attributes: ["ping"] },
  {
    label: "application cache manifest",
    elements: ["html"],
    attributes: ["manifest"],
  },
] as const;

// Script content of these types is not JavaScript, so it is inert markup or
// data rather than code the browser will run. An import map and a speculation
// rules block are deliberately absent: both exist to name resources the
// browser should load, so neither is inert.
const NON_JAVASCRIPT_SCRIPT_TYPES = new Set([
  "application/json",
  "application/ld+json",
  "text/plain",
  "text/template",
]);

// Script types whose whole purpose is to point the browser at other
// resources. A single-file deck has nothing to point at.
const RESOURCE_DIRECTING_SCRIPT_TYPES = new Set([
  "importmap",
  "speculationrules",
]);

const EXTERNAL_CSS_RESOURCE_PATTERN =
  /\burl\(\s*["']?(?!data:|#)[^)"']+|@import\s+(?:url\(\s*)?["']?(?!data:|#)[^\s;"')]+/i;

interface LockPackage {
  version?: unknown;
  license?: unknown;
  dependencies?: Record<string, string>;
  optionalDependencies?: Record<string, string>;
  peerDependencies?: Record<string, string>;
  dev?: boolean;
}

interface PackageLock {
  lockfileVersion: number;
  packages: Record<string, LockPackage>;
}

export interface GitMetadata {
  revision: string;
  state: "committed" | "uncommitted";
  commitSha: string | null;
  commitEpochSeconds: number;
}

interface ArtifactRecord {
  path: string;
  bytes: number;
  sha256: string;
}

interface RepositoryLegalFiles {
  license: Uint8Array;
  notice: Uint8Array;
}

export interface BundleBuildOptions {
  distDirectory?: string;
  gitMetadata?: GitMetadata;
  outputDirectory?: string;
  packageDirectory?: string;
  repositoryDirectory?: string;
  sourceDateEpoch?: string;
  sourceDirectory?: string;
  spec?: PresentationSpec;
}

/** What the offline checks concluded, and what the manifest then records. */
export interface OfflineAssurance {
  readonly selfContainedHtml: boolean;
  readonly runtimeNetworkDependencies: boolean;
  readonly filesScanned: number;
}

export interface BundleBuildResult {
  outputDirectory: string;
  manifestPath: string;
  checksumsPath: string;
}

export class BundleBuildError extends Error {
  constructor(message: string, options?: ErrorOptions) {
    super(message, options);
    this.name = "BundleBuildError";
  }
}

function comparePaths(left: string, right: string): number {
  return left < right ? -1 : left > right ? 1 : 0;
}

function sha256(value: Uint8Array | string): string {
  return createHash("sha256").update(value).digest("hex");
}

function parseEpochSeconds(value: string, label: string): number {
  if (!/^\d+$/.test(value)) {
    throw new BundleBuildError(`${label} must be a non-negative integer`);
  }
  const parsed = Number(value);
  if (!Number.isSafeInteger(parsed)) {
    throw new BundleBuildError(`${label} is outside the safe integer range`);
  }
  return parsed;
}

function commandOutput(
  executable: string,
  args: readonly string[],
  workingDirectory: string,
): string {
  return execFileSync(executable, args, {
    cwd: workingDirectory,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
  }).trim();
}

export function resolveGitMetadata(workingDirectory: string): GitMetadata {
  try {
    const isWorkTree = commandOutput(
      "git",
      ["rev-parse", "--is-inside-work-tree"],
      workingDirectory,
    );
    if (isWorkTree !== "true") {
      throw new BundleBuildError(
        `${workingDirectory} is not inside a Git checkout`,
      );
    }

    const commitSha = commandOutput(
      "git",
      ["rev-parse", "HEAD"],
      workingDirectory,
    );
    if (!/^[0-9a-f]{40}$/i.test(commitSha)) {
      throw new BundleBuildError("Git returned an invalid commit SHA");
    }
    const commitEpochSeconds = parseEpochSeconds(
      commandOutput(
        "git",
        ["show", "-s", "--format=%ct", "HEAD"],
        workingDirectory,
      ),
      "Git commit timestamp",
    );
    const status = commandOutput(
      "git",
      ["status", "--porcelain=v1", "--untracked-files=all"],
      workingDirectory,
    );
    const isDirty = status.length > 0;

    return {
      revision: isDirty ? "uncommitted" : commitSha,
      state: isDirty ? "uncommitted" : "committed",
      commitSha: isDirty ? null : commitSha,
      commitEpochSeconds,
    };
  } catch (error: unknown) {
    if (error instanceof BundleBuildError) {
      throw error;
    }
    throw new BundleBuildError(
      `Unable to resolve Git revision from ${workingDirectory}; set up a Git checkout before building the customer bundle`,
      { cause: error },
    );
  }
}

export function resolveBuildTimestamp(
  gitEpochSeconds: number,
  sourceDateEpoch: string | undefined,
): string {
  const epochSeconds =
    sourceDateEpoch === undefined
      ? gitEpochSeconds
      : parseEpochSeconds(sourceDateEpoch, "SOURCE_DATE_EPOCH");
  const timestamp = new Date(epochSeconds * 1000);
  if (Number.isNaN(timestamp.valueOf())) {
    throw new BundleBuildError(
      "Build timestamp is outside the supported date range",
    );
  }
  return timestamp.toISOString();
}

function classifySourceFile(
  filePath: string,
  rootDirectory: string,
): SourceFileKind {
  const extension = path.extname(filePath).toLocaleLowerCase("en");
  if (SCRIPT_EXTENSIONS.has(extension)) {
    return "script";
  }
  if (STYLE_EXTENSIONS.has(extension)) {
    return "style";
  }
  if (MARKUP_EXTENSIONS.has(extension)) {
    return "markup";
  }
  if (INERT_EXTENSIONS.has(extension)) {
    return "inert";
  }
  throw new BundleBuildError(
    `Presentation source contains a file the offline scan cannot classify: ${path.relative(rootDirectory, filePath)}. Every file that can reach the customer bundle must be scannable, so give it a known extension or keep it out of the source tree.`,
  );
}

async function sourceFiles(
  directory: string,
  rootDirectory: string = directory,
): Promise<ClassifiedSourceFile[]> {
  const directoryDetails = await lstat(directory);
  if (directoryDetails.isSymbolicLink()) {
    throw new BundleBuildError(
      `Symbolic links are not allowed in presentation source: ${directory}`,
    );
  }
  if (!directoryDetails.isDirectory()) {
    throw new BundleBuildError(
      `Presentation source is not a directory: ${directory}`,
    );
  }
  const entries = await readdir(directory, { withFileTypes: true });
  const files: ClassifiedSourceFile[] = [];
  for (const entry of entries) {
    const entryPath = path.join(directory, entry.name);
    if (entry.isSymbolicLink()) {
      throw new BundleBuildError(
        `Symbolic links are not allowed in presentation source: ${entryPath}`,
      );
    }
    if (entry.isDirectory()) {
      files.push(...(await sourceFiles(entryPath, rootDirectory)));
    } else if (entry.isFile() && !IGNORED_FILE_NAMES.has(entry.name)) {
      files.push({
        path: entryPath,
        kind: classifySourceFile(entryPath, rootDirectory),
      });
    }
  }
  return files.sort((left, right) => comparePaths(left.path, right.path));
}

async function isReadableFile(candidate: string): Promise<boolean> {
  try {
    const details = await lstat(candidate);
    if (details.isSymbolicLink()) {
      throw new BundleBuildError(
        `Symbolic links are not allowed in presentation source: ${candidate}`,
      );
    }
    return details.isFile();
  } catch (error: unknown) {
    if (error instanceof BundleBuildError) {
      throw error;
    }
    return false;
  }
}

/**
 * Resolve one local module specifier to the file the bundler would read.
 *
 * A specifier that cannot be resolved is a file this scan cannot open, so it
 * is refused rather than skipped.
 */
async function resolveLocalSpecifier(
  fromFile: string,
  specifier: string,
): Promise<string> {
  const base = path.resolve(path.dirname(fromFile), specifier);
  const candidates = [base];
  // TypeScript sources import a sibling module by its emitted `.js` name.
  const jsExtension = /\.(m|c)?js$/i.exec(base);
  if (jsExtension !== null) {
    const stem = base.slice(0, base.length - jsExtension[0].length);
    const infix = jsExtension[1] ?? "";
    candidates.push(`${stem}.${infix}ts`, `${stem}.${infix}tsx`);
  }
  for (const extension of MODULE_RESOLUTION_EXTENSIONS) {
    candidates.push(`${base}${extension}`);
    candidates.push(path.join(base, `index${extension}`));
  }
  for (const candidate of candidates) {
    if (await isReadableFile(candidate)) {
      return candidate;
    }
  }
  throw new BundleBuildError(
    `Presentation source imports ${specifier} from ${fromFile}, which the offline scan cannot resolve to a file it can read`,
  );
}

/**
 * Close the set of source files over the imports they declare.
 *
 * A directory walk answers "what is in this folder", but the question the
 * offline scan has to answer is "what can reach the customer bundle", and the
 * two are not the same: the deck's own content module already imports scenario
 * data from outside the presentation tree, so a module placed beside it would
 * be compiled into the artifact without ever being opened by a walk.
 */
export async function reachableSourceFiles(
  entryFiles: readonly ClassifiedSourceFile[],
  rootDirectory: string,
): Promise<ClassifiedSourceFile[]> {
  const found = new Map<string, ClassifiedSourceFile>();
  const queue: ClassifiedSourceFile[] = [];
  for (const file of entryFiles) {
    if (!found.has(file.path)) {
      found.set(file.path, file);
      queue.push(file);
    }
  }

  while (queue.length > 0) {
    const file = queue.shift()!;
    if (file.kind !== "script") {
      continue;
    }
    const source = await readFile(file.path, "utf8");
    for (const specifier of importSpecifiers(file.path, source)) {
      if (!specifier.startsWith(".") && !specifier.startsWith("/")) {
        // A package specifier is inventoried against the lockfile instead.
        continue;
      }
      const resolved = await resolveLocalSpecifier(file.path, specifier);
      if (found.has(resolved)) {
        continue;
      }
      const reached: ClassifiedSourceFile = {
        path: resolved,
        kind: classifySourceFile(resolved, rootDirectory),
      };
      found.set(resolved, reached);
      queue.push(reached);
    }
  }

  return [...found.values()].sort((left, right) =>
    comparePaths(left.path, right.path),
  );
}

async function scannedSourceFiles(
  directory: string,
): Promise<ClassifiedSourceFile[]> {
  return reachableSourceFiles(await sourceFiles(directory), directory);
}

async function scriptSourceFiles(directory: string): Promise<string[]> {
  return (await scannedSourceFiles(directory))
    .filter((file) => file.kind === "script")
    .map((file) => file.path);
}

function markupIssues(content: string): string[] {
  const document = readHtml(content);
  const issues: string[] = [];
  for (const element of document.elements) {
    issues.push(...externalReferenceIssues(element));
  }
  if (document.rawText.some((block) => block.name === "script")) {
    issues.push("embedded script");
  }
  return issues;
}

export async function assertNoForbiddenRuntimeSource(
  directory: string,
): Promise<OfflineAssurance> {
  const issues: string[] = [];
  const scanned = await scannedSourceFiles(directory);
  for (const file of scanned) {
    const relativePath = path.relative(directory, file.path);
    if (file.kind === "inert") {
      continue;
    }
    const content = await readFile(file.path, "utf8");
    if (file.kind === "style") {
      if (EXTERNAL_CSS_RESOURCE_PATTERN.test(content)) {
        issues.push(`${relativePath}: external CSS resource`);
      }
      continue;
    }
    if (file.kind === "markup") {
      for (const issue of markupIssues(content)) {
        issues.push(`${relativePath}: ${issue}`);
      }
      continue;
    }
    for (const capability of findSourceCapabilities(content)) {
      issues.push(`${relativePath}: ${capability}`);
    }
  }
  if (issues.length > 0) {
    throw new BundleBuildError(
      `Presentation source contains forbidden runtime behavior:\n- ${issues.join("\n- ")}`,
    );
  }
  return {
    selfContainedHtml: true,
    runtimeNetworkDependencies: false,
    filesScanned: scanned.length,
  };
}

function isInlineValue(value: string): boolean {
  const trimmed = value.trim();
  return (
    trimmed.length === 0 || trimmed.startsWith("#") || /^data:/i.test(trimmed)
  );
}

function externalReferenceIssues(element: HtmlElement): string[] {
  const issues: string[] = [];
  for (const rule of EXTERNAL_REFERENCE_RULES) {
    if (!rule.elements.includes(element.name)) {
      continue;
    }
    if (rule.attributes === undefined) {
      issues.push(`${rule.label} <${element.name}>`);
      continue;
    }
    for (const attribute of rule.attributes) {
      const value = element.attributes.get(attribute);
      if (value === undefined) {
        continue;
      }
      if (rule.allowsInlineValue === true && isInlineValue(value)) {
        continue;
      }
      issues.push(`${rule.label} <${element.name} ${attribute}>`);
    }
  }
  if (
    element.name === "meta" &&
    element.attributes.get("http-equiv")?.toLocaleLowerCase("en") === "refresh"
  ) {
    issues.push("automatic page refresh <meta http-equiv=refresh>");
  }
  const inlineStyle = element.attributes.get("style");
  if (
    inlineStyle !== undefined &&
    EXTERNAL_CSS_RESOURCE_PATTERN.test(inlineStyle)
  ) {
    issues.push(`external CSS resource <${element.name} style>`);
  }
  return issues;
}

/**
 * Decide whether a built artifact needs the network, from the artifact.
 *
 * The answer is read out of the document: which elements carry which
 * attribute values, what the style blocks declare, and what the scripts the
 * browser will run actually do. The previous check searched the serialized
 * text for the same shapes, which both refused deck copy that quoted a script
 * tag and accepted a beacon written inside an inline script.
 */
export function assertSelfContainedHtml(html: string): OfflineAssurance {
  let document;
  try {
    document = readHtml(html);
  } catch (error: unknown) {
    if (error instanceof HtmlParseError) {
      throw new BundleBuildError(
        `Built HTML cannot be read as a document, so it cannot be shown to be self-contained: ${error.message}`,
        { cause: error },
      );
    }
    throw error;
  }
  const issues: string[] = [];
  for (const element of document.elements) {
    issues.push(...externalReferenceIssues(element));
  }
  for (const block of document.rawText) {
    if (block.name === "style") {
      if (EXTERNAL_CSS_RESOURCE_PATTERN.test(block.content)) {
        issues.push("external CSS resource <style>");
      }
      continue;
    }
    if (block.name !== "script") {
      continue;
    }
    const type = block.attributes.get("type")?.trim().toLocaleLowerCase("en");
    if (type !== undefined && RESOURCE_DIRECTING_SCRIPT_TYPES.has(type)) {
      issues.push(`resource-directing script <script type=${type}>`);
      continue;
    }
    if (type !== undefined && NON_JAVASCRIPT_SCRIPT_TYPES.has(type)) {
      continue;
    }
    for (const target of findNetworkTargets(block.content)) {
      issues.push(`inline script: ${target}`);
    }
  }
  if (issues.length > 0) {
    throw new BundleBuildError(
      `Built HTML is not self-contained:\n- ${[...new Set(issues)].join("\n- ")}`,
    );
  }
  return {
    selfContainedHtml: true,
    runtimeNetworkDependencies: false,
    filesScanned: document.elements.length,
  };
}

function packageNameFromSpecifier(specifier: string): string | null {
  if (
    specifier.startsWith(".") ||
    specifier.startsWith("/") ||
    specifier.startsWith("node:") ||
    specifier.startsWith("#")
  ) {
    return null;
  }
  const parts = specifier.split("/");
  return specifier.startsWith("@")
    ? parts.slice(0, 2).join("/")
    : (parts[0] ?? null);
}

interface SourceToken {
  kind: SyntaxKind;
  value: string;
}

function sourceTokens(source: string): SourceToken[] {
  const scanner = createScanner(true, LanguageVariant.JSX, source);
  const tokens: SourceToken[] = [];
  let kind = scanner.scan();
  let scanCount = 0;
  while (kind !== SyntaxKind.EndOfFile) {
    scanCount += 1;
    if (scanCount > source.length * 2 + 1) {
      throw new BundleBuildError(
        "Unable to enumerate presentation source imports",
      );
    }
    const tokenStart = scanner.getTokenStart();
    const tokenEnd = scanner.getTokenEnd();
    if (tokenEnd <= tokenStart) {
      if (tokenStart >= source.length) {
        throw new BundleBuildError(
          "Presentation source scanner stopped before EOF",
        );
      }
      scanner.resetTokenState(tokenStart + 1);
      kind = scanner.scan();
      continue;
    }
    tokens.push({ kind, value: scanner.getTokenValue() });
    kind = scanner.scan();
  }
  return tokens;
}

function staticImportSpecifier(
  tokens: SourceToken[],
  start: number,
): string | null {
  const first = tokens[start];
  if (first?.kind === SyntaxKind.StringLiteral) {
    return first.value;
  }
  for (let index = start; index < tokens.length; index += 1) {
    const lexeme = tokens[index]!;
    if (lexeme.kind === SyntaxKind.SemicolonToken) {
      return null;
    }
    if (lexeme.value === "from") {
      const specifier = tokens[index + 1];
      return specifier?.kind === SyntaxKind.StringLiteral
        ? specifier.value
        : null;
    }
  }
  return null;
}

function staticExportSpecifier(
  tokens: SourceToken[],
  start: number,
): string | null {
  for (let index = start; index < tokens.length; index += 1) {
    const lexeme = tokens[index]!;
    if (lexeme.kind === SyntaxKind.SemicolonToken) {
      return null;
    }
    if (lexeme.value === "from") {
      const specifier = tokens[index + 1];
      return specifier?.kind === SyntaxKind.StringLiteral
        ? specifier.value
        : null;
    }
  }
  return null;
}

/**
 * Every module specifier a source file declares, in source order.
 *
 * Both callers need this list for different reasons - one inventories the
 * packages it names, the other follows the local files it reaches - so the
 * specifiers are collected once and interpreted by each caller.
 */
function importSpecifiers(filePath: string, source: string): string[] {
  const specifiers: string[] = [];
  const tokens = sourceTokens(source);

  for (let index = 0; index < tokens.length; index += 1) {
    const lexeme = tokens[index]!;
    const previous = tokens[index - 1];
    const next = tokens[index + 1];
    if (lexeme.kind === SyntaxKind.ImportKeyword) {
      if (next?.kind === SyntaxKind.TypeKeyword) {
        continue;
      }
      if (next?.kind === SyntaxKind.OpenParenToken) {
        const argument = tokens[index + 2];
        if (argument?.kind !== SyntaxKind.StringLiteral) {
          throw new BundleBuildError(
            `Dynamic import must use a string literal so offline dependencies are enumerable: ${filePath}`,
          );
        }
        specifiers.push(argument.value);
        continue;
      }
      if (next?.kind === SyntaxKind.DotToken) {
        continue;
      }
      const specifier = staticImportSpecifier(tokens, index + 1);
      if (specifier !== null) {
        specifiers.push(specifier);
      }
      continue;
    }
    if (
      lexeme.kind === SyntaxKind.ExportKeyword &&
      next?.kind !== SyntaxKind.TypeKeyword
    ) {
      const specifier = staticExportSpecifier(tokens, index + 1);
      if (specifier !== null) {
        specifiers.push(specifier);
      }
      continue;
    }
    if (
      lexeme.value === "require" &&
      next?.kind === SyntaxKind.OpenParenToken &&
      previous?.kind !== SyntaxKind.DotToken &&
      previous?.kind !== SyntaxKind.QuestionDotToken
    ) {
      const argument = tokens[index + 2];
      if (argument?.kind !== SyntaxKind.StringLiteral) {
        throw new BundleBuildError(
          `require must use a string literal so offline dependencies are enumerable: ${filePath}`,
        );
      }
      specifiers.push(argument.value);
    }
  }

  return specifiers;
}

function runtimeImports(filePath: string, source: string): string[] {
  const packages = new Set<string>();
  for (const specifier of importSpecifiers(filePath, source)) {
    const packageName = packageNameFromSpecifier(specifier);
    if (packageName !== null) {
      packages.add(packageName);
    }
  }
  return [...packages].sort(comparePaths);
}

function parsePackageLock(value: unknown): PackageLock {
  if (typeof value !== "object" || value === null) {
    throw new BundleBuildError("package-lock.json must contain an object");
  }
  const candidate = value as Partial<PackageLock>;
  if (
    !Number.isInteger(candidate.lockfileVersion) ||
    candidate.lockfileVersion !== 3 ||
    typeof candidate.packages !== "object" ||
    candidate.packages === null
  ) {
    throw new BundleBuildError("package-lock.json must use lockfileVersion 3");
  }
  return candidate as PackageLock;
}

async function loadPackageLock(packageDirectory: string): Promise<PackageLock> {
  const lockPath = path.join(packageDirectory, "package-lock.json");
  try {
    return parsePackageLock(
      JSON.parse(await readFile(lockPath, "utf8")) as unknown,
    );
  } catch (error: unknown) {
    if (error instanceof BundleBuildError) {
      throw error;
    }
    throw new BundleBuildError(`Unable to load ${lockPath}`, { cause: error });
  }
}

function dependencyNames(entry: LockPackage): string[] {
  return Object.keys({
    ...entry.dependencies,
    ...entry.optionalDependencies,
    ...entry.peerDependencies,
  }).sort(comparePaths);
}

function packageNameFromLockPath(lockPath: string): string {
  const marker = "node_modules/";
  const markerIndex = lockPath.lastIndexOf(marker);
  if (markerIndex < 0) {
    throw new BundleBuildError(`Invalid installed package path: ${lockPath}`);
  }
  return lockPath.slice(markerIndex + marker.length);
}

function resolveDependencyLockPath(
  dependencyName: string,
  requesterPath: string,
  packages: Record<string, LockPackage>,
): string {
  let current = requesterPath;
  while (current.length > 0) {
    const candidate = `${current}/node_modules/${dependencyName}`;
    if (packages[candidate] !== undefined) {
      return candidate;
    }
    const parentMarker = current.lastIndexOf("/node_modules/");
    current = parentMarker < 0 ? "" : current.slice(0, parentMarker);
  }

  const rootCandidate = `node_modules/${dependencyName}`;
  if (packages[rootCandidate] !== undefined) {
    return rootCandidate;
  }
  throw new BundleBuildError(
    `package-lock.json does not resolve runtime dependency ${dependencyName} from ${requesterPath}`,
  );
}

export async function discoverRuntimePackageNames(
  sourceDirectory: string,
): Promise<string[]> {
  const directPackages = new Set<string>();
  for (const filePath of await scriptSourceFiles(sourceDirectory)) {
    const source = await readFile(filePath, "utf8");
    for (const packageName of runtimeImports(filePath, source)) {
      directPackages.add(packageName);
    }
  }
  return [...directPackages].sort(comparePaths);
}

async function bundledPackagePaths(
  packageDirectory: string,
  sourceDirectory: string,
  lock: PackageLock,
): Promise<string[]> {
  const directPackages = await discoverRuntimePackageNames(sourceDirectory);

  const queue = directPackages.map((name) =>
    resolveDependencyLockPath(name, "", lock.packages),
  );
  const visited = new Set<string>();
  while (queue.length > 0) {
    const lockPath = queue.shift();
    if (lockPath === undefined || visited.has(lockPath)) {
      continue;
    }
    const entry = lock.packages[lockPath];
    if (entry === undefined) {
      throw new BundleBuildError(`Missing package-lock entry for ${lockPath}`);
    }
    if (entry.dev === true) {
      throw new BundleBuildError(
        `Runtime package ${packageNameFromLockPath(lockPath)} is marked dev-only`,
      );
    }
    visited.add(lockPath);
    for (const dependencyName of dependencyNames(entry)) {
      queue.push(
        resolveDependencyLockPath(dependencyName, lockPath, lock.packages),
      );
    }
  }

  if (visited.size === 0) {
    throw new BundleBuildError(
      `No bundled runtime packages were discovered under ${path.relative(packageDirectory, sourceDirectory)}`,
    );
  }
  return [...visited].sort(comparePaths);
}

async function licenseTexts(packagePath: string): Promise<string> {
  const entries = await readdir(packagePath, { withFileTypes: true });
  const candidates = entries
    .filter(
      (entry) =>
        entry.isFile() &&
        /^(?:licen[cs]e|copying|notice)(?:\..+)?$/i.test(entry.name),
    )
    .map((entry) => entry.name)
    .sort(comparePaths);
  if (candidates.length === 0) {
    throw new BundleBuildError(
      `No usable license text found in ${packagePath}`,
    );
  }
  const sections: string[] = [];
  for (const candidate of candidates) {
    const text = (
      await readFile(path.join(packagePath, candidate), "utf8")
    ).trim();
    if (text.length === 0) {
      throw new BundleBuildError(
        `License text is empty in ${packagePath}/${candidate}`,
      );
    }
    sections.push(`${candidate}\n\n${text}`);
  }
  return sections.join("\n\n------------------------------\n\n");
}

export async function buildThirdPartyNotices(
  packageDirectory: string,
  sourceDirectory: string,
): Promise<string> {
  const lock = await loadPackageLock(packageDirectory);
  const sections: string[] = [];
  for (const lockPath of await bundledPackagePaths(
    packageDirectory,
    sourceDirectory,
    lock,
  )) {
    const entry = lock.packages[lockPath];
    if (entry === undefined) {
      throw new BundleBuildError(`Missing package-lock entry for ${lockPath}`);
    }
    if (typeof entry.version !== "string" || entry.version.length === 0) {
      throw new BundleBuildError(
        `Runtime package ${lockPath} has no locked version`,
      );
    }
    if (
      typeof entry.license !== "string" ||
      entry.license.trim().length === 0
    ) {
      throw new BundleBuildError(
        `Runtime package ${lockPath} has no declared license`,
      );
    }
    const packagePath = path.join(packageDirectory, lockPath);
    const packageJson = JSON.parse(
      await readFile(path.join(packagePath, "package.json"), "utf8"),
    ) as { name?: unknown; version?: unknown };
    const packageName = packageNameFromLockPath(lockPath);
    if (
      packageJson.name !== packageName ||
      packageJson.version !== entry.version
    ) {
      throw new BundleBuildError(
        `Installed package does not match package-lock.json: ${packageName}@${entry.version}`,
      );
    }
    const text = await licenseTexts(packagePath);
    sections.push(
      [
        `${packageName}@${entry.version}`,
        `Declared license: ${entry.license}`,
        "",
        text,
      ].join("\n"),
    );
  }

  return [
    "THIRD-PARTY SOFTWARE NOTICES",
    "",
    "The self-contained HTML presentation includes the following runtime packages.",
    "Build-only development tools are not included in this customer artifact.",
    "",
    sections.join(
      "\n\n============================================================\n\n",
    ),
    "",
  ].join("\n");
}

async function artifactRecord(
  filePath: string,
  relativePath: string,
): Promise<ArtifactRecord> {
  const bytes = await readFile(filePath);
  return {
    path: relativePath,
    bytes: bytes.byteLength,
    sha256: sha256(bytes),
  };
}

function assertSafeOutputDirectory(
  outputDirectory: string,
  distDirectory: string,
): void {
  const resolved = path.resolve(outputDirectory);
  const expected = path.join(
    path.resolve(distDirectory),
    BUNDLE_DIRECTORY_NAME,
  );
  if (resolved !== expected) {
    throw new BundleBuildError(
      `Bundle output directory must be exactly ${expected}: ${resolved}`,
    );
  }
  if (path.dirname(resolved) === resolved) {
    throw new BundleBuildError(
      "Refusing to use a filesystem root as bundle output",
    );
  }
}

async function assertRequiredFile(
  filePath: string,
  label: string,
): Promise<void> {
  try {
    const details = await stat(filePath);
    if (!details.isFile() || details.size === 0) {
      throw new BundleBuildError(
        `${label} is not a non-empty file: ${filePath}`,
      );
    }
  } catch (error: unknown) {
    if (error instanceof BundleBuildError) {
      throw error;
    }
    throw new BundleBuildError(`${label} is missing: ${filePath}`, {
      cause: error,
    });
  }
}

async function readRepositoryLegalFile(
  repositoryDirectory: string,
  fileName: string,
): Promise<Uint8Array> {
  const resolvedRepositoryDirectory = path.resolve(repositoryDirectory);
  let repositoryDetails;
  try {
    repositoryDetails = await lstat(resolvedRepositoryDirectory);
  } catch (error: unknown) {
    throw new BundleBuildError(
      `Repository directory is missing: ${resolvedRepositoryDirectory}`,
      { cause: error },
    );
  }
  if (repositoryDetails.isSymbolicLink() || !repositoryDetails.isDirectory()) {
    throw new BundleBuildError(
      `Repository directory must be a real directory, not a symbolic link: ${resolvedRepositoryDirectory}`,
    );
  }

  const resolvedFilePath = path.resolve(resolvedRepositoryDirectory, fileName);
  if (path.dirname(resolvedFilePath) !== resolvedRepositoryDirectory) {
    throw new BundleBuildError(
      `Repository legal file resolves outside the repository: ${fileName}`,
    );
  }

  let fileDetails;
  try {
    fileDetails = await lstat(resolvedFilePath);
  } catch (error: unknown) {
    throw new BundleBuildError(
      `Repository ${fileName} is missing: ${resolvedFilePath}`,
      { cause: error },
    );
  }
  if (fileDetails.isSymbolicLink() || !fileDetails.isFile()) {
    throw new BundleBuildError(
      `Repository ${fileName} must be a regular file, not a symbolic link: ${resolvedFilePath}`,
    );
  }
  if (fileDetails.size === 0) {
    throw new BundleBuildError(
      `Repository ${fileName} is empty: ${resolvedFilePath}`,
    );
  }

  const [canonicalRepositoryDirectory, canonicalFilePath] = await Promise.all([
    realpath(resolvedRepositoryDirectory),
    realpath(resolvedFilePath),
  ]);
  if (path.dirname(canonicalFilePath) !== canonicalRepositoryDirectory) {
    throw new BundleBuildError(
      `Repository ${fileName} resolves outside the repository: ${resolvedFilePath}`,
    );
  }

  const fileHandle = await open(resolvedFilePath, "r");
  try {
    const [openedFileDetails, currentPathDetails] = await Promise.all([
      fileHandle.stat(),
      lstat(resolvedFilePath),
    ]);
    if (
      currentPathDetails.isSymbolicLink() ||
      !openedFileDetails.isFile() ||
      openedFileDetails.dev !== fileDetails.dev ||
      openedFileDetails.ino !== fileDetails.ino ||
      currentPathDetails.dev !== openedFileDetails.dev ||
      currentPathDetails.ino !== openedFileDetails.ino
    ) {
      throw new BundleBuildError(
        `Repository ${fileName} changed while its source was being validated: ${resolvedFilePath}`,
      );
    }

    const contents = await fileHandle.readFile();
    if (contents.byteLength === 0) {
      throw new BundleBuildError(
        `Repository ${fileName} became empty while building the bundle: ${resolvedFilePath}`,
      );
    }
    return contents;
  } finally {
    await fileHandle.close();
  }
}

async function readRepositoryLegalFiles(
  repositoryDirectory: string,
): Promise<RepositoryLegalFiles> {
  const [license, notice] = await Promise.all([
    readRepositoryLegalFile(repositoryDirectory, REPOSITORY_LICENSE_FILE_NAME),
    readRepositoryLegalFile(repositoryDirectory, REPOSITORY_NOTICE_FILE_NAME),
  ]);
  const licenseText = Buffer.from(license).toString("utf8");
  if (
    !licenseText.includes("Apache License") ||
    !licenseText.includes("Version 2.0, January 2004") ||
    !licenseText.includes("END OF TERMS AND CONDITIONS")
  ) {
    throw new BundleBuildError(
      `Repository ${REPOSITORY_LICENSE_FILE_NAME} is not an Apache License 2.0 text`,
    );
  }
  return { license, notice };
}

export async function buildCustomerBundle(
  options: BundleBuildOptions = {},
): Promise<BundleBuildResult> {
  const packageDirectory = options.packageDirectory ?? presentationRoot;
  const sourceDirectory =
    options.sourceDirectory ?? path.join(packageDirectory, "src");
  const distDirectory = options.distDirectory ?? distRoot;
  const outputDirectory =
    options.outputDirectory ?? path.join(distDirectory, BUNDLE_DIRECTORY_NAME);
  const repositoryDirectory = options.repositoryDirectory ?? repositoryRoot;
  const spec = validatePresentationContent(options.spec ?? presentation);
  const evidenceStates = [
    ...new Set(spec.slides.map((slide) => slide.evidenceState)),
  ].sort(comparePaths);
  const guideContractSourceRevisions = [
    ...new Set(
      spec.slides
        .filter((slide) => slide.evidenceState === "guide-contract")
        .map((slide) => slide.sourceRevision as string),
    ),
  ].sort(comparePaths);
  const gitMetadata =
    options.gitMetadata ?? resolveGitMetadata(repositoryDirectory);
  const generatedAt = resolveBuildTimestamp(
    gitMetadata.commitEpochSeconds,
    options.sourceDateEpoch ?? process.env.SOURCE_DATE_EPOCH,
  );
  const sourceHtmlPath = path.join(distDirectory, "index.html");
  const sourcePptxPath = path.join(
    distDirectory,
    path.basename(defaultPptxPath),
  );

  assertSafeOutputDirectory(outputDirectory, distDirectory);
  const repositoryLegalFiles =
    await readRepositoryLegalFiles(repositoryDirectory);
  const sourceAssurance = await assertNoForbiddenRuntimeSource(sourceDirectory);
  await assertRequiredFile(sourceHtmlPath, "Built HTML");
  await assertRequiredFile(sourcePptxPath, "Built PowerPoint");
  const html = await readFile(sourceHtmlPath, "utf8");
  const htmlAssurance = assertSelfContainedHtml(html);
  const notices = await buildThirdPartyNotices(
    packageDirectory,
    sourceDirectory,
  );

  const stagingDirectory = path.join(
    distDirectory,
    `.${BUNDLE_DIRECTORY_NAME}.staging`,
  );
  await rm(stagingDirectory, { recursive: true, force: true });
  await mkdir(stagingDirectory, { recursive: true });
  const htmlPath = path.join(stagingDirectory, HTML_FILE_NAME);
  const pptxPath = path.join(stagingDirectory, POWERPOINT_FILE_NAME);
  const noticesPath = path.join(stagingDirectory, NOTICES_FILE_NAME);
  const repositoryLicensePath = path.join(
    stagingDirectory,
    REPOSITORY_LICENSE_FILE_NAME,
  );
  const repositoryNoticePath = path.join(
    stagingDirectory,
    REPOSITORY_NOTICE_FILE_NAME,
  );
  await copyFile(sourceHtmlPath, htmlPath);
  await copyFile(sourcePptxPath, pptxPath);
  await writeFile(noticesPath, notices, "utf8");
  await writeFile(repositoryLicensePath, repositoryLegalFiles.license);
  await writeFile(repositoryNoticePath, repositoryLegalFiles.notice);

  const primaryArtifacts = await Promise.all(
    [
      HTML_FILE_NAME,
      POWERPOINT_FILE_NAME,
      NOTICES_FILE_NAME,
      REPOSITORY_LICENSE_FILE_NAME,
      REPOSITORY_NOTICE_FILE_NAME,
    ]
      .sort(comparePaths)
      .map((relativePath) =>
        artifactRecord(path.join(stagingDirectory, relativePath), relativePath),
      ),
  );
  const manifest = {
    schema_version: 2,
    generated_at: generatedAt,
    source: {
      revision: gitMetadata.revision,
      state: gitMetadata.state,
      commit_sha: gitMetadata.commitSha,
    },
    deck: {
      title: spec.title,
      schema_version: spec.schemaVersion,
      scenario_slug: spec.scenario.slug,
      scenario_legacy_id: spec.scenario.legacyId,
      evidence_states: evidenceStates,
      guide_contract_source_revisions: guideContractSourceRevisions,
      slide_count: spec.slides.length,
      slides: spec.slides.map((slide) => ({
        id: slide.id,
        evidence_state: slide.evidenceState,
        source_revision: slide.sourceRevision ?? null,
      })),
    },
    offline: {
      // Recorded from the checks above rather than asserted beside them, and
      // scoped to what those checks establish: the artifact was read, not run.
      self_contained_html: htmlAssurance.selfContainedHtml,
      runtime_network_dependencies:
        htmlAssurance.runtimeNetworkDependencies ||
        sourceAssurance.runtimeNetworkDependencies,
      verified_by: {
        source_files_scanned: sourceAssurance.filesScanned,
        built_html_elements_read: htmlAssurance.filesScanned,
        browser_execution_observed: false,
      },
    },
    licensing: {
      repository_spdx_license: "Apache-2.0",
      repository_license_file: REPOSITORY_LICENSE_FILE_NAME,
      repository_notice_file: REPOSITORY_NOTICE_FILE_NAME,
      third_party_notices_file: NOTICES_FILE_NAME,
    },
    artifacts: primaryArtifacts,
  } as const;
  const stagingManifestPath = path.join(stagingDirectory, MANIFEST_FILE_NAME);
  await writeFile(
    stagingManifestPath,
    `${JSON.stringify(manifest, null, 2)}\n`,
    "utf8",
  );

  const checksumFiles = [
    HTML_FILE_NAME,
    POWERPOINT_FILE_NAME,
    MANIFEST_FILE_NAME,
    NOTICES_FILE_NAME,
    REPOSITORY_LICENSE_FILE_NAME,
    REPOSITORY_NOTICE_FILE_NAME,
  ].sort(comparePaths);
  const checksumLines: string[] = [];
  for (const relativePath of checksumFiles) {
    const contents = await readFile(path.join(stagingDirectory, relativePath));
    checksumLines.push(`${sha256(contents)}  ${relativePath}`);
  }
  const stagingChecksumsPath = path.join(stagingDirectory, CHECKSUMS_FILE_NAME);
  await writeFile(
    stagingChecksumsPath,
    `${checksumLines.join("\n")}\n`,
    "utf8",
  );

  await rm(outputDirectory, { recursive: true, force: true });
  await rename(stagingDirectory, outputDirectory);
  const manifestPath = path.join(outputDirectory, MANIFEST_FILE_NAME);
  const checksumsPath = path.join(outputDirectory, CHECKSUMS_FILE_NAME);

  return { outputDirectory, manifestPath, checksumsPath };
}

if (isMainModule(import.meta.url)) {
  const result = await buildCustomerBundle();
  process.stdout.write(
    `Built offline customer bundle: ${result.outputDirectory}\n`,
  );
}
