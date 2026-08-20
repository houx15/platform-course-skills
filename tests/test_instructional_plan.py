import copy
import subprocess
import tempfile
import unittest
from pathlib import Path

from course_toolkit.jsonio import load_json, write_json_atomic


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
                "bindings": [],
            },
            {
                "sourceId": "source-image",
                "sourceFile": "materials/chart.png",
                "location": "image:chart-1",
                "summary": "对比图",
                "disposition": "required-evidence",
                "bindings": [],
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
                            "referenceSourceIds": ["source-image"],
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

    def test_duplicate_part_or_slice_identity_is_rejected(self):
        data = plan_document()
        data["parts"].append(copy.deepcopy(data["parts"][0]))
        codes = {issue.code for issue in self.api().validate_instructional_plan(data, coverage_document())}
        self.assertIn("duplicate-part-id", codes)
        self.assertIn("duplicate-slice-id", codes)

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
        for source_id in ("source-support", "source-authoring", "source-exclude", "source-exclude-approved"):
            self.assertIn(source_id, rendered)
        self.assertNotIn("G0", rendered)
        self.assertNotIn("workflow", rendered.lower())

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
        action["dependencyJustification"] = "学生已在纸质材料上标注同一张图表。"
        self.assertNotIn("reference-not-covisible", {issue.code for issue in self.api().validate_instructional_plan(data, coverage_document())})
        action["dependencyJustification"] = "学生可以回看上一页图表。"
        self.assertIn("reference-not-covisible", {issue.code for issue in self.api().validate_instructional_plan(data, coverage_document())})

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

    def test_changed_inventory_coverage_or_plan_makes_approval_stale(self):
        api = self.api()
        for name in ("materials-extracted.json", "source-coverage.json", "course-storyboard.json"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                write_root(root)
                api.approve_plan(root, decision_id="decision-1", approved_at="2026-08-21T00:00:00Z")
                path = root / ".course-work" / name
                changed = load_json(path)
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
