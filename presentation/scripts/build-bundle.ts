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
const SOURCE_EXTENSIONS = new Set([".ts", ".tsx"]);

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

const EXTERNAL_HTML_PATTERNS = [
  { label: "external script", pattern: /<script\b[^>]*\bsrc\s*=/i },
  {
    label: "external link resource",
    pattern: /<link\b[^>]*\bhref\s*=/i,
  },
  { label: "base URL", pattern: /<base\b[^>]*\bhref\s*=/i },
  {
    label: "embedded active resource",
    pattern: /<(?:iframe|object|embed)\b/i,
  },
  {
    label: "external media source",
    pattern:
      /<(?:img|source|video|audio|track|input)\b[^>]*\bsrc\s*=\s*["']?(?!data:|#)[^\s"'>]+/i,
  },
  {
    label: "responsive media source",
    pattern: /<(?:img|source)\b[^>]*\bsrcset\s*=/i,
  },
  {
    label: "external video poster",
    pattern: /<video\b[^>]*\bposter\s*=\s*["']?(?!data:|#)[^\s"'>]+/i,
  },
  {
    label: "external SVG resource",
    pattern:
      /<(?:image|use)\b[^>]*\b(?:href|xlink:href)\s*=\s*["']?(?!data:|#)[^\s"'>]+/i,
  },
  {
    label: "automatic page refresh",
    pattern: /<meta\b(?=[^>]*\bhttp-equiv\s*=\s*["']?refresh\b)[^>]*>/i,
  },
  {
    label: "form submission target",
    pattern: /<(?:form|button|input)\b[^>]*\b(?:action|formaction)\s*=/i,
  },
  {
    label: "hyperlink beacon",
    pattern: /<a\b[^>]*\bping\s*=/i,
  },
  {
    label: "application cache manifest",
    pattern: /<html\b[^>]*\bmanifest\s*=/i,
  },
] as const;

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

async function sourceFiles(directory: string): Promise<string[]> {
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
  const files: string[] = [];
  for (const entry of entries) {
    const entryPath = path.join(directory, entry.name);
    if (entry.isSymbolicLink()) {
      throw new BundleBuildError(
        `Symbolic links are not allowed in presentation source: ${entryPath}`,
      );
    }
    if (entry.isDirectory()) {
      files.push(...(await sourceFiles(entryPath)));
    } else if (
      entry.isFile() &&
      SOURCE_EXTENSIONS.has(path.extname(entry.name))
    ) {
      files.push(entryPath);
    }
  }
  return files.sort(comparePaths);
}

export async function assertNoForbiddenRuntimeSource(
  directory: string,
): Promise<void> {
  const issues: string[] = [];
  for (const filePath of await sourceFiles(directory)) {
    const content = await readFile(filePath, "utf8");
    for (const forbidden of FORBIDDEN_SOURCE_PATTERNS) {
      if (forbidden.pattern.test(content)) {
        issues.push(
          `${path.relative(directory, filePath)}: ${forbidden.label}`,
        );
      }
    }
  }
  if (issues.length > 0) {
    throw new BundleBuildError(
      `Presentation source contains forbidden runtime behavior:\n- ${issues.join("\n- ")}`,
    );
  }
}

export function assertSelfContainedHtml(html: string): void {
  const issues: string[] = EXTERNAL_HTML_PATTERNS.filter(({ pattern }) =>
    pattern.test(html),
  ).map(({ label }) => label);
  const cssFragments = [
    ...[...html.matchAll(/<style\b[^>]*>([\s\S]*?)<\/style>/gi)].map(
      (match) => match[1] ?? "",
    ),
    ...[...html.matchAll(/\bstyle\s*=\s*(["'])(.*?)\1/gi)].map(
      (match) => match[2] ?? "",
    ),
  ];
  if (cssFragments.some((css) => EXTERNAL_CSS_RESOURCE_PATTERN.test(css))) {
    issues.push("external CSS resource");
  }
  if (issues.length > 0) {
    throw new BundleBuildError(
      `Built HTML is not self-contained:\n- ${issues.join("\n- ")}`,
    );
  }
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

function recordPackageSpecifier(
  packages: Set<string>,
  specifier: string,
): void {
  const packageName = packageNameFromSpecifier(specifier);
  if (packageName !== null) {
    packages.add(packageName);
  }
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
    const token = tokens[index]!;
    if (token.kind === SyntaxKind.SemicolonToken) {
      return null;
    }
    if (token.value === "from") {
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
    const token = tokens[index]!;
    if (token.kind === SyntaxKind.SemicolonToken) {
      return null;
    }
    if (token.value === "from") {
      const specifier = tokens[index + 1];
      return specifier?.kind === SyntaxKind.StringLiteral
        ? specifier.value
        : null;
    }
  }
  return null;
}

function runtimeImports(filePath: string, source: string): string[] {
  const packages = new Set<string>();
  const tokens = sourceTokens(source);

  for (let index = 0; index < tokens.length; index += 1) {
    const token = tokens[index]!;
    const previous = tokens[index - 1];
    const next = tokens[index + 1];
    if (token.kind === SyntaxKind.ImportKeyword) {
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
        recordPackageSpecifier(packages, argument.value);
        continue;
      }
      if (next?.kind === SyntaxKind.DotToken) {
        continue;
      }
      const specifier = staticImportSpecifier(tokens, index + 1);
      if (specifier !== null) {
        recordPackageSpecifier(packages, specifier);
      }
      continue;
    }
    if (
      token.kind === SyntaxKind.ExportKeyword &&
      next?.kind !== SyntaxKind.TypeKeyword
    ) {
      const specifier = staticExportSpecifier(tokens, index + 1);
      if (specifier !== null) {
        recordPackageSpecifier(packages, specifier);
      }
      continue;
    }
    if (
      token.value === "require" &&
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
      recordPackageSpecifier(packages, argument.value);
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
  for (const filePath of await sourceFiles(sourceDirectory)) {
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
  await assertNoForbiddenRuntimeSource(sourceDirectory);
  await assertRequiredFile(sourceHtmlPath, "Built HTML");
  await assertRequiredFile(sourcePptxPath, "Built PowerPoint");
  const html = await readFile(sourceHtmlPath, "utf8");
  assertSelfContainedHtml(html);
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
    schema_version: 1,
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
      evidence_state: "scenario-contract",
      guide_sha: null,
      guide_sha_reason:
        "not applicable: this expected-contract deck does not record an executed guide",
      slide_count: spec.slides.length,
      slide_ids: spec.slides.map((slide) => slide.id),
    },
    offline: {
      self_contained_html: true,
      runtime_network_dependencies: false,
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
