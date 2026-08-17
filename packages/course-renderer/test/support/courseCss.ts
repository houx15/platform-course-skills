import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

/**
 * §Slice5 / P1-06 — jsdom doesn't run a real layout engine, so a mounted
 * component's computed style can't prove the shipped stylesheet's rules
 * (overflow, minmax, hidden-block reservation, the focus ring) are what
 * they claim to be. This reads the actual shipped CSS SOURCE so tests can
 * assert those rules exist in the file the package ships — the structural
 * guarantee the plan calls for; full visual verification at the viewport
 * matrix is Slice 10's browser job.
 */
const here = dirname(fileURLToPath(import.meta.url));
export const courseCssText = readFileSync(resolve(here, "../../src/styles/course.css"), "utf-8");
