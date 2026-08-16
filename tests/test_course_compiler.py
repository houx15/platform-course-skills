import copy
import json
import unittest

from course_toolkit.course_compiler import (
    CompilationBlocked,
    canonical_json_hash,
    compile_blueprint,
)
from course_toolkit.jsonio import dump_json, load_json
from tests.helpers import ROOT


FIXTURES = ROOT / "tests" / "fixtures" / "course-blueprint"
APPROVED = FIXTURES / "approved-blueprint.json"


def approved_blueprint():
    return json.loads(APPROVED.read_text(encoding="utf-8"))


class CourseCompilerTests(unittest.TestCase):
    def test_compile_is_byte_reproducible(self):
        first = compile_blueprint(approved_blueprint())
        second = compile_blueprint(copy.deepcopy(approved_blueprint()))

        self.assertEqual(dump_json(first.document), dump_json(second.document))
        self.assertEqual(dump_json(first.source_map), dump_json(second.source_map))
        self.assertEqual(dump_json(first.report), dump_json(second.report))

    def test_compile_matches_frozen_runtime_fixtures(self):
        result = compile_blueprint(approved_blueprint())

        self.assertEqual(
            result.document,
            load_json(FIXTURES / "expected-course-definition.json"),
        )
        self.assertEqual(
            result.source_map,
            load_json(FIXTURES / "expected-source-map.json"),
        )

    def test_runtime_output_contains_no_authoring_metadata(self):
        result = compile_blueprint(approved_blueprint())
        rendered = dump_json(result.document)

        self.assertNotIn("provenance", rendered)
        self.assertNotIn("decisionIds", rendered)
        self.assertNotIn("teacherConfirmed", rendered)

    def test_source_map_resolves_every_stable_target(self):
        result = compile_blueprint(approved_blueprint())
        target_ids = {mapping["targetId"] for mapping in result.source_map["mappings"]}

        self.assertEqual(
            target_ids,
            {
                "course",
                "opening",
                "closing",
                "objective:apply-check",
                "part:part-evidence-check",
                "slice:slice-read-and-answer",
                "block:claim-text",
                "block:evidence-question",
                "slice:slice-read-and-answer/narration:introduce-check",
                "slice:slice-read-and-answer/workflow-step:introduce",
                "slice:slice-read-and-answer/workflow-step:answer",
                "slice:slice-read-and-answer/workflow-step:finish",
            },
        )

    def test_source_map_propagates_provenance_and_pointers(self):
        result = compile_blueprint(approved_blueprint())
        mapping = next(
            item
            for item in result.source_map["mappings"]
            if item["targetId"] == "block:evidence-question"
        )

        self.assertEqual(
            mapping["blueprintPointer"],
            "/course/parts/0/slices/0/blocks/1",
        )
        self.assertEqual(mapping["runtimePointer"], mapping["blueprintPointer"])
        self.assertEqual(mapping["sourceIds"], ["source-1"])
        self.assertEqual(mapping["decisionIds"], ["decision-course-design"])

    def test_hashes_are_canonical_and_reported(self):
        data = approved_blueprint()
        result = compile_blueprint(data)

        self.assertEqual(result.source_map["blueprintHash"], canonical_json_hash(data))
        self.assertEqual(
            result.source_map["courseDefinitionHash"],
            canonical_json_hash(result.document),
        )
        self.assertEqual(
            result.report["sourceMapHash"],
            canonical_json_hash(result.source_map),
        )

    def test_report_uses_shared_contract_asset_collection(self):
        result = compile_blueprint(approved_blueprint())

        self.assertEqual(result.report["status"], "compiled")
        self.assertEqual(
            result.report["assetPaths"],
            ["assets/audio/introduce-check.mp3"],
        )
        self.assertEqual(
            result.report["contractSnapshot"]["upstreamCommit"],
            "df36a8ecd1b30f28c27789fcf02e898b5bee6e21",
        )

    def test_unconfirmed_blueprint_cannot_compile(self):
        data = approved_blueprint()
        data["approval"] = {"teacherConfirmed": False, "decisionIds": []}

        with self.assertRaises(CompilationBlocked) as caught:
            compile_blueprint(data)

        self.assertIn("blueprint-unconfirmed", {issue.code for issue in caught.exception.issues})

    def test_real_shared_contract_rejection_blocks_compilation(self):
        data = approved_blueprint()
        data["course"]["parts"][0]["slices"][0]["layout"]["slots"] = []

        with self.assertRaises(CompilationBlocked) as caught:
            compile_blueprint(data)

        issue = caught.exception.issues[0]
        self.assertEqual(issue.code, "course-contract-invalid")
        self.assertEqual(issue.layer, "structural")
        self.assertIn("slots", issue.path)


if __name__ == "__main__":
    unittest.main()
