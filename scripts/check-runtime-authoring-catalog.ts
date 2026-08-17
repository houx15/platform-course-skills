#!/usr/bin/env node
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import {
  BlockDefinition,
  ClosingDefinition,
  FillBlankAssessment,
  FillBlankCompletionRule,
  HTML_MESSAGE_PAYLOAD_SCHEMAS,
  InteractiveHtmlBlock,
  LayoutPreset,
  NarrationDefinition,
  NavigationDefinition,
  OpeningDefinition,
  SingleChoiceAssessment,
  SingleChoiceCompletionRule,
  SplitRatio,
  VideoInteractionActivity,
  WorkflowAction,
  WorkflowEventMatcher,
  WorkflowEventType,
} from "@mind-imprint/course-contract";
import { HOST_MESSAGE_TYPES } from "../packages/course-renderer/src/blocks/html/protocol";

type JsonObject = Record<string, any>;

const root = fileURLToPath(new URL("..", import.meta.url));
const catalogPath = fileURLToPath(
  new URL("../course_toolkit/runtime_authoring_catalog.json", import.meta.url),
);
const catalog = JSON.parse(readFileSync(catalogPath, "utf8")) as JsonObject;

function same(label: string, actual: unknown, expected: unknown): void {
  if (JSON.stringify(actual) !== JSON.stringify(expected)) {
    throw new Error(
      `${label} drifted\nexpected=${JSON.stringify(expected)}\nactual=${JSON.stringify(actual)}`,
    );
  }
}

function literal(schema: any): string {
  return schema.value ?? schema._def?.value;
}

function enumValues(schema: any): string[] {
  return [...(schema.options ?? schema._def?.values ?? [])];
}

function unwrap(schema: any): any {
  let current = schema;
  while (typeof current?.unwrap === "function") current = current.unwrap();
  return current;
}

function unionDiscriminators(schema: any, field: string): string[] {
  return schema.options.map((option: any) => literal(option.shape[field]));
}

function objectFieldCatalog(schema: any, excluded: string[] = []): { requiredFields: string[]; optionalFields: string[] } {
  const requiredFields: string[] = [];
  const optionalFields: string[] = [];
  for (const [field, value] of Object.entries(schema.shape)) {
    if (excluded.includes(field)) continue;
    if ((value as any).isOptional()) optionalFields.push(field);
    else requiredFields.push(field);
  }
  return { requiredFields, optionalFields };
}

const expectedTopLevel = [
  "authority",
  "blocks",
  "course",
  "layout",
  "narration",
  "navigation",
  "rendererCaveats",
  "schemaVersion",
  "slice",
  "targetContractVersion",
  "upstreamTag",
  "videoInteraction",
  "workflow",
];
same("top-level fields", Object.keys(catalog).sort(), expectedTopLevel);
same("upstream tag", catalog.upstreamTag, "course-authoring-v1.0.0");
same("layout presets", catalog.layout.presets, enumValues(LayoutPreset));
same("split ratios", catalog.layout.splitRatios, enumValues(SplitRatio));
same("block types", catalog.blocks.types, unionDiscriminators(BlockDefinition, "type"));

for (const option of (BlockDefinition as any).options) {
  const type = literal(option.shape.type);
  const fields = objectFieldCatalog(option, ["type"]);
  const expected = {
    requiredFields: ["id", "type", ...fields.requiredFields.filter((field) => field !== "id")],
    optionalFields: fields.optionalFields,
  };
  same(`${type} required fields`, catalog.blocks[type].requiredFields, expected.requiredFields);
  same(`${type} optional fields`, catalog.blocks[type].optionalFields, expected.optionalFields);
}

const blockByType = new Map(
  (BlockDefinition as any).options.map((option: any) => [literal(option.shape.type), option]),
);
same(
  "image presentations",
  catalog.blocks.images.presentations,
  enumValues(blockByType.get("images")!.shape.presentation),
);
same(
  "video completion rules",
  catalog.blocks.video.completionRules,
  unionDiscriminators(unwrap(blockByType.get("video")!.shape.completion), "rule"),
);
same(
  "html aspect ratios",
  catalog.blocks.interactiveHtml.aspectRatios,
  enumValues((InteractiveHtmlBlock as any).shape.aspectRatio),
);
same(
  "html frame message types",
  catalog.blocks.interactiveHtml.frameMessageTypes,
  Object.keys(HTML_MESSAGE_PAYLOAD_SCHEMAS),
);
same(
  "html host message types",
  catalog.blocks.interactiveHtml.hostMessageTypes,
  [...HOST_MESSAGE_TYPES],
);
same(
  "fill blank assessment modes",
  catalog.blocks.fillBlank.assessmentModes,
  unionDiscriminators(FillBlankAssessment, "mode"),
);
same(
  "fill blank completion rules",
  catalog.blocks.fillBlank.completionRules,
  unionDiscriminators(FillBlankCompletionRule, "rule"),
);
same(
  "single choice assessment modes",
  catalog.blocks.singleChoice.assessmentModes,
  unionDiscriminators(SingleChoiceAssessment, "mode"),
);
same(
  "single choice completion rules",
  catalog.blocks.singleChoice.completionRules,
  unionDiscriminators(SingleChoiceCompletionRule, "rule"),
);

const contractActions = (WorkflowAction as any).options.map((option: any) => {
  const fields = Object.entries(option.shape)
    .filter(([field]) => field !== "type")
    .map(([field, value]) => ({ field, optional: (value as any).isOptional() }));
  return {
    type: literal(option.shape.type),
    requiredFields: fields.filter((item) => !item.optional).map((item) => item.field),
    optionalFields: fields.filter((item) => item.optional).map((item) => item.field),
  };
});
same("workflow actions", catalog.workflow.actions, contractActions);
same("workflow events", catalog.workflow.events, enumValues(WorkflowEventType));
same("workflow matcher fields", catalog.workflow.matcherFields, Object.keys((WorkflowEventMatcher as any).shape));

same(
  "narration fields",
  {
    requiredFields: catalog.narration.requiredFields,
    optionalFields: catalog.narration.optionalFields,
  },
  objectFieldCatalog(NarrationDefinition),
);
same(
  "opening signals",
  catalog.course.openingSignals,
  enumValues((OpeningDefinition as any).shape.personalization.shape.allowedSignals.element),
);
same(
  "closing signals",
  catalog.course.closingSignals,
  enumValues((ClosingDefinition as any).shape.personalization.shape.allowedSignals.element),
);
same(
  "navigation manual next",
  catalog.navigation.manualNext,
  enumValues((NavigationDefinition as any).shape.manualNext),
);
same(
  "video interaction activities",
  catalog.videoInteraction.activityTypes,
  unionDiscriminators(VideoInteractionActivity, "type"),
);

const pdfRenderer = readFileSync(
  `${root}/packages/course-renderer/src/blocks/media/PdfRenderer.tsx`,
  "utf8",
);
const producerless = pdfRenderer.includes('"pdf.pageChanged"') ? [] : ["pdf.pageChanged"];
same(
  "renderer event caveats",
  catalog.rendererCaveats.workflowEventsWithoutProducer,
  producerless,
);

process.stdout.write(
  `${JSON.stringify({ ok: true, upstreamTag: catalog.upstreamTag }, null, 2)}\n`,
);
