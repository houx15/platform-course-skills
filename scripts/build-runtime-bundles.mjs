#!/usr/bin/env node
import { mkdir, mkdtemp, rename, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { build } from "esbuild";

const root = fileURLToPath(new URL("..", import.meta.url));
const outputDirectory = join(root, "course_toolkit", "runtime_dist");
const entries = [
  ["validate-course-definition", join(root, "scripts", "validate-course-definition.ts")],
  ["validate-video-interaction", join(root, "scripts", "validate-video-interaction.ts")],
];

const stagingDirectory = await mkdtemp(join(tmpdir(), "course-runtime-bundles-"));
try {
  await mkdir(outputDirectory, { recursive: true });
  for (const [name, entryPoint] of entries) {
    await build({
      entryPoints: [entryPoint],
      outfile: join(stagingDirectory, `${name}.mjs`),
      bundle: true,
      platform: "node",
      format: "esm",
      target: "node20",
      legalComments: "none",
      logLevel: "silent",
    });
  }
  for (const [name] of entries) {
    await rename(
      join(stagingDirectory, `${name}.mjs`),
      join(outputDirectory, `${name}.mjs`),
    );
  }
  process.stdout.write(`Built ${entries.length} pinned runtime validators.\n`);
} finally {
  await rm(stagingDirectory, { recursive: true, force: true });
}
