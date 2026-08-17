import copy
import tempfile
import unittest
from pathlib import Path

from course_toolkit.decisions import DecisionStore
from course_toolkit.jsonio import load_json
from course_toolkit.live_publication import (
    DECISION_ID,
    LivePublicationBlocked,
    build_live_asset_manifest,
    execute_live_publication,
    init_live_publish_state,
    prepare_live_preflight,
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
    load_session,
    new_session,
    save_session,
    verify_g5_compilation,
    verify_g6_validation,
)
from tests.test_package_review_v2 import approve
from tests.test_publication_manifest import NOW, prepare_g6


class FakeMindApi:
    api_base = "https://mind-api.example.test"

    def __init__(self):
        self.remote = None
        self.uploads = []
        self.saved = 0
        self.shipped = 0
        self.max_bytes = 500_000_000
        self.fail_save_once = False

    def get_course(self, slug):
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

    def save_definition(self, slug, definition, *, blurb, card_ids):
        self.saved += 1
        if self.fail_save_once:
            self.fail_save_once = False
            raise AmbiguousRemoteWrite("synthetic ambiguous save")
        self.remote = RemoteCourse(slug, self.remote.status if self.remote else "preview", "b" * 64, copy.deepcopy(definition))
        return {"slug": slug, "status": self.remote.status}

    def ship(self, slug, *, cover):
        self.shipped += 1
        self.remote = RemoteCourse(slug, "published", "b" * 64, self.remote.definition)
        return {"slug": slug, "status": "published", "narrationsGenerated": 1}


def prepare_g8(root: Path):
    prepare_g6(root, full=True)
    from course_toolkit.jsonio import write_json_atomic
    write_json_atomic(root / ".course-work/source-coverage.json", {"schemaVersion": "1.0", "items": []})
    write_json_atomic(root / ".course-work/decisions.json", {"schemaVersion": "1.0", "decisions": []})
    write_json_atomic(root / ".course-work/unresolved.json", {"schemaVersion": "1.0", "items": []})
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
    for gate in ("G0", "G1", "G2", "G3", "G4"):
        complete_gate(session, gate, NOW)
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
        self.slug = load_json(self.root / "course/course.json")["course"]["id"]
        init_live_publish_state(self.root, self.slug)
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
            self.root, self.api, action="publish", blurb="Demo", card_ids=[], cover="img:3", now=NOW
        )
        self.assertEqual(preflight["mode"], "create")
        self.assertTrue(all(item["objectKey"] == f"courses/{self.slug}/{item['relativePath']}" for item in preflight["assets"]["upload"]))
        self.approve_preflight()

        result = execute_live_publication(self.root, self.api, now=NOW)

        self.assertEqual(result["status"], "published")
        self.assertEqual(self.api.saved, 1)
        self.assertEqual(self.api.shipped, 1)
        self.assertEqual(load_session(self.root).completed_gate_ids[-1], "G10")

    def test_successful_local_upload_proof_is_reused_by_path_and_hash(self):
        prepare_live_preflight(self.root, self.api, action="publish", blurb="Demo", card_ids=[], cover="", now=NOW)
        self.approve_preflight()
        execute_live_publication(self.root, self.api, now=NOW)
        manifest = build_live_asset_manifest(self.root, load_json(self.root / ".course-work/publish-state.json"))
        self.assertTrue(manifest["entries"])
        self.assertTrue(all(entry["state"] == "reuse-local-proof" for entry in manifest["entries"]))

    def test_server_upload_limit_blocks_before_sending_asset_bytes(self):
        prepare_live_preflight(self.root, self.api, action="publish", blurb="Demo", card_ids=[], cover="", now=NOW)
        self.approve_preflight()
        self.api.max_bytes = 0

        with self.assertRaisesRegex(LivePublicationBlocked, "upload limit"):
            execute_live_publication(self.root, self.api, now=NOW)

        self.assertEqual(self.api.uploads, [])

    def test_resume_reuses_each_verified_asset_after_ambiguous_save(self):
        preflight = prepare_live_preflight(
            self.root, self.api, action="publish", blurb="Demo", card_ids=[], cover="", now=NOW
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


if __name__ == "__main__":
    unittest.main()
