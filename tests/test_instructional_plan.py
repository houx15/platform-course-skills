import copy
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from course_toolkit.jsonio import load_json, write_json_atomic

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def coverage_document():
    return {
        "schemaVersion": "2.0",
        "items": [
            {
                "sourceId": "source-claim",
                "sourceFile": "materials/claim.pdf",
                "location": "page:2/figure:1",
                "summary": "待检验的主张",
                "disposition": "required-core",
                "bindings": [{"partId": "part-evidence", "sliceId": "slice-compare", "blockId": "claim-block"}],
            },
            {
                "sourceId": "source-image",
                "sourceFile": "materials/chart.png",
                "location": "image:chart-1",
                "summary": "对比图",
                "disposition": "required-evidence",
                "bindings": [{"partId": "part-evidence", "sliceId": "slice-compare", "blockId": "image-block"}],
            },
            {
                "sourceId": "source-support",
                "sourceFile": "materials/extra.pdf",
                "location": "page:9",
                "summary": "延伸材料",
                "disposition": "optional-support",
                "reason": "本课时间有限",
                "bindings": [],
            },
            {
                "sourceId": "source-authoring",
                "sourceFile": "materials/guide.docx",
                "location": "paragraph:3",
                "summary": "教师备课提示",
                "disposition": "authoring-only",
                "reason": "仅供教师备课",
                "bindings": [],
            },
            {
                "sourceId": "source-exclude",
                "sourceFile": "materials/outdated.pdf",
                "location": "page:1",
                "summary": "过时示例",
                "disposition": "exclude-proposed",
                "reason": "证据已过时",
                "bindings": [],
            },
        ],
    }


def extracted_document():
    return {
        "schemaVersion": "1.0",
        "items": [
            {
                "sourceId": item["sourceId"],
                "sourceFile": item["sourceFile"],
                "location": item["location"],
                "kind": "file",
                "text": item["summary"],
            }
            for item in coverage_document()["items"]
        ],
        "ignored": [],
        "unsupported": [],
        "errors": [],
    }


def plan_document():
    return {
        "schemaVersion": "2.0",
        "title": "证据判断",
        "parts": [
            {
                "partId": "part-evidence",
                "title": "看证据",
                "slices": [
                    {
                        "partId": "part-evidence",
                        "sliceId": "slice-compare",
                        "title": "比较主张和图表",
                        "teachingPurpose": "让学生用图表检查主张是否站得住。",
                        "sourceUses": [
                            {
                                "sourceId": "source-claim",
                                "locator": "page:2/figure:1",
                                "materialRole": "待检验主张",
                            },
                            {
                                "sourceId": "source-image",
                                "locator": "image:chart-1",
                                "materialRole": "比较证据",
                            },
                        ],
                        "learnerSees": "主张、图表和一个回答框。",
                        "learnerAction": {
                            "kind": "answer",
                            "description": "比较图表后写出判断。",
                            "referencePolicy": "co-visible",
                            "referenceSourceIds": ["source-image"],
                            "targetId": "question:compare-claim",
                        },
                        "completionEvidence": "提交一条引用图表的判断。",
                        "layoutIntent": {"preset": "split-horizontal", "ratio": "1:1"},
                        "coVisibleRequirements": [
                            {
                                "sourceId": "source-image",
                                "targetId": "question:compare-claim",
                                "reason": "回答时需要直接阅读图表。",
                            }
                        ],
                        "imageRelationships": [
                            {
                                "sourceId": "source-image",
                                "targetType": "claim",
                                "targetId": "claim:main",
                                "relationship": "用图表检验主张",
                            }
                        ],
                        "unresolvedBlockers": [],
                        "proposedExclusions": ["source-exclude"],
                    }
                ],
            }
        ],
    }


def teaching_plan_document():
    plan = plan_document()
    plan["teachingDesign"] = {
        "essentialQuestion": "怎样用证据判断一个公开主张是否站得住？",
        "learnerStartingPoint": "学生容易凭主张的语气或单一图表快速下结论。",
        "learnerDestination": "学生能够使用证据核查步骤，并把方法迁移到新的公开主张。",
        "methodologies": [
            {
                "id": "evidence-check",
                "name": "证据核查",
                "purpose": "把直觉判断转化为可复核的证据判断。",
                "steps": [
                    {
                        "id": "evidence-compare",
                        "name": "主张—证据对照",
                        "learnerCapability": "指出证据支持、限制或无法回答主张的部分。",
                    }
                ],
                "commonMistakes": ["只复述图表，不说明它与主张的关系。"],
            }
        ],
        "casePractice": {
            "anchorCase": "一条带图表的公开主张",
            "caseRole": "让学生跟随示范完成一次完整证据核查。",
            "transferTask": "独立判断另一条公开主张并说明证据边界。",
        },
        "cumulativeArtifact": {
            "name": "证据判断记录",
            "description": "持续记录主张、证据、判断和仍需核查的信息。",
        },
        "learningArc": [
            {
                "id": "phase-learn",
                "title": "学习核查方法",
                "instructionalRoles": ["teach", "model"],
                "methodStepIds": ["evidence-compare"],
                "learnerStartsWith": "只有直觉判断。",
                "learnerDoes": "观看一次主张—证据对照示范。",
                "learnerLeavesWith": "知道核查时要同时写出支持和边界。",
                "artifactUpdate": "建立证据判断记录的四个栏位。",
            },
            {
                "id": "phase-practise",
                "title": "跟随案例练习",
                "instructionalRoles": ["guided-practice"],
                "methodStepIds": ["evidence-compare"],
                "learnerStartsWith": "知道步骤但尚未自己使用。",
                "learnerDoes": "比较主张与图表并写出判断。",
                "learnerLeavesWith": "完成一条有证据边界的判断。",
                "artifactUpdate": "填写案例的主张、证据和判断。",
            },
            {
                "id": "phase-transfer",
                "title": "迁移到新主张",
                "instructionalRoles": ["transfer"],
                "methodStepIds": ["evidence-compare"],
                "learnerStartsWith": "已经在示范案例中完成核查。",
                "learnerDoes": "独立核查一个新的公开主张。",
                "learnerLeavesWith": "能够不依赖示范迁移核查方法。",
                "artifactUpdate": "新增一条独立核查记录。",
            },
        ],
        "studentPerspectiveReview": {
            "status": "ready-for-teacher",
            "studentJourneySummary": "先理解方法并看示范，再跟随案例练习，最后独立迁移。",
            "checks": [
                {"criterion": criterion, "status": "pass", "evidence": f"已具体检查 {criterion}。"}
                for criterion in (
                    "purpose-clarity",
                    "method-before-practice",
                    "scaffolding",
                    "assessment-load",
                    "cumulative-progress",
                    "motivation-and-pacing",
                    "transfer",
                )
            ],
            "revisionsMade": ["将原来连续两道题改为方法示范、案例练习和迁移。"],
            "remainingConcerns": [],
        },
    }
    practice_slice = plan["parts"][0]["slices"][0]
    practice_slice.update({
        "arcPhaseId": "phase-practise",
        "instructionalRole": "guided-practice",
        "methodStepIds": ["evidence-compare"],
        "learnerStateBefore": "知道证据核查步骤，但尚未自己使用。",
        "learnerStateAfter": "能够在提示下写出证据支持与边界。",
        "artifactUpdate": "完成示范案例的证据判断记录。",
        "whyOwnSlice": "需要让图表和作答区同屏，集中完成第一次方法练习。",
    })
    model_slice = {
        "partId": "part-evidence",
        "sliceId": "slice-model",
        "title": "示范如何核查主张",
        "teachingPurpose": "讲清证据核查步骤并展示完整思考过程。",
        "sourceUses": [],
        "learnerSees": "一份逐步展开的主张—证据对照示范。",
        "learnerAction": {"kind": "observe", "description": "跟随示范标记支持与边界。", "referencePolicy": "none", "referenceSourceIds": []},
        "completionEvidence": {"event": "block.completed"},
        "layoutIntent": {"preset": "full"},
        "coVisibleRequirements": [],
        "imageRelationships": [],
        "unresolvedBlockers": [],
        "proposedExclusions": [],
        "arcPhaseId": "phase-learn",
        "instructionalRole": "model",
        "methodStepIds": ["evidence-compare"],
        "learnerStateBefore": "只有直觉判断。",
        "learnerStateAfter": "知道核查步骤和完整判断的结构。",
        "artifactUpdate": "建立证据判断记录的四个栏位。",
        "whyOwnSlice": "完整示范需要独立呈现，避免和首次作答竞争注意力。",
    }
    transfer_slice = {
        **copy.deepcopy(model_slice),
        "sliceId": "slice-transfer",
        "title": "独立核查新主张",
        "teachingPurpose": "检验学生能否把证据核查方法迁移到新情境。",
        "learnerSees": "一条新的公开主张及其证据。",
        "learnerAction": {"kind": "answer", "description": "独立写出证据判断和边界。", "referencePolicy": "none", "referenceSourceIds": []},
        "completionEvidence": {"artifact": "提交一条新的证据判断记录。"},
        "arcPhaseId": "phase-transfer",
        "instructionalRole": "transfer",
        "learnerStateBefore": "已经在示范案例中完成核查。",
        "learnerStateAfter": "能够独立迁移证据核查方法。",
        "artifactUpdate": "新增一条独立核查记录。",
        "whyOwnSlice": "迁移任务必须与示范案例分开，才能观察独立应用。",
    }
    plan["parts"][0]["slices"] = [model_slice, practice_slice, transfer_slice]
    plan["sliceSemanticReview"] = {
        "status": "ready-for-teacher",
        "summary": "三页依次完成方法示范、带练和独立迁移，每一页都说明当前方法位置和学习结果的去向。",
        "sliceChecks": [
            {
                "sliceId": slice_data["sliceId"],
                "status": "pass",
                "context": f"已交代 {slice_data['title']} 所承接的已有理解。",
                "frameworkPosition": f"位于 {slice_data['arcPhaseId']} 阶段。",
                "purpose": slice_data["teachingPurpose"],
                "evidence": f"学生看到的内容和行动共同支持 {slice_data['title']}。",
                "revision": None,
            }
            for slice_data in plan["parts"][0]["slices"]
        ],
        "transitionChecks": [
            {
                "fromSliceId": "slice-model",
                "toSliceId": "slice-compare",
                "status": "pass",
                "connection": "学生把示范中的主张—证据对照步骤用于第一次带练。",
                "evidence": "前页形成判断结构，后页要求依照同一结构提交判断。",
                "revision": None,
            },
            {
                "fromSliceId": "slice-compare",
                "toSliceId": "slice-transfer",
                "status": "pass",
                "connection": "学生把带练中完成的证据判断迁移到新主张。",
                "evidence": "前页提供有支架练习，后页移除支架并保持同一方法。",
                "revision": None,
            },
        ],
        "revisionsMade": ["补充每页的课程位置、承接关系和下一步用途。"],
    }
    return plan


def write_root(root: Path, *, plan=None, coverage=None, extracted=None):
    """Create a fixture only inside an explicit temporary course root.

    A prior manual test probe passed the repository directory here, leaving a
    root-level ``.course-work`` fixture behind.  Keep the helper deliberately
    unable to write into this repository so focused test reruns cannot repeat
    that leak.
    """
    if root.resolve() == REPOSITORY_ROOT:
        raise AssertionError("fixture root must not be the repository root")
    course_path = root / "course" / "course.json"
    if plan is None and coverage is None and extracted is None and course_path.is_file():
        course = load_json(course_path)["course"]
        parts = []
        for part in course["parts"]:
            slices = []
            for slice_data in part["slices"]:
                layout = slice_data["layout"]
                intent = {"preset": layout["preset"]}
                if "ratio" in layout:
                    intent["ratio"] = layout["ratio"]
                slices.append({"partId": part["id"], "sliceId": slice_data["id"], "title": slice_data["title"], "teachingPurpose": "Practice the course objective.", "sourceUses": [], "learnerSees": "Prepared learning content.", "learnerAction": {"kind": "answer", "description": "Choose an answer.", "referencePolicy": "none", "referenceSourceIds": []}, "completionEvidence": {"event": "block.completed"}, "layoutIntent": intent, "coVisibleRequirements": [], "imageRelationships": [], "unresolvedBlockers": [], "proposedExclusions": []})
            parts.append({"partId": part["id"], "title": part["title"], "slices": slices})
        plan = {"schemaVersion": "2.0", "title": "Current fixture plan", "parts": parts}
        coverage = {"schemaVersion": "2.0", "items": []}
        extracted = {"schemaVersion": "1.0", "items": [], "ignored": [], "unsupported": [], "errors": []}
    write_json_atomic(root / ".course-work/course-storyboard.json", plan or plan_document())
    write_json_atomic(root / ".course-work/source-coverage.json", coverage or coverage_document())
    write_json_atomic(root / ".course-work/materials-extracted.json", extracted or extracted_document())


def write_valid_media_design(root: Path) -> None:
    """Write the focused G4 media/narration plan used by workflow fixtures."""
    from course_toolkit.instructional_plan import plan_content_hash
    from course_toolkit.workflow import MEDIA_KINDS_BY_EXTENSION

    plan = load_json(root / ".course-work/course-storyboard.json")
    coverage = load_json(root / ".course-work/source-coverage.json")
    source_by_id = {item["sourceId"]: item for item in coverage["items"]}
    items = []
    narrations = []
    for part in plan["parts"]:
        for slice_data in part["slices"]:
            narrations.append(
                {
                    "partId": slice_data["partId"],
                    "sliceId": slice_data["sliceId"],
                    "status": "planned",
                }
            )
            for source_use in slice_data["sourceUses"]:
                source = source_by_id[source_use["sourceId"]]
                source_path = source["sourceFile"]
                kind = MEDIA_KINDS_BY_EXTENSION.get(Path(source_path).suffix.lower())
                if kind is None:
                    continue
                asset = root / source_path
                asset.parent.mkdir(parents=True, exist_ok=True)
                asset.write_bytes(b"fixture media source")
                items.append(
                    {
                        "sourceId": source_use["sourceId"],
                        "partId": slice_data["partId"],
                        "sliceId": slice_data["sliceId"],
                        "kind": kind,
                        "sourcePath": source_path,
                        "status": "planned",
                    }
                )
    write_json_atomic(
        root / ".course-work/media-design.json",
        {
            "schemaVersion": "1.0",
            "planContentHash": plan_content_hash(plan),
            "items": items,
            "narrations": narrations,
        },
    )


class InstructionalPlanTests(unittest.TestCase):
    def api(self):
        import course_toolkit.instructional_plan as api

        return api

    def test_complete_plan_validates_and_requires_a_slice_per_part(self):
        self.assertEqual(self.api().validate_instructional_plan(plan_document(), coverage_document()), [])
        empty = plan_document()
        empty["parts"][0]["slices"] = []
        self.assertIn("part-slices-required", {issue.code for issue in self.api().validate_instructional_plan(empty, coverage_document())})

    def test_new_teaching_design_plan_validates_and_renders_before_page_rows(self):
        data = teaching_plan_document()
        self.assertEqual(self.api().validate_instructional_plan(data, coverage_document()), [])
        rendered = self.api().render_teacher_plan(data, coverage_document())
        self.assertLess(rendered.index("## 教学设计总图"), rendered.index("## 逐页计划"))
        self.assertIn("### 核心方法论", rendered)
        self.assertIn("### 学生视角预审", rendered)
        self.assertIn("证据核查", rendered)
        self.assertIn("只有直觉判断。 → 知道核查步骤和完整判断的结构。", rendered)

    def test_teaching_design_requires_student_review_before_teacher_confirmation(self):
        data = teaching_plan_document()
        del data["teachingDesign"]["studentPerspectiveReview"]
        codes = {issue.code for issue in self.api().validate_instructional_plan(data, coverage_document())}
        self.assertIn("student-review-required", codes)

        data = teaching_plan_document()
        data["teachingDesign"]["studentPerspectiveReview"]["checks"][0]["status"] = "revise"
        codes = {issue.code for issue in self.api().validate_instructional_plan(data, coverage_document())}
        self.assertIn("student-review-not-ready", codes)

    def test_new_plan_semantic_review_covers_every_slice_and_adjacent_transition(self):
        data = teaching_plan_document()
        self.assertEqual(self.api().validate_instructional_plan(data, coverage_document()), [])
        rendered = self.api().render_teacher_plan(data, coverage_document())
        self.assertLess(rendered.index("## Slice 语义连贯性审查"), rendered.index("## 逐页计划"))
        self.assertIn("### 单页清晰性", rendered)
        self.assertIn("### 相邻页衔接", rendered)
        self.assertIn("slice&#45;model → slice&#45;compare", rendered)

        missing_slice = teaching_plan_document()
        missing_slice["sliceSemanticReview"]["sliceChecks"].pop()
        codes = {issue.code for issue in self.api().validate_instructional_plan(missing_slice, coverage_document())}
        self.assertIn("semantic-slice-coverage-mismatch", codes)

        wrong_transition = teaching_plan_document()
        wrong_transition["sliceSemanticReview"]["transitionChecks"][0]["toSliceId"] = "slice-transfer"
        codes = {issue.code for issue in self.api().validate_instructional_plan(wrong_transition, coverage_document())}
        self.assertIn("semantic-transition-coverage-mismatch", codes)

        across_parts = teaching_plan_document()
        transfer_slice = across_parts["parts"][0]["slices"].pop()
        transfer_slice["partId"] = "part-transfer"
        across_parts["parts"].append({"partId": "part-transfer", "title": "独立迁移", "slices": [transfer_slice]})
        self.assertEqual(self.api().validate_instructional_plan(across_parts, coverage_document()), [])

    def test_semantic_review_requires_concrete_evidence_and_consistent_status(self):
        data = teaching_plan_document()
        check = data["sliceSemanticReview"]["sliceChecks"][0]
        check["status"] = "revise"
        check["evidence"] = ""
        check["revision"] = ""
        data["sliceSemanticReview"]["status"] = "revise"
        codes = {issue.code for issue in self.api().validate_instructional_plan(data, coverage_document())}
        self.assertTrue({"semantic-review-evidence-required", "semantic-review-revision-required", "semantic-review-not-ready"}.issubset(codes))

    def test_teaching_design_rejects_question_first_or_unpractised_method_steps(self):
        data = teaching_plan_document()
        data["parts"][0]["slices"][0]["instructionalRole"] = "feedback"
        data["teachingDesign"]["learningArc"][0]["instructionalRoles"] = ["feedback"]
        codes = {issue.code for issue in self.api().validate_instructional_plan(data, coverage_document())}
        self.assertIn("method-step-not-taught", codes)

        data = teaching_plan_document()
        data["parts"][0]["slices"] = data["parts"][0]["slices"][:1]
        codes = {issue.code for issue in self.api().validate_instructional_plan(data, coverage_document())}
        self.assertTrue({"arc-phase-unused", "method-step-not-practised", "transfer-slice-required"}.issubset(codes))

    def test_teaching_design_is_additive_for_existing_courses(self):
        self.assertNotIn("teachingDesign", plan_document())
        self.assertNotIn("sliceSemanticReview", plan_document())
        self.assertEqual(self.api().validate_instructional_plan(plan_document(), coverage_document()), [])

        legacy_teaching_plan = teaching_plan_document()
        del legacy_teaching_plan["sliceSemanticReview"]
        self.assertEqual(self.api().validate_instructional_plan(legacy_teaching_plan, coverage_document()), [])

    def test_fixture_writer_refuses_repository_root(self):
        with self.assertRaisesRegex(AssertionError, "must not be the repository root"):
            write_root(REPOSITORY_ROOT)
        self.assertFalse((REPOSITORY_ROOT / ".course-work").exists())

    def test_duplicate_part_or_slice_identity_is_rejected(self):
        data = plan_document()
        data["parts"].append(copy.deepcopy(data["parts"][0]))
        codes = {issue.code for issue in self.api().validate_instructional_plan(data, coverage_document())}
        self.assertIn("duplicate-part-id", codes)
        self.assertIn("duplicate-slice-id", codes)

    def test_part_and_slice_ids_use_pinned_lowercase_hyphenated_grammar(self):
        for invalid in (" Part", "part ", "Part-evidence", "part_evidence", "part/evidence"):
            with self.subTest(invalid=invalid):
                data = plan_document()
                data["parts"][0]["partId"] = invalid
                data["parts"][0]["slices"][0]["partId"] = invalid
                data["parts"][0]["slices"][0]["sliceId"] = invalid
                self.assertIn("invalid-stable-id", {issue.code for issue in self.api().validate_instructional_plan(data, coverage_document())})

    def test_teacher_markdown_highlights_only_unused_visual_and_interactive_media(self):
        coverage = coverage_document()
        coverage["items"].extend([
            {
                "sourceId": "source-exclude-approved",
                "sourceFile": "materials/duplicate.pdf",
                "location": "page:4",
                "summary": "重复内容",
                "disposition": "exclude-approved",
                "reason": "与核心证据重复",
                "bindings": [],
            },
            {
                "sourceId": "source-unused-image",
                "sourceFile": "materials/unused.webp",
                "location": "image:1",
                "summary": "未采用图片",
                "disposition": "exclude-proposed",
                "reason": "与核心案例无关",
                "bindings": [],
            },
            {
                "sourceId": "source-unused-html",
                "sourceFile": "materials/unused.html",
                "location": "document",
                "summary": "未采用互动",
                "disposition": "authoring-only",
                "reason": "仅用于备课",
                "bindings": [],
            },
            {
                "sourceId": "source-unused-video",
                "sourceFile": "materials/unused.mp4",
                "location": "full",
                "summary": "未采用视频",
                "disposition": "optional-support",
                "reason": "课程时长有限",
                "bindings": [],
            },
        ])
        rendered = self.api().render_teacher_plan(plan_document(), coverage)
        self.assertIn("| 教学目的 |", rendered)
        self.assertIn("未使用或仅用于备课的图片、HTML、视频", rendered)
        unused = rendered.split("## 未使用或仅用于备课", 1)[1]
        for source_id in ("source&#45;unused&#45;image", "source&#45;unused&#45;html", "source&#45;unused&#45;video"):
            self.assertIn(source_id, rendered)
        for source_id in ("source&#45;support", "source&#45;authoring", "source&#45;exclude", "source&#45;exclude&#45;approved"):
            self.assertNotIn(source_id, unused)
        self.assertNotIn("G0", rendered)
        self.assertNotIn("workflow", rendered.lower())

    def test_teacher_table_has_exactly_thirteen_cells_per_header_delimiter_and_row(self):
        rendered = self.api().render_teacher_plan(plan_document(), coverage_document())
        table = rendered.split("## 逐页计划", 1)[1].split("## 页面细节", 1)[0]
        rows = [line for line in table.splitlines() if line.startswith("|")]
        self.assertGreaterEqual(len(rows), 3)
        for row in rows:
            self.assertEqual(len(row.split("|")[1:-1]), 13, row)

    def test_new_plan_can_make_the_student_journey_visible_without_invalidating_legacy_plans(self):
        plan = teaching_plan_document()
        plan["parts"][0]["slices"][0]["journeyContext"] = {
            "coursePosition": "方法一：证据核查 / 示范",
            "connectionFromPrevious": "课程总览已经说明今天要学会把直觉变成可复核判断。",
            "currentFocus": "现在先看完整示范，认识主张—证据对照。",
            "setsUpNext": "下一页将用同一方法完成第一次带练。",
        }

        self.assertEqual(self.api().validate_instructional_plan(plan, coverage_document()), [])
        rendered = self.api().render_teacher_plan(plan, coverage_document())
        self.assertIn("课程位置与衔接", rendered)
        self.assertIn("方法一：证据核查 &#47; 示范", rendered)

        legacy = teaching_plan_document()
        self.assertEqual(self.api().validate_instructional_plan(legacy, coverage_document()), [])

    def test_unbound_optional_source_use_is_rejected_and_never_rendered_as_unused(self):
        coverage = coverage_document()
        plan = plan_document()
        plan["parts"][0]["slices"][0]["sourceUses"].append({"sourceId": "source-support", "locator": "page:9", "materialRole": "可选延伸"})
        self.assertIn("plan-source-use-unbound", {issue.code for issue in self.api().validate_instructional_plan(plan, coverage)})
        unused = self.api().render_teacher_plan(plan, coverage).split("## 未使用或仅用于备课", 1)[1]
        self.assertNotIn("source&#45;support", unused)
        coverage["items"][2]["bindings"] = [{"partId": "part-evidence", "sliceId": "slice-compare", "blockId": "support-block"}]
        unused = self.api().render_teacher_plan(plan, coverage).split("## 未使用或仅用于备课", 1)[1]
        self.assertNotIn("source&#45;support", unused)

    def test_authoring_or_excluded_material_cannot_be_learner_source_use(self):
        coverage = coverage_document()
        coverage["items"].append({"sourceId": "source-exclude-approved", "sourceFile": "materials/duplicate.pdf", "location": "page:4", "summary": "重复内容", "disposition": "exclude-approved", "reason": "重复", "decisionId": "decision-1", "teacherConfirmed": True, "bindings": []})
        for source_id in ("source-authoring", "source-exclude", "source-exclude-approved"):
            with self.subTest(source_id=source_id):
                data = plan_document()
                item = next(item for item in coverage["items"] if item["sourceId"] == source_id)
                data["parts"][0]["slices"][0]["sourceUses"].append({"sourceId": source_id, "locator": item["location"], "materialRole": "不应面向学生"})
                self.assertIn("learner-source-disposition-forbidden", {issue.code for issue in self.api().validate_instructional_plan(data, coverage)})

    def test_unknown_source_empty_purpose_and_action_are_rejected(self):
        data = plan_document()
        slice_data = data["parts"][0]["slices"][0]
        slice_data["sourceUses"][0]["sourceId"] = "missing"
        slice_data["teachingPurpose"] = ""
        slice_data["learnerAction"] = {"kind": "answer", "description": ""}
        codes = {issue.code for issue in self.api().validate_instructional_plan(data, coverage_document())}
        self.assertTrue({"unknown-source", "required"}.issubset(codes))

    def test_source_use_preserves_coverage_locator_and_material_role(self):
        data = plan_document()
        source_use = data["parts"][0]["slices"][0]["sourceUses"][0]
        source_use["locator"] = "page:99"
        source_use["materialRole"] = ""
        codes = {issue.code for issue in self.api().validate_instructional_plan(data, coverage_document())}
        self.assertIn("source-locator-mismatch", codes)
        self.assertIn("required", codes)

    def test_answer_requires_concrete_evidence_and_reference_requires_visibility(self):
        data = plan_document()
        slice_data = data["parts"][0]["slices"][0]
        slice_data["completionEvidence"] = ""
        slice_data["coVisibleRequirements"] = []
        codes = {issue.code for issue in self.api().validate_instructional_plan(data, coverage_document())}
        self.assertIn("completion-evidence-required", codes)
        self.assertIn("reference-not-covisible", codes)

    def test_explicit_dependency_is_allowed_but_assessment_backtracking_is_not(self):
        data = plan_document()
        action = data["parts"][0]["slices"][0]["learnerAction"]
        data["parts"][0]["slices"][0]["coVisibleRequirements"] = []
        action["referencePolicy"] = "justified-dependency"
        action["dependencyJustification"] = "学生已在纸质材料上标注同一张图表。"
        self.assertNotIn("reference-not-covisible", {issue.code for issue in self.api().validate_instructional_plan(data, coverage_document())})
        action["dependencyJustification"] = "学生可以回看上一页图表。"
        self.assertIn("invalid-dependency", {issue.code for issue in self.api().validate_instructional_plan(data, coverage_document())})

    def test_reference_wording_cannot_bypass_closed_reference_policy_or_target_linkage(self):
        data = plan_document()
        action = data["parts"][0]["slices"][0]["learnerAction"]
        action["referencePolicy"] = "none"
        action["referenceSourceIds"] = []
        action.pop("targetId")
        action["description"] = "先查看材料图表，再写出判断。"
        data["parts"][0]["slices"][0]["coVisibleRequirements"] = []
        self.assertIn("reference-policy-inconsistent", {issue.code for issue in self.api().validate_instructional_plan(data, coverage_document())})
        action["referencePolicy"] = "co-visible"
        action["referenceSourceIds"] = ["source-image"]
        action["targetId"] = "question:compare-claim"
        data["parts"][0]["slices"][0]["coVisibleRequirements"] = [{"sourceId": "source-image", "targetId": "claim:other", "reason": "错误关联"}]
        codes = {issue.code for issue in self.api().validate_instructional_plan(data, coverage_document())}
        self.assertIn("reference-not-covisible", codes)
        self.assertIn("covisible-target-mismatch", codes)

    def test_invalid_layout_preset_and_ratio_are_rejected(self):
        data = plan_document()
        data["parts"][0]["slices"][0]["layoutIntent"] = {"preset": "stack", "ratio": "5:4"}
        codes = {issue.code for issue in self.api().validate_instructional_plan(data, coverage_document())}
        self.assertIn("invalid-layout-preset", codes)
        self.assertIn("invalid-layout-ratio", codes)

    def test_image_and_proposed_exclusion_relationships_must_be_known_and_stable(self):
        data = plan_document()
        slice_data = data["parts"][0]["slices"][0]
        slice_data["imageRelationships"][0]["sourceId"] = "missing"
        slice_data["imageRelationships"][0]["targetId"] = ""
        slice_data["proposedExclusions"] = ["source-support"]
        codes = {issue.code for issue in self.api().validate_instructional_plan(data, coverage_document())}
        self.assertTrue({"unknown-source", "stable-target-required", "invalid-proposed-exclusion"}.issubset(codes))

    def test_content_hash_excludes_approval_but_not_plan_body(self):
        api = self.api()
        data = plan_document()
        first = api.plan_content_hash(data)
        data["approval"] = {"teacherConfirmed": True, "decisionId": "decision-1"}
        self.assertEqual(first, api.plan_content_hash(data))
        data["parts"][0]["slices"][0]["title"] = "改过的标题"
        self.assertNotEqual(first, api.plan_content_hash(data))

    def test_coverage_bindings_and_source_uses_must_share_part_slice_placement(self):
        coverage = coverage_document()
        coverage["items"][0]["bindings"][0]["sliceId"] = "slice-other"
        codes = {issue.code for issue in self.api().validate_instructional_plan(plan_document(), coverage)}
        self.assertIn("coverage-binding-plan-mismatch", codes)
        self.assertIn("plan-source-use-binding-mismatch", codes)
        self.assertNotIn("coverage-binding-plan-mismatch", {issue.code for issue in self.api().validate_instructional_plan(plan_document(), coverage_document())})

    def test_unknown_plan_fields_and_unknown_approval_metadata_are_rejected(self):
        data = plan_document()
        slice_data = data["parts"][0]["slices"][0]
        data["runtime"] = True
        data["parts"][0]["runtime"] = True
        slice_data["runtime"] = True
        slice_data["sourceUses"][0]["runtime"] = True
        slice_data["learnerAction"]["runtime"] = True
        slice_data["completionEvidence"] = {"description": "提交回答", "runtime": True}
        slice_data["layoutIntent"]["runtime"] = True
        slice_data["coVisibleRequirements"][0]["runtime"] = True
        slice_data["imageRelationships"][0]["runtime"] = True
        slice_data["unresolvedBlockers"] = [{"id": "blocker", "reason": "待确认", "runtime": True}]
        slice_data["proposedExclusions"] = [{"sourceId": "source-exclude", "reason": "过时", "runtime": True}]
        self.assertIn("unknown-field", {issue.code for issue in self.api().validate_instructional_plan(data, coverage_document())})
        api = self.api()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_root(root)
            api.approve_plan(root, decision_id="decision-1", approved_at="2026-08-21T00:00:00Z")
            stored = load_json(root / ".course-work/course-storyboard.json")
            stored["approval"]["runtime"] = True
            write_json_atomic(root / ".course-work/course-storyboard.json", stored)
            with self.assertRaises(api.PlanApprovalError) as caught:
                api.verify_plan_approval(root)
            self.assertEqual(caught.exception.code, "approval-invalid")

    def test_approval_binds_evidence_and_never_changes_plan_body(self):
        api = self.api()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_root(root)
            before = load_json(root / ".course-work/course-storyboard.json")
            approval = api.approve_plan(root, decision_id="decision-1", approved_at="2026-08-21T00:00:00Z")
            after = load_json(root / ".course-work/course-storyboard.json")
            self.assertEqual(api.plan_content_hash(before), api.plan_content_hash(after))
            self.assertEqual(approval["materialsExtractedHash"], api.verify_plan_approval(root)["materialsExtractedHash"])

    def test_concurrent_edit_conflicts_with_approval_without_losing_new_body(self):
        api = self.api()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_root(root)
            original_guard = api._plan_guard

            @contextmanager
            def coordinated_edit(guard_root, **kwargs):
                current = load_json(guard_root / ".course-work/course-storyboard.json")
                current["title"] = "并发编辑后的计划"
                write_json_atomic(guard_root / ".course-work/course-storyboard.json", current)
                with original_guard(guard_root, **kwargs):
                    yield

            with patch.object(api, "_plan_guard", coordinated_edit):
                with self.assertRaises(api.PlanApprovalError) as caught:
                    api.approve_plan(root, decision_id="decision-1", approved_at="2026-08-21T00:00:00Z")
            self.assertEqual(caught.exception.code, "approval-conflict")
            stored = load_json(root / ".course-work/course-storyboard.json")
            self.assertEqual(stored["title"], "并发编辑后的计划")
            self.assertNotIn("approval", stored)

    def test_public_plan_body_writer_clears_approval_and_honors_expected_hash(self):
        api = self.api()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_root(root)
            api.approve_plan(root, decision_id="decision-1", approved_at="2026-08-21T00:00:00Z")
            stored = load_json(root / ".course-work/course-storyboard.json")
            expected = api.plan_content_hash(stored)
            updated = api.write_plan_body(root, expected_plan_content_hash=expected, mutate=lambda body: {**body, "title": "由写入接口更新"})
            self.assertEqual(updated["title"], "由写入接口更新")
            self.assertNotIn("approval", load_json(root / ".course-work/course-storyboard.json"))

    def test_changed_inventory_coverage_or_plan_makes_approval_stale(self):
        api = self.api()
        for name in ("materials-extracted.json", "source-coverage.json", "course-storyboard.json"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                write_root(root)
                api.approve_plan(root, decision_id="decision-1", approved_at="2026-08-21T00:00:00Z")
                path = root / ".course-work" / name
                changed = load_json(path)
                if name == "course-storyboard.json":
                    changed["title"] = "变更后的教学计划"
                else:
                    changed["changeMarker"] = name
                write_json_atomic(path, changed)
                with self.assertRaises(api.PlanApprovalError) as caught:
                    api.verify_plan_approval(root)
                self.assertEqual(caught.exception.code, "approval-stale")

    def test_missing_malformed_and_symlinked_evidence_fail_closed_with_logical_issues(self):
        api = self.api()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_root(root)
            (root / ".course-work/materials-extracted.json").unlink()
            issues = api.validate_plan_at_root(root)
            self.assertIn((".course-work/materials-extracted.json", "missing-file"), {(item.path, item.code) for item in issues})
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_root(root)
            (root / ".course-work/course-storyboard.json").write_text("{broken", encoding="utf-8")
            issues = api.validate_plan_at_root(root)
            self.assertIn((".course-work/course-storyboard.json", "invalid-json"), {(item.path, item.code) for item in issues})
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_root(root)
            target = root / "coverage-target.json"
            write_json_atomic(target, coverage_document())
            (root / ".course-work/source-coverage.json").unlink()
            (root / ".course-work/source-coverage.json").symlink_to(target)
            issues = api.validate_plan_at_root(root)
            self.assertIn((".course-work/source-coverage.json", "symlink-file"), {(item.path, item.code) for item in issues})

    def test_approval_rejects_complete_evidence_schema_failures(self):
        api = self.api()
        invalid_cases = {
            "bad-disposition": ("coverage", lambda value: value["items"][0].update({"disposition": "bogus"})),
            "bad-inventory-item": ("extracted", lambda value: value["items"].__setitem__(0, "not-an-object")),
            "duplicate-inventory": ("extracted", lambda value: value["items"].append(value["items"][0].copy())),
            "missing-trace": ("coverage", lambda value: value["items"][0].pop("location")),
            "mismatch": ("extracted", lambda value: value["items"][0].update({"location": "page:99"})),
        }
        for name, (target, mutate) in invalid_cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                write_root(root)
                filename = "source-coverage.json" if target == "coverage" else "materials-extracted.json"
                path = root / ".course-work" / filename
                value = load_json(path)
                mutate(value)
                write_json_atomic(path, value)
                with self.assertRaises(api.PlanValidationError):
                    api.approve_plan(root, decision_id="decision-1", approved_at="2026-08-21T00:00:00Z")

    def test_markdown_escapes_adversarial_titles_and_cells_deterministically(self):
        data = plan_document()
        data["title"] = "标题\\<b>|\n## 注入"
        data["parts"][0]["slices"][0]["teachingPurpose"] = "目的|<script>&\r\n# 假标题"
        rendered = self.api().render_teacher_plan(data, coverage_document())
        self.assertEqual(rendered, self.api().render_teacher_plan(data, coverage_document()))
        self.assertIn("标题&#92;&#60;b&#62;&#124; &#35;&#35; 注入", rendered)
        self.assertIn("目的&#124;&#60;script&#62;&#38; &#35; 假标题", rendered)
        self.assertNotIn("<script>", rendered)

    def test_markdown_shows_all_substantive_teacher_fields_and_disables_links(self):
        data = plan_document()
        slice_data = data["parts"][0]["slices"][0]
        slice_data["learnerSees"] = "学生可见材料"
        slice_data["completionEvidence"] = {"description": "提交判断", "artifact": "一段理由"}
        slice_data["unresolvedBlockers"] = [{"id": "needs-confirmation", "reason": "请确认图表版本"}]
        slice_data["proposedExclusions"] = [{"sourceId": "source-exclude", "reason": "过时"}]
        data["title"] = "[click](javascript:alert(1)) ![track](https://example.test) <img src=x>"
        rendered = self.api().render_teacher_plan(data, coverage_document())
        for text in ("学生可见材料", "提交判断", "一段理由", "请确认图表版本", "source&#45;exclude", "图像关系", "拟排除素材"):
            self.assertIn(text, rendered)
        self.assertNotIn("[click]", rendered)
        self.assertNotIn("![track]", rendered)
        self.assertNotIn("<img", rendered)

    def test_malformed_target_id_and_reference_word_boundaries_are_safe(self):
        data = plan_document()
        data["parts"][0]["slices"][0]["coVisibleRequirements"][0]["targetId"] = ["not-a-target"]
        codes = {issue.code for issue in self.api().validate_instructional_plan(data, coverage_document())}
        self.assertIn("stable-target-required", codes)
        action = plan_document()["parts"][0]["slices"][0]["learnerAction"]
        action["referencePolicy"] = "none"
        action["referenceSourceIds"] = []
        action.pop("targetId")
        action["description"] = "The response is ready for review."
        plan = plan_document()
        plan["parts"][0]["slices"][0]["learnerAction"] = action
        plan["parts"][0]["slices"][0]["coVisibleRequirements"] = []
        self.assertNotIn("reference-policy-inconsistent", {issue.code for issue in self.api().validate_instructional_plan(plan, coverage_document())})
        action["description"] = "Read the source chart and answer."
        self.assertIn("reference-policy-inconsistent", {issue.code for issue in self.api().validate_instructional_plan(plan, coverage_document())})
        action["description"] = "准备好后提交回答。"
        self.assertNotIn("reference-policy-inconsistent", {issue.code for issue in self.api().validate_instructional_plan(plan, coverage_document())})
        action["description"] = "比较图表后提交回答。"
        self.assertIn("reference-policy-inconsistent", {issue.code for issue in self.api().validate_instructional_plan(plan, coverage_document())})
        action["description"] = "写出你的判断依据。"
        self.assertNotIn("reference-policy-inconsistent", {issue.code for issue in self.api().validate_instructional_plan(plan, coverage_document())})
        action["description"] = "依据外部证据写出你的判断。"
        self.assertIn("reference-policy-inconsistent", {issue.code for issue in self.api().validate_instructional_plan(plan, coverage_document())})
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_root(root, plan=data)
            script = Path(__file__).resolve().parents[1] / "scripts/manage-course-plan.py"
            result = subprocess.run(["python3", str(script), str(root), "validate"], text=True, capture_output=True, check=False)
            self.assertEqual(result.returncode, 2)
            self.assertIn("stable-target-required", result.stderr)
            self.assertNotIn(str(root), result.stderr)

    def test_plan_guard_has_windows_backend_and_real_process_timeout_then_release(self):
        api = self.api()
        class FakeMsvcrt:
            LK_NBLCK = 1
            LK_UNLCK = 2
            calls = []

            @classmethod
            def locking(cls, descriptor, mode, size):
                cls.calls.append((mode, size))

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / ".course-work").mkdir()
            with patch.object(api, "_fcntl", None), patch.object(api, "_msvcrt", FakeMsvcrt):
                with api._plan_guard(root, timeout_seconds=0.1):
                    pass
            self.assertEqual([mode for mode, _ in FakeMsvcrt.calls], [FakeMsvcrt.LK_NBLCK, FakeMsvcrt.LK_UNLCK])
            holder = subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    "from pathlib import Path; import time; from course_toolkit.instructional_plan import _plan_guard; root=Path(__import__('sys').argv[1]);\nwith _plan_guard(root, timeout_seconds=1):\n print('locked', flush=True); time.sleep(0.5)",
                    str(root),
                ],
                cwd=Path(__file__).resolve().parents[1],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(holder.stdout.readline().strip(), "locked")
            with self.assertRaises(api.PlanApprovalError) as caught:
                with api._plan_guard(root, timeout_seconds=0.1):
                    pass
            self.assertEqual(caught.exception.code, "plan-lock-timeout")
            self.assertEqual(holder.wait(timeout=2), 0, holder.stderr.read())
            holder.stdout.close()
            holder.stderr.close()
            with api._plan_guard(root, timeout_seconds=0.1):
                pass

    def test_render_rejects_symlinked_output_and_never_reports_absolute_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_root(root)
            output = root / ".course-work/course-storyboard.md"
            target = root / "outside.md"
            target.write_text("outside", encoding="utf-8")
            output.symlink_to(target)
            script = Path(__file__).resolve().parents[1] / "scripts/manage-course-plan.py"
            result = subprocess.run(["python3", str(script), str(root), "render"], text=True, capture_output=True, check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn(str(root), result.stdout + result.stderr)
            self.assertEqual(target.read_text(encoding="utf-8"), "outside")

    def test_render_does_not_follow_precreated_temp_symlink_and_reports_relative_output(self):
        api = self.api()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_root(root)
            target = root / "outside.md"
            target.write_text("outside", encoding="utf-8")
            trap = root / ".course-work/.course-storyboard-trap.tmp"
            trap.symlink_to(target)
            api.render_plan_at_root(root)
            self.assertEqual(target.read_text(encoding="utf-8"), "outside")
            script = Path(__file__).resolve().parents[1] / "scripts/manage-course-plan.py"
            result = subprocess.run(["python3", str(script), str(root), "render"], text=True, capture_output=True, check=False)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout.strip(), ".course-work/course-storyboard.md")

    def test_render_rejects_symlinked_course_work_directory(self):
        api = self.api()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_root(root)
            work = root / ".course-work"
            target = root / "work-target"
            work.rename(target)
            work.symlink_to(target, target_is_directory=True)
            with self.assertRaises(api.PlanValidationError) as caught:
                api.render_plan_at_root(root)
            self.assertEqual(caught.exception.issues[0].code, "symlink-file")

    def test_approval_does_not_follow_legacy_predictable_json_temp_symlink(self):
        api = self.api()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_root(root)
            outside = root / "outside.json"
            outside.write_text("outside", encoding="utf-8")
            legacy_temp = root / ".course-work" / f".course-storyboard.json.{os.getpid()}.tmp"
            legacy_temp.symlink_to(outside)
            api.approve_plan(root, decision_id="decision-1", approved_at="2026-08-21T00:00:00Z")
            self.assertEqual(outside.read_text(encoding="utf-8"), "outside")

    def test_cli_write_failure_hides_course_root_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_root(root)
            work = root / ".course-work"
            work.chmod(0o500)
            script = Path(__file__).resolve().parents[1] / "scripts/manage-course-plan.py"
            try:
                result = subprocess.run(["python3", str(script), str(root), "render"], text=True, capture_output=True, check=False)
            finally:
                work.chmod(0o700)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("filesystem-error", result.stderr)
            self.assertNotIn(str(root), result.stdout + result.stderr)

    def test_cli_validate_render_approve_and_status(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_root(root)
            script = Path(__file__).resolve().parents[1] / "scripts/manage-course-plan.py"
            def run(*args):
                return subprocess.run(["python3", str(script), str(root), *args], text=True, capture_output=True, check=False)
            self.assertEqual(run("validate").returncode, 0)
            self.assertIn("ready-for-approval", run("status").stdout)
            self.assertEqual(run("render").returncode, 0)
            rendered = root / ".course-work/course-storyboard.md"
            first = rendered.read_text(encoding="utf-8")
            self.assertEqual(run("render").returncode, 0)
            self.assertEqual(first, rendered.read_text(encoding="utf-8"))
            self.assertEqual(list(rendered.parent.glob(".course-storyboard.md.*.tmp")), [])
            self.assertEqual(run("approve", "--decision-id", "decision-1").returncode, 0)
            rendered.write_text("教师笔记不会影响审批", encoding="utf-8")
            self.assertIn("approved-current", run("status").stdout)
            self.assertNotEqual(run("approve").returncode, 0)
            (root / ".course-work/course-storyboard.json").write_text("{broken", encoding="utf-8")
            self.assertNotEqual(run("validate").returncode, 0)


if __name__ == "__main__":
    unittest.main()
