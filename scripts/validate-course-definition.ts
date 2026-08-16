#!/usr/bin/env node
import { readFileSync } from "node:fs";
import { collectAssetPaths, validateCourseDefinition } from "@mind-imprint/course-contract";

function emit(payload: unknown, asJson: boolean): void {
  if (asJson) {
    process.stdout.write(`${JSON.stringify(payload, null, 2)}\n`);
    return;
  }
  if (typeof payload === "object" && payload !== null && "ok" in payload) {
    const result = payload as { ok: boolean; issues?: Array<{ path: string; message: string }> };
    if (result.ok) process.stdout.write("CourseDefinition 2.0 is valid\n");
    else for (const issue of result.issues ?? []) process.stdout.write(`- ${issue.path}: ${issue.message}\n`);
  }
}

function main(): number {
  const args = process.argv.slice(2);
  const asJson = args.includes("--json");
  const inputPath = args.find((arg) => arg !== "--json");
  if (!inputPath) throw new Error("INPUT path is required");
  const input = JSON.parse(readFileSync(inputPath, "utf8")) as unknown;
  const validation = validateCourseDefinition(input);
  if (!validation.ok) {
    emit({ ok: false, issues: validation.issues }, asJson);
    return 2;
  }
  const document = input as Parameters<typeof collectAssetPaths>[0];
  emit(
    {
      ok: true,
      courseId: validation.course.id,
      assetPaths: collectAssetPaths(document).sort(),
    },
    asJson,
  );
  return 0;
}

try {
  process.exitCode = main();
} catch (error) {
  const message = error instanceof Error ? error.message : String(error);
  const asJson = process.argv.includes("--json");
  if (asJson) process.stdout.write(`${JSON.stringify({ ok: false, error: message }, null, 2)}\n`);
  else process.stderr.write(`CourseDefinition validator error: ${message}\n`);
  process.exitCode = 3;
}
