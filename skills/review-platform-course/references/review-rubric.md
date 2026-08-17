# CourseDefinition 2.0 independent review rubric

## Evidence boundary

The current `course/course.json`, G6 validation report, G7 preview manifest, Blueprint, sources, decisions, unresolved items, and annotations must agree by hash. A legacy 1.0/1.1 report is `migration-required` and cannot certify CourseDefinition 2.0. ZIP files are ignored.

## Part dimensions

For each Part, record `pass|revise` and specific evidence for:

1. `instructionalGoalStructure`: objectives are explicit; Slices form an intelligible sequence; each Slice contributes to the Part goal.
2. `contentCompleteness`: explanations, examples, instructions, and synthesis are sufficient; source evidence is not flattened or omitted.
3. `studentFacingPresentation`: learner text contains no teacher notes, AI rules, implementation detail, or source-coverage commentary.
4. `modalityChoice`: text, images, `pdf`, video, HTML, and questions each serve the learning action; one Slice remains legible on one desktop screen.
5. `practiceFeedback`: evidence comes after adequate teaching, answers/rubrics and feedback are valid, and completion rules reflect the intended learning action.
6. `resourcesFormat`: all references are safe, current, complete, accessible, and consistent with the confirmed Blueprint and source.

Each Slice also requires explicit review of content purpose, layout, workflow reachability, interaction completion, and media behavior. Exercise meaningful branches in G7 rather than inspecting only the initial state.

## Objective evidence

Every objective must be listed once with the exact contract `evidenceBlockIds`. Every evidence Block must be inside a Part whose `objectiveIds` includes that objective and must collect a result. `fillBlank`, `singleChoice`, result-producing `interactiveHtml`, and video interaction can count. Static text, images, or PDF alone cannot.

## Media

- PDF: preserve the 完整文档 bytes; require `.pdf`, `%PDF-`, `%%EOF`, learner-facing purpose, G6 integrity, and G7 embedded reading/download behavior. Static checks cannot prove every page renders or the edition is authoritative.
- Video: require MP4/H.264, AAC when audio exists, faststart, correct duration, in-range cues, required-cue completion, and G7 auto-pause/modal behavior. `unsupported-video-codec`, `unsupported-audio-codec`, and `missing-faststart` block. Report `long-video` and `large-video` separately.
- HTML: require the declared completion/student-data message contract, current source hash, safe iframe behavior, and G7 evidence. Verify audio lifecycle when `capabilities.audio` is true. Visible text follows 16px / 14px rules. Static validation never substitutes for the 真实 iframe.

## Overall checks

All of these must pass with evidence: `allPartsPass`, `sourceClassificationCoverage`, `teacherDecisions`, `resourcesPresent`, `courseContract`, `objectiveEvidence`, `layoutWorkflow`, `pdf`, `video`, `html`, `previewRuntime`, and `unresolved`.

Any `revise`, stale hash, runtime error, open required annotation, unresolved runtime bug, pending decision, blocking unresolved item, missing asset, or invalid completion path yields `blocked`. A polished preview cannot override missing evidence.
