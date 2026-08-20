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


def write_root(root: Path, *, plan=None, coverage=None, extracted=None):
    """Create a fixture only inside an explicit temporary course root.

    A prior manual test probe passed the repository directory here, leaving a
    root-level ``.course-work`` fixture behind.  Keep the helper deliberately
    unable to write into this repository so focused test reruns cannot repeat
    that leak.
    """
    if root.resolve() == REPOSITORY_ROOT:
        raise AssertionError("fixture root must not be the repository root")
    write_json_atomic(root / ".course-work/course-storyboard.json", plan or plan_document())
    write_json_atomic(root / ".course-work/source-coverage.json", coverage or coverage_document())
    write_json_atomic(root / ".course-work/materials-extracted.json", extracted or extracted_document())


class InstructionalPlanTests(unittest.TestCase):
    def api(self):
        import course_toolkit.instructional_plan as api

        return api

    def test_complete_plan_validates_and_requires_a_slice_per_part(self):
        self.assertEqual(self.api().validate_instructional_plan(plan_document(), coverage_document()), [])
        empty = plan_document()
        empty["parts"][0]["slices"] = []
        self.assertIn("part-slices-required", {issue.code for issue in self.api().validate_instructional_plan(empty, coverage_document())})

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

    def test_teacher_markdown_has_rows_and_every_unused_material(self):
        coverage = coverage_document()
        coverage["items"].append(
            {
                "sourceId": "source-exclude-approved",
                "sourceFile": "materials/duplicate.pdf",
                "location": "page:4",
                "summary": "重复内容",
                "disposition": "exclude-approved",
                "reason": "与核心证据重复",
                "bindings": [],
            }
        )
        rendered = self.api().render_teacher_plan(plan_document(), coverage)
        self.assertIn("| 教学目的 |", rendered)
        self.assertIn("未使用或仅用于备课", rendered)
        for source_id in ("source&#45;support", "source&#45;authoring", "source&#45;exclude", "source&#45;exclude&#45;approved"):
            self.assertIn(source_id, rendered)
        self.assertNotIn("G0", rendered)
        self.assertNotIn("workflow", rendered.lower())

    def test_teacher_table_has_exactly_eight_cells_per_header_delimiter_and_row(self):
        rendered = self.api().render_teacher_plan(plan_document(), coverage_document())
        table = rendered.split("## 页面计划", 1)[1].split("## 页面细节", 1)[0]
        rows = [line for line in table.splitlines() if line.startswith("|")]
        self.assertGreaterEqual(len(rows), 3)
        for row in rows:
            self.assertEqual(len(row.split("|")[1:-1]), 8, row)

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
