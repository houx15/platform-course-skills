import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from course_toolkit.course_catalog import confirm_course_selection
from course_toolkit.course_compiler import compile_blueprint, write_compilation_outputs_atomic
from course_toolkit.course_package_validation import (
    build_course_validation_report,
    sync_validation_issues,
    write_current_validation_report,
)
from course_toolkit.decisions import DecisionStore
from course_toolkit.jsonio import load_json, write_json_atomic
from course_toolkit.instructional_plan import approve_plan
from course_toolkit.live_publication import (
    DECISION_ID,
    LivePublicationBlocked,
    build_live_asset_manifest,
    execute_live_publication,
    init_live_publish_state,
    prepare_live_preflight,
    live_preflight_status,
)
from course_toolkit.mind_imprint_api import RemoteCourse
from course_toolkit.mind_imprint_api import AmbiguousRemoteWrite
from course_toolkit.package_review import (
    prepare_v2_review,
    verify_g8_review,
    write_publication_review_evidence_v2,
    write_v2_review_report,
)
from course_toolkit.preview_evidence import record_preview_evidence, verify_g7_preview
from course_toolkit.workflow import (
    complete_gate,
    G3_EVIDENCE_KEYS,
    load_session,
    new_session,
    reconcile_artifacts,
    save_session,
    verify_g5_compilation,
    verify_g6_validation,
    verify_g3_plan,
    verify_g4_media_design,
)
from tests.test_package_review_v2 import approve
from tests.test_publication_manifest import NOW, prepare_g6
from tests.test_instructional_plan import write_root, write_valid_media_design


class FakeMindApi:
    api_base = "https://mind-api.example.test"
    supports_course_asset_cover = True

    def __init__(self):
        self.remote = None
        self.uploads = []
        self.saved = 0
        self.shipped = 0
        self.last_definition_options = None
        self.last_cover_asset_path = None
        self.get_course_calls = 0
        self.max_bytes = 500_000_000
        self.fail_save_once = False
        self.cover_verifications = []

    def get_course(self, slug):
        self.get_course_calls += 1
        return self.remote

    def plan_asset_upload(self, slug, relative_path, content_type, size):
        return {
            "putUrl": f"https://oss.example.test/{relative_path}",
            "objectKey": f"courses/{slug}/{relative_path}",
            "requiredContentType": content_type,
            "maxBytes": self.max_bytes,
            "expiresAt": NOW,
        }

    def upload_asset(self, put_url, local_path, required_content_type):
        self.uploads.append(local_path.name)
        return "etag"

    def save_definition(self, slug, definition, *, blurb, card_ids, category, introduction):
        self.saved += 1
        self.last_definition_options = {
            "blurb": blurb,
            "cardIds": card_ids,
            "category": category,
            "introduction": introduction,
        }
        if self.fail_save_once:
            self.fail_save_once = False
            raise AmbiguousRemoteWrite("synthetic ambiguous save")
        self.remote = RemoteCourse(slug, self.remote.status if self.remote else "preview", "b" * 64, copy.deepcopy(definition))
        return {"slug": slug, "status": self.remote.status}

    def ship(self, slug, *, cover, cover_asset_path=None):
        self.shipped += 1
        self.last_cover_asset_path = cover_asset_path
        self.remote = RemoteCourse(slug, "published", "b" * 64, self.remote.definition)
        return {"slug": slug, "status": "published", "narrationsGenerated": 1}

    def verify_published_cover(self, slug, expected_sha256):
        self.cover_verifications.append((slug, expected_sha256))
        return {
            "coverUrlPresent": True,
            "sha256": expected_sha256,
            "sizeBytes": 123,
        }


def prepare_g8(root: Path, *, catalog_identity: bool = True):
    prepare_g6(root, full=True)
    if catalog_identity:
        blueprint_path = root / ".course-work/course-blueprint.json"
        blueprint = load_json(blueprint_path)
        blueprint["course"]["id"] = "course-01"
        blueprint["course"]["title"] = "把争议放回证据里：立场光谱与视角对照矩阵"
        write_json_atomic(blueprint_path, blueprint)
        write_compilation_outputs_atomic(root, compile_blueprint(blueprint))
    report = build_course_validation_report(root)
    write_current_validation_report(root, report)
    sync_validation_issues(root, report, NOW)
    write_root(root)
    approve_plan(root, decision_id="decision-plan-1", approved_at=NOW)
    write_valid_media_design(root)
    write_json_atomic(root / ".course-work/decisions.json", {"schemaVersion": "1.0", "decisions": []})
    write_json_atomic(root / ".course-work/unresolved.json", {"schemaVersion": "1.0", "items": []})
    report = build_course_validation_report(root)
    write_current_validation_report(root, report)
    sync_validation_issues(root, report, NOW)
    document = load_json(root / "course/course.json")
    slices = [slice_data["id"] for part in document["course"]["parts"] for slice_data in part["slices"]]
    record_preview_evidence(root, {
        "viewport": {"width": 1440, "height": 900},
        "visitedSliceIds": slices,
        "exercisedEvents": [],
        "runtimeErrors": [],
        "teacherConfirmed": True,
        "completedAt": NOW,
    })
    write_v2_review_report(root, approve(prepare_v2_review(root)))
    session = new_session(document["course"]["id"], [], NOW)
    for gate in ("G0", "G1", "G2"):
        complete_gate(session, gate, NOW)
    complete_gate(
        session, "G3", NOW, gate_evidence=verify_g3_plan(root)
    )
    complete_gate(
        session,
        "G4",
        NOW,
        gate_evidence=verify_g4_media_design(root),
    )
    complete_gate(session, "G5", NOW, gate_evidence=verify_g5_compilation(root))
    complete_gate(session, "G6", NOW, gate_evidence=verify_g6_validation(root))
    complete_gate(session, "G7", NOW, gate_evidence=verify_g7_preview(root))
    complete_gate(session, "G8", NOW, gate_evidence=verify_g8_review(root))
    save_session(root, session)
    write_publication_review_evidence_v2(root)


class LivePublicationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        prepare_g8(self.root)
        self.reviewed_identity = copy.deepcopy(
            load_json(self.root / "course/course.json")["course"]
        )
        confirm_course_selection(
            self.root,
            "course-01",
            teacher_response="确认，这是第一门课。",
            confirmed_at=NOW,
        )
        state = init_live_publish_state(self.root)
        self.slug = state["slug"]
        self.api = FakeMindApi()

    def tearDown(self):
        self.temporary.cleanup()

    def approve_preflight(self):
        decisions = DecisionStore.load(self.root / ".course-work/decisions.json")
        decisions.confirm(DECISION_ID, {"choice": "approve", "rationale": "Approved for the production sandbox."}, NOW)
        decisions.save()
        session = load_session(self.root)
        session.pending_decision_ids = []
        save_session(self.root, session)

    def test_publish_uses_stable_slug_relative_paths_and_readback(self):
        preflight = prepare_live_preflight(
            self.root, self.api, action="publish", now=NOW
        )
        self.assertEqual(preflight["mode"], "create")
        self.assertEqual(preflight["catalog"]["catalogId"], "course-01")
        self.assertEqual(preflight["options"]["category"], "stance-value")
        self.assertEqual(preflight["options"]["cardIds"], ["belief-spectrum", "perspective-matrix"])
        self.assertEqual(preflight["catalogCover"]["relativePath"], "cover/course-cover.webp")
        self.assertEqual(
            preflight["catalogCover"]["objectKey"],
            "courses/course-01/cover/course-cover.webp",
        )
        self.assertEqual(preflight["options"]["blurb"], preflight["options"]["introduction"]["whatYouDo"])
        self.assertTrue(all(item["objectKey"] == f"courses/{self.slug}/{item['relativePath']}" for item in preflight["assets"]["upload"]))
        self.assertNotIn(
            "cover/course-cover.webp",
            [item["relativePath"] for item in preflight["assets"]["upload"]],
        )
        self.approve_preflight()

        result = execute_live_publication(self.root, self.api, now=NOW)

        self.assertEqual(result["status"], "published")
        self.assertEqual(self.api.saved, 1)
        self.assertEqual(self.api.shipped, 1)
        self.assertEqual(self.api.last_definition_options["category"], "stance-value")
        self.assertIn("hook", self.api.last_definition_options["introduction"])
        self.assertEqual(self.api.last_cover_asset_path, "cover/course-cover.webp")
        self.assertEqual(len(self.api.cover_verifications), 1)
        self.assertEqual(result["coverVerification"]["coverUrlPresent"], True)
        self.assertEqual(self.api.remote.definition["course"]["id"], "course-01")
        self.assertEqual(
            self.api.remote.definition["course"]["title"],
            "把争议放回证据里：立场光谱与视角对照矩阵",
        )
        self.assertEqual(
            load_json(self.root / "course/course.json")["course"],
            self.reviewed_identity,
        )
        self.assertEqual(
            result["coverVerification"]["sha256"],
            preflight["catalogCover"]["sha256"],
        )
        self.assertEqual(load_session(self.root).completed_gate_ids[-1], "G10")

    def test_late_catalog_selection_applies_fixed_identity_without_rewriting_reviewed_course(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prepare_g8(root, catalog_identity=False)
            reviewed = copy.deepcopy(load_json(root / "course/course.json"))
            self.assertNotEqual(reviewed["course"]["id"], "course-01")
            confirm_course_selection(
                root,
                "course-01",
                teacher_response="确认，这是第一门课。",
                confirmed_at=NOW,
            )
            state = init_live_publish_state(root)
            api = FakeMindApi()

            preflight = prepare_live_preflight(root, api, action="publish", now=NOW)
            decisions = DecisionStore.load(root / ".course-work/decisions.json")
            decisions.confirm(
                DECISION_ID,
                {"choice": "approve", "rationale": "Approved for the production sandbox."},
                NOW,
            )
            decisions.save()
            session = load_session(root)
            session.pending_decision_ids = []
            save_session(root, session)
            result = execute_live_publication(root, api, now=NOW)

            self.assertEqual(state["slug"], "course-01")
            self.assertTrue(preflight["definition"]["catalogIdentityApplied"])
            self.assertEqual(api.remote.definition["course"]["id"], "course-01")
            self.assertEqual(api.remote.definition["course"]["title"], preflight["catalog"]["title"])
            self.assertEqual(load_json(root / "course/course.json"), reviewed)
            self.assertEqual(result["status"], "published")

    def test_legacy_completed_course_is_not_retroactively_blocked_by_new_page_plan_evidence(self):
        prepare_live_preflight(self.root, self.api, action="publish", now=NOW)
        self.approve_preflight()
        session = load_session(self.root)
        for key in G3_EVIDENCE_KEYS:
            session.artifact_hashes.pop(key, None)
        save_session(self.root, session)

        status = live_preflight_status(self.root)

        self.assertTrue(status["current"])
        self.assertTrue(status["approved"])
        self.assertNotIn("g8-not-current", status["staleReasons"])
        self.assertIn("G8", load_session(self.root).completed_gate_ids)
        self.assertEqual(self.api.uploads, [])
        self.assertEqual(self.api.saved, 0)
        self.assertEqual(self.api.shipped, 0)

    def test_existing_canonical_remote_is_updated_instead_of_creating_a_duplicate(self):
        document = load_json(self.root / "course/course.json")
        self.api.remote = RemoteCourse(self.slug, "preview", "a" * 64, document)

        preflight = prepare_live_preflight(
            self.root, self.api, action="publish", now=NOW
        )

        self.assertEqual(preflight["mode"], "update")
        self.assertEqual(preflight["slug"], self.slug)

    def test_init_state_cli_derives_identity_without_accepting_a_free_form_slug(self):
        (self.root / ".course-work/publish-state.json").unlink()
        completed = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).resolve().parents[1] / "scripts/publish-course.py"),
                "init-state",
                str(self.root),
                "--json",
            ],
            cwd=Path(__file__).resolve().parents[1],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout)["slug"], "course-01")

    def test_old_course_without_catalog_binding_is_blocked_before_remote_discovery(self):
        (self.root / ".course-work/course-catalog-selection.json").unlink()

        with self.assertRaisesRegex(LivePublicationBlocked, "33-course catalog"):
            prepare_live_preflight(
                self.root, self.api, action="publish", now=NOW
            )

        self.assertEqual(self.api.get_course_calls, 0)

    def test_adapter_without_v1_4_cover_support_is_blocked_before_fixed_cover_publish(self):
        self.api.supports_course_asset_cover = False

        with self.assertRaisesRegex(LivePublicationBlocked, "cannot bind the fixed catalog WebP"):
            prepare_live_preflight(
                self.root, self.api, action="publish", now=NOW
            )

        self.assertIsNone(self.api.remote)

    def test_fixed_catalog_cover_is_never_a_teacher_upload_asset(self):
        preflight = prepare_live_preflight(self.root, self.api, action="publish", now=NOW)

        all_assets = preflight["assets"]["upload"] + preflight["assets"]["reuse"]
        self.assertNotIn("cover/course-cover.webp", [item["relativePath"] for item in all_assets])
        self.assertEqual(preflight["options"]["coverAssetPath"], "cover/course-cover.webp")

    def test_successful_local_upload_proof_is_reused_by_path_and_hash(self):
        prepare_live_preflight(self.root, self.api, action="publish", now=NOW)
        self.approve_preflight()
        execute_live_publication(self.root, self.api, now=NOW)
        manifest = build_live_asset_manifest(self.root, load_json(self.root / ".course-work/publish-state.json"))
        self.assertTrue(manifest["entries"])
        self.assertTrue(all(entry["state"] == "reuse-local-proof" for entry in manifest["entries"]))

    def test_server_upload_limit_blocks_before_sending_asset_bytes(self):
        prepare_live_preflight(self.root, self.api, action="publish", now=NOW)
        self.approve_preflight()
        self.api.max_bytes = 0

        with self.assertRaisesRegex(LivePublicationBlocked, "upload limit"):
            execute_live_publication(self.root, self.api, now=NOW)

        self.assertEqual(self.api.uploads, [])

    def test_resume_reuses_each_verified_asset_after_ambiguous_save(self):
        preflight = prepare_live_preflight(
            self.root, self.api, action="publish", now=NOW
        )
        self.approve_preflight()
        self.api.fail_save_once = True

        with self.assertRaises(LivePublicationBlocked):
            execute_live_publication(self.root, self.api, now=NOW)
        first_upload_count = len(self.api.uploads)
        self.assertEqual(first_upload_count, len(preflight["assets"]["upload"]))

        result = execute_live_publication(self.root, self.api, now=NOW)

        self.assertEqual(result["status"], "published")
        self.assertEqual(len(self.api.uploads), first_upload_count)
        self.assertEqual(result["uploadedPaths"], [])
        self.assertEqual(
            result["reusedPaths"],
            sorted(asset["relativePath"] for asset in preflight["assets"]["upload"]),
        )

    def test_repeated_publish_refreshes_gate_evidence_without_false_invalidation(self):
        prepare_live_preflight(
            self.root, self.api, action="publish", now=NOW
        )
        self.approve_preflight()
        execute_live_publication(self.root, self.api, now=NOW)

        prepare_live_preflight(
            self.root, self.api, action="publish", now=NOW
        )
        self.approve_preflight()
        second = execute_live_publication(self.root, self.api, now=NOW)
        reconciled = reconcile_artifacts(self.root, load_session(self.root), NOW)

        self.assertEqual(second["uploadedPaths"], [])
        self.assertIsNone(reconciled.earliest_invalidated_gate_id)

    def test_catalog_selection_change_invalidates_publication_approval(self):
        prepare_live_preflight(
            self.root, self.api, action="publish", now=NOW
        )
        self.approve_preflight()
        confirm_course_selection(
            self.root,
            "course-02",
            teacher_response="改为第二门课。",
            confirmed_at=NOW,
        )

        with self.assertRaisesRegex(LivePublicationBlocked, "catalogSelectionHash-changed"):
            execute_live_publication(self.root, self.api, now=NOW)


if __name__ == "__main__":
    unittest.main()
