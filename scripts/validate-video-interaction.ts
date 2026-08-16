#!/usr/bin/env node
import { readFileSync } from "node:fs";
import {
  VideoBlock,
  VideoInteractionDocument,
  validateVideoInteraction,
  type ValidationIssue,
} from "@mind-imprint/course-contract";

function emit(payload: unknown, asJson: boolean): void {
  if (asJson) {
    process.stdout.write(`${JSON.stringify(payload, null, 2)}\n`);
    return;
  }
  if (typeof payload === "object" && payload !== null && "ok" in payload) {
    const result = payload as { ok: boolean; issues?: ValidationIssue[] };
    if (result.ok) process.stdout.write("VideoInteractionDocument is valid\n");
    else for (const issue of result.issues ?? []) process.stdout.write(`- ${issue.path}: ${issue.message}\n`);
  }
}

function structuralIssues(
  issues: Array<{ path: Array<string | number>; message: string }>,
  prefix = "",
): ValidationIssue[] {
  return issues.map((issue) => {
    const suffix = issue.path.join(".");
    const path = prefix && suffix ? `${prefix}.${suffix}` : prefix || suffix;
    return { path, message: issue.message, layer: "structural" as const };
  });
}

function main(): number {
  const args = process.argv.slice(2);
  const asJson = args.includes("--json");
  const paths = args.filter((arg) => arg !== "--json");
  if (paths.length !== 2) throw new Error("DOCUMENT and OWNING_BLOCK paths are required");
  const [documentPath, ownerPath] = paths;
  if (!documentPath || !ownerPath) throw new Error("DOCUMENT and OWNING_BLOCK paths are required");

  const documentInput = JSON.parse(readFileSync(documentPath, "utf8")) as unknown;
  const ownerInput = JSON.parse(readFileSync(ownerPath, "utf8")) as unknown;
  const parsedDocument = VideoInteractionDocument.safeParse(documentInput);
  if (!parsedDocument.success) {
    emit({ ok: false, issues: structuralIssues(parsedDocument.error.issues) }, asJson);
    return 2;
  }
  const parsedOwner = VideoBlock.safeParse(ownerInput);
  if (!parsedOwner.success) {
    emit({ ok: false, issues: structuralIssues(parsedOwner.error.issues, "owningBlock") }, asJson);
    return 2;
  }

  const issues = validateVideoInteraction(parsedDocument.data, parsedOwner.data);
  if (issues.length > 0) {
    emit({ ok: false, issues }, asJson);
    return 2;
  }
  emit(
    {
      ok: true,
      cueCount: parsedDocument.data.video.cues.length,
      durationSeconds: parsedDocument.data.video.durationSeconds,
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
  else process.stderr.write(`VideoInteraction validator error: ${message}\n`);
  process.exitCode = 3;
}
