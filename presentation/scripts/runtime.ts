import { realpathSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

export class EntryPointError extends Error {
  constructor(message: string, options?: ErrorOptions) {
    super(message, options);
    this.name = "EntryPointError";
  }
}

// Resolve to a canonical path so that two names for the same file compare
// equal. `path.resolve` normalizes `.`, `..` and separators but keeps symbolic
// links, while the module loader hands out already-resolved paths; comparing
// the two forms makes a gate invoked through a linked path silently decide it
// is not the entry point and exit without doing any work.
function canonicalPath(target: string, label: string): string {
  try {
    // `native` also canonicalizes component case, which matters where the
    // file system is case-insensitive and two spellings name one file.
    return realpathSync.native(path.resolve(target));
  } catch (error: unknown) {
    throw new EntryPointError(`Unable to resolve the ${label}: ${target}`, {
      cause: error,
    });
  }
}

export const presentationRoot = canonicalPath(
  fileURLToPath(new URL("../", import.meta.url)),
  "presentation root",
);
export const repositoryRoot = path.resolve(presentationRoot, "..");
export const distRoot = path.join(presentationRoot, "dist");

export function isMainModule(moduleUrl: string): boolean {
  const entryPoint = process.argv[1];
  if (entryPoint === undefined) {
    // Refusing here is deliberate: a build gate that cannot tell whether it is
    // the entry point would otherwise report success while doing nothing.
    throw new EntryPointError(
      "No process entry point is available, so a build gate cannot tell whether it was invoked directly",
    );
  }
  return (
    canonicalPath(entryPoint, "process entry point") ===
    canonicalPath(fileURLToPath(moduleUrl), "module path")
  );
}
