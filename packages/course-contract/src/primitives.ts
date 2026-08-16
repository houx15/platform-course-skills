import { z } from "zod";

/** Lower-case hyphenated identifier (§5): segments of [a-z0-9] joined by single hyphens. */
export const idSchema = z.string().regex(/^[a-z0-9]+(-[a-z0-9]+)*$/, "must be a lower-case hyphenated id");

/**
 * A safe relative asset path (§4, §20): no leading slash, no `..` segment, no
 * URL scheme, no backslash. The AssetResolver later maps this to a preview or
 * CDN URL; the package itself never resolves it.
 */
export const relativeAssetPathSchema = z
  .string()
  .min(1)
  .refine((p) => !p.startsWith("/"), "must not be absolute")
  .refine((p) => !p.includes("\\"), "must not contain backslashes")
  .refine((p) => !/^[a-z][a-z0-9+.-]*:\/\//i.test(p), "must not contain a URL scheme")
  .refine((p) => !p.split("/").includes(".."), "must not contain a parent-directory segment");

// Namespace ids all share idSchema's shape; distinct exports document intent and
// let later code read as the spec does. (Branding is documentation-only here.)
export const courseIdSchema = idSchema;
export const objectiveIdSchema = idSchema;
export const partIdSchema = idSchema;
export const sliceIdSchema = idSchema;
export const blockIdSchema = idSchema;
export const narrationIdSchema = idSchema;
export const workflowStepIdSchema = idSchema;

export type Id = z.infer<typeof idSchema>;
export type RelativeAssetPath = z.infer<typeof relativeAssetPathSchema>;
