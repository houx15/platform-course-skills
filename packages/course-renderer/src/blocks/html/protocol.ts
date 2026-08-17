import { HTML_MESSAGE_PAYLOAD_SCHEMAS, type HtmlMessagePayloadMap, type HtmlMessageType } from "@mind-imprint/course-contract";

/**
 * §17.11 / §20 — the versioned `postMessage` protocol for `interactiveHtml`
 * blocks. This module is PURE: no DOM, no iframe, no window access, so every
 * acceptance/rejection path is unit-testable independent of the renderer.
 *
 * The sandboxed frame speaks exactly one message shape:
 *
 *   { protocol: "mind-course-interaction"; version: "1.0";
 *     sessionToken: string; type: "ready"|"progress"|"completed"|"error";
 *     payload?: unknown }
 *
 * A message is ACCEPTED only if the protocol name matches, the version equals
 * the block's `expectedVersion`, the session token equals the per-mount minted
 * token, the `type` is one of the four known types, AND (P1-08) the `payload`
 * validates against that type's schema from `course-contract`'s
 * `HTML_MESSAGE_PAYLOAD_SCHEMAS` — e.g. a `completed` message with no
 * learning evidence fails here with reason `"payload"`. Anything rejected
 * NEVER becomes a runtime Event.
 */

export const PROTOCOL_NAME = "mind-course-interaction" as const;
export const PROTOCOL_VERSION = "1.0" as const;

/** The four message types the frame may send — kept in sync with course-contract's `HtmlMessageType`. */
export const FRAME_MESSAGE_TYPES = ["ready", "progress", "completed", "error"] as const satisfies readonly HtmlMessageType[];
export type FrameMessageType = (typeof FRAME_MESSAGE_TYPES)[number];

export interface ParseContext {
  /** The per-mount token minted by the renderer; the frame must echo it back. */
  sessionToken: string;
  /** The block's declared `protocolVersion` (currently always `"1.0"`). */
  expectedVersion: string;
}

/** Ordered so the caller can classify a rejection for diagnostics. `"payload"` is the P1-08 addition: envelope was fine, the payload itself didn't validate. */
export type RejectionReason = "shape" | "version" | "token" | "type" | "payload";

/** A discriminated union: `result.type` narrows `result.payload` to that type's validated shape. */
export type ParseResult =
  | { [K in FrameMessageType]: { ok: true; type: K; payload: HtmlMessagePayloadMap[K] } }[FrameMessageType]
  | { ok: false; reason: RejectionReason };

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isKnownType(value: unknown): value is FrameMessageType {
  return typeof value === "string" && (FRAME_MESSAGE_TYPES as readonly string[]).includes(value);
}

/**
 * Validates a raw `postMessage` payload against the protocol. `shape` covers a
 * non-object or a wrong/absent protocol name (the message is not even ours);
 * the remaining reasons are checked in a fixed order (version → token → type
 * → payload) so the outcome is deterministic.
 */
export function parseFrameMessage(raw: unknown, ctx: ParseContext): ParseResult {
  if (!isRecord(raw)) return { ok: false, reason: "shape" };
  if (raw.protocol !== PROTOCOL_NAME) return { ok: false, reason: "shape" };
  if (raw.version !== ctx.expectedVersion) return { ok: false, reason: "version" };
  if (raw.sessionToken !== ctx.sessionToken) return { ok: false, reason: "token" };
  if (!isKnownType(raw.type)) return { ok: false, reason: "type" };
  const schema = HTML_MESSAGE_PAYLOAD_SCHEMAS[raw.type];
  const parsed = schema.safeParse(raw.payload);
  if (!parsed.success) return { ok: false, reason: "payload" };
  // Cast is safe: `raw.type` was just narrowed to `FrameMessageType` above, and
  // `schema` was looked up BY that same `raw.type`, so `parsed.data`'s runtime
  // shape matches `HtmlMessagePayloadMap[raw.type]` — TS just can't correlate
  // the two through a dynamic object-index lookup.
  return { ok: true, type: raw.type, payload: parsed.data } as ParseResult;
}

/**
 * P1-09 / D3 — the host→frame half of the protocol: a small, versioned
 * lifecycle the renderer posts to the iframe on runtime transitions (block
 * shown/hidden, enabled/disabled, slice left). Authored HTML MAY listen for
 * these to pause/resume its own audio and stop responding to input, but the
 * host never depends on that cooperation for `enabled=false` enforcement —
 * that's done host-side (pointer-events/overlay). Same protocol name/version
 * identity as the frame→host handshake, so a frame can validate host
 * messages the same way the host validates frame messages.
 */
export const HOST_MESSAGE_TYPES = [
  "activate",
  "deactivate",
  "enable",
  "disable",
  "pauseMedia",
  "resumeMedia",
  "stopMedia",
] as const;
export type HostMessageType = (typeof HOST_MESSAGE_TYPES)[number];

export interface HostMessage {
  protocol: typeof PROTOCOL_NAME;
  version: typeof PROTOCOL_VERSION;
  sessionToken: string;
  type: HostMessageType;
}

/** Builds one host→frame lifecycle message. */
export function buildHostMessage(type: HostMessageType, sessionToken: string): HostMessage {
  return { protocol: PROTOCOL_NAME, version: PROTOCOL_VERSION, sessionToken, type };
}
