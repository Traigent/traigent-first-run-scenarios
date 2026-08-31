import { fileURLToPath } from "node:url";
import path from "node:path";

export const presentationRoot = fileURLToPath(new URL("../", import.meta.url));
export const repositoryRoot = path.resolve(presentationRoot, "..");
export const distRoot = path.join(presentationRoot, "dist");

export function isMainModule(moduleUrl: string): boolean {
  const entryPoint = process.argv[1];
  return (
    entryPoint !== undefined &&
    path.resolve(entryPoint) === fileURLToPath(moduleUrl)
  );
}
