import { mkdtemp, rm, symlink } from "node:fs/promises";
import { execFileSync } from "node:child_process";
import os from "node:os";
import path from "node:path";
import { pathToFileURL } from "node:url";

import { afterEach, describe, expect, it } from "vitest";

import {
  EntryPointError,
  isMainModule,
  presentationRoot,
} from "../scripts/runtime";

const temporaryDirectories: string[] = [];
const originalEntryPoint = process.argv[1];

async function temporaryDirectory(): Promise<string> {
  const directory = await mkdtemp(
    path.join(os.tmpdir(), "presentation-entry-"),
  );
  temporaryDirectories.push(directory);
  return directory;
}

afterEach(async () => {
  process.argv[1] = originalEntryPoint;
  await Promise.all(
    temporaryDirectories
      .splice(0)
      .map((directory) => rm(directory, { recursive: true, force: true })),
  );
});

describe("build gate entry point", () => {
  it("recognizes its own module through a symbolic link on the entry path", async () => {
    const directory = await temporaryDirectory();
    const linkedScripts = path.join(directory, "scripts");
    await symlink(path.join(presentationRoot, "scripts"), linkedScripts);

    const modulePath = path.join(
      presentationRoot,
      "scripts",
      "validate-content.ts",
    );
    process.argv[1] = path.join(linkedScripts, "validate-content.ts");

    expect(isMainModule(pathToFileURL(modulePath).href)).toBe(true);
  });

  it("does not claim to be the entry point for a different module", async () => {
    const directory = await temporaryDirectory();
    await symlink(
      path.join(presentationRoot, "scripts"),
      path.join(directory, "scripts"),
    );
    process.argv[1] = path.join(directory, "scripts", "build-pptx.ts");

    expect(
      isMainModule(
        pathToFileURL(
          path.join(presentationRoot, "scripts", "validate-content.ts"),
        ).href,
      ),
    ).toBe(false);
  });

  it("fails loudly instead of skipping work it cannot place", async () => {
    const directory = await temporaryDirectory();
    process.argv[1] = path.join(directory, "missing-gate.ts");

    expect(() =>
      isMainModule(
        pathToFileURL(
          path.join(presentationRoot, "scripts", "validate-content.ts"),
        ).href,
      ),
    ).toThrowError(EntryPointError);
  });

  it("runs a gate invoked through a symbolic link instead of exiting silently", async () => {
    const directory = await temporaryDirectory();
    const linkedPresentation = path.join(directory, "presentation");
    await symlink(presentationRoot, linkedPresentation);

    const output = execFileSync(
      path.join(presentationRoot, "node_modules", ".bin", "tsx"),
      [path.join(linkedPresentation, "scripts", "validate-content.ts")],
      {
        cwd: presentationRoot,
        encoding: "utf8",
        stdio: ["ignore", "pipe", "pipe"],
      },
    );

    expect(output).toContain("Validated");
    expect(output).toContain("presentation slides");
  });
});
