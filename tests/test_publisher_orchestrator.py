import json
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from course_toolkit.decisions import DecisionStore
from course_toolkit.publication import (
    PUBLICATION_DECISION_ID,
    PublishState,
    build_asset_manifest,
    load_publish_state,
    prepare_publication_preflight,
    write_asset_manifest,
    write_publish_state,
    new_publish_state,
)
from course_toolkit.publisher import (
    AmbiguousPublicationResult,
    AssetUploadResult,
    CourseWriteResult,
    RemoteCourseSnapshot,
    load_publication_operation,
    publish_course,
)
from course_toolkit.workflow import (
    G3_EVIDENCE_KEYS,
    complete_gate,
    hash_path,
    load_session,
    save_session,
    verify_g9_publication_preflight,
    verify_g10_remote_publication,
)
from tests.helpers import ROOT
from tests.test_publication_manifest import NOW, prepare_g6
from tests.test_publication_preflight import (
    complete_through_g8,
    not_found_discovery,
    review_evidence,
)


class FakeObjectStore:
    def __init__(self, fail_once_at=None):
        self.calls = Counter()
        self.fail_once_at = fail_once_at
        self.total_calls = 0

    def ensure_asset(self, *, local_path, object_key, sha256, idempotency_key):
        self.total_calls += 1
        self.calls[sha256] += 1
        if self.fail_once_at == self.total_calls:
            self.fail_once_at = None
            raise RuntimeError("simulated object store interruption")
        self.asserted_idempotency_key = idempotency_key
        if hash_path(local_path) != sha256:
            raise AssertionError("orchestrator supplied wrong local bytes")
        return AssetUploadResult(
            object_key=object_key,
            uploaded_sha256=sha256,
            etag=f"etag-{sha256[:8]}",
            verified_at=NOW,
        )


class FakeCourseApi:
    def __init__(self, *, ambiguous_create_after_write=False, corrupt_read=False):
        self.create_calls = 0
        self.update_calls = 0
        self.discover_calls = 0
        self.read_calls = 0
        self.ambiguous_create_after_write = ambiguous_create_after_write
        self.corrupt_read = corrupt_read
        self.remote = None

    def discover(self, *, slug):
        self.discover_calls += 1
        if self.remote is None:
            return not_found_discovery()
        return self.remote.as_discovery()

    def create_course(self, *, request):
        self.create_calls += 1
        self.remote = RemoteCourseSnapshot.from_request(
            request,
            remote_course_id="remote-course-1",
            revision="revision-1",
            observed_at=NOW,
        )
        if self.ambiguous_create_after_write:
            self.ambiguous_create_after_write = False
            raise AmbiguousPublicationResult("create response timed out")
        return CourseWriteResult("remote-course-1", "revision-1")

    def update_course(self, *, remote_course_id, expected_revision, request):
        self.update_calls += 1
        if self.remote is None or remote_course_id != self.remote.remote_course_id:
            raise AssertionError("update targeted a different remote course")
        if expected_revision != self.remote.revision:
            raise AssertionError("update used a stale revision")
        next_revision = f"revision-{self.update_calls + 1}"
        self.remote = RemoteCourseSnapshot.from_request(
            request,
            remote_course_id=remote_course_id,
            revision=next_revision,
            observed_at=NOW,
        )
        return CourseWriteResult(remote_course_id, next_revision)

    def read_course(self, *, remote_course_id):
        self.read_calls += 1
        if self.remote is None or self.remote.remote_course_id != remote_course_id:
            raise AssertionError("unknown remote course")
        if not self.corrupt_read:
            return self.remote
        return RemoteCourseSnapshot(
            **{
                **self.remote.__dict__,
                "definition_hash": "0" * 64,
            }
        )


def approve(root: Path, rationale="Approved exact publication dry run.") -> None:
    decisions = DecisionStore.load(root / ".course-work/decisions.json")
    decisions.confirm(
        PUBLICATION_DECISION_ID,
        {"choice": "approve", "rationale": rationale},
        NOW,
    )
    decisions.save()
    session = load_session(root)
    session.pending_decision_ids = [
        decision_id
        for decision_id in session.pending_decision_ids
        if decision_id != PUBLICATION_DECISION_ID
    ]
    save_session(root, session)


class PublisherOrchestratorTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        prepare_g6(self.root, full=True)
        complete_through_g8(self.root)
        write_asset_manifest(
            self.root,
            build_asset_manifest(self.root, "course-local-a"),
        )
        write_publish_state(
            self.root,
            new_publish_state("course-local-a", "evidence-course"),
        )
        prepare_publication_preflight(
            root=self.root,
            discovery=not_found_discovery(),
            review_evidence=review_evidence(self.root),
            intended_status="preview",
            visibility="private",
            now=NOW,
        )
        approve(self.root)

    def tearDown(self):
        self.temporary.cleanup()

    def test_create_is_verified_then_persisted_and_same_operation_is_idempotent(self):
        objects = FakeObjectStore()
        api = FakeCourseApi()

        first = publish_course(
            self.root,
            object_store=objects,
            course_api=api,
            now=NOW,
        )
        second = publish_course(
            self.root,
            object_store=objects,
            course_api=api,
            now=NOW,
        )

        self.assertEqual(first, second)
        self.assertEqual(api.create_calls, 1)
        self.assertEqual(api.update_calls, 0)
        self.assertEqual(sum(objects.calls.values()), 7)
        state = load_publish_state(self.root)
        self.assertEqual(state.remote_course_id, "remote-course-1")
        self.assertEqual(state.last_known_remote_revision, "revision-1")
        self.assertEqual(state.last_uploaded_definition_hash, first.definition_hash)
        operation = load_publication_operation(self.root)
        self.assertEqual(operation.phase, "verified")

    def test_g9_evidence_is_hash_bound_but_fake_operation_cannot_complete_g10(self):
        evidence = verify_g9_publication_preflight(self.root)
        session = load_session(self.root)
        complete_gate(session, "G9", NOW, gate_evidence=evidence)
        save_session(self.root, session)
        publish_course(
            self.root,
            object_store=FakeObjectStore(),
            course_api=FakeCourseApi(),
            now=NOW,
        )

        with self.assertRaisesRegex(ValueError, "live publication adapter"):
            verify_g10_remote_publication(self.root)

    def test_publication_readiness_preserves_legacy_completed_page_plan_gates(self):
        session = load_session(self.root)
        for key in G3_EVIDENCE_KEYS:
            session.artifact_hashes.pop(key, None)
        save_session(self.root, session)

        evidence = verify_g9_publication_preflight(self.root)

        self.assertIn(".course-work/publication-preflight.json", evidence)
        self.assertIn("G8", load_session(self.root).completed_gate_ids)

    def test_local_workflow_cli_refuses_g9_even_with_approved_current_dry_run(self):
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/course-workflow.py"),
                "complete-gate",
                str(self.root),
                "G9",
                "--json",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 2)
        payload = json.loads(completed.stdout)
        self.assertIn("live publication adapter", payload["error"]["message"])
        self.assertEqual(load_session(self.root).completed_gate_ids[-1], "G8")

    def test_next_preflight_updates_same_course_and_reuses_uploaded_assets(self):
        objects = FakeObjectStore()
        api = FakeCourseApi()
        publish_course(self.root, object_store=objects, course_api=api, now=NOW)
        first_upload_count = sum(objects.calls.values())
        prepare_publication_preflight(
            root=self.root,
            discovery=api.discover(slug="evidence-course"),
            review_evidence=review_evidence(self.root),
            intended_status="published",
            visibility="unlisted",
            now=NOW,
        )
        approve(self.root, "Approve update of the existing course.")

        result = publish_course(
            self.root,
            object_store=objects,
            course_api=api,
            now=NOW,
        )

        self.assertEqual(api.create_calls, 1)
        self.assertEqual(api.update_calls, 1)
        self.assertEqual(sum(objects.calls.values()), first_upload_count)
        self.assertEqual(result.remote_course_id, "remote-course-1")
        state = load_publish_state(self.root)
        self.assertEqual(state.remote_course_id, "remote-course-1")
        self.assertEqual(state.remote_status, "published")
        self.assertEqual(state.last_published_definition_hash, result.definition_hash)

    def test_verified_uploads_resume_without_uploading_the_same_hash_twice(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            prepare_g6(root, full=True)
            complete_through_g8(root)
            write_asset_manifest(root, build_asset_manifest(root, "course-local-a"))
            write_publish_state(
                root,
                new_publish_state("course-local-a", "evidence-course"),
            )
            prepare_publication_preflight(
                root=root,
                discovery=not_found_discovery(),
                review_evidence=review_evidence(root),
                intended_status="preview",
                visibility="private",
                now=NOW,
            )
            approve(root)
            objects = FakeObjectStore(fail_once_at=2)
            api = FakeCourseApi()

            with self.assertRaisesRegex(RuntimeError, "interruption"):
                publish_course(root, object_store=objects, course_api=api, now=NOW)
            first_verified_hash = load_publication_operation(root).verified_assets[0].uploaded_sha256
            publish_course(root, object_store=objects, course_api=api, now=NOW)

        self.assertEqual(objects.calls[first_verified_hash], 1)
        self.assertEqual(api.create_calls, 1)

    def test_ambiguous_create_recovers_by_discovery_and_read_without_second_create(self):
        objects = FakeObjectStore()
        api = FakeCourseApi(ambiguous_create_after_write=True)

        result = publish_course(
            self.root,
            object_store=objects,
            course_api=api,
            now=NOW,
        )

        self.assertEqual(result.remote_course_id, "remote-course-1")
        self.assertEqual(api.create_calls, 1)
        self.assertGreaterEqual(api.discover_calls, 1)
        self.assertGreaterEqual(api.read_calls, 1)

    def test_failed_readback_never_updates_verified_publish_state(self):
        objects = FakeObjectStore()
        api = FakeCourseApi(corrupt_read=True)

        with self.assertRaisesRegex(ValueError, "definition hash"):
            publish_course(
                self.root,
                object_store=objects,
                course_api=api,
                now=NOW,
            )

        state = load_publish_state(self.root)
        self.assertIsNone(state.remote_course_id)
        operation = load_publication_operation(self.root)
        self.assertNotEqual(operation.phase, "verified")

    def test_update_failure_never_falls_back_to_create(self):
        objects = FakeObjectStore()
        api = FakeCourseApi()
        publish_course(self.root, object_store=objects, course_api=api, now=NOW)
        prepare_publication_preflight(
            root=self.root,
            discovery=api.discover(slug="evidence-course"),
            review_evidence=review_evidence(self.root),
            intended_status="published",
            visibility="private",
            now=NOW,
        )
        approve(self.root, "Approve update, never another create.")
        create_calls_before_update = api.create_calls

        def fail_update(**_kwargs):
            api.update_calls += 1
            raise RuntimeError("simulated update failure")

        api.update_course = fail_update
        with self.assertRaisesRegex(RuntimeError, "update failure"):
            publish_course(
                self.root,
                object_store=objects,
                course_api=api,
                now=NOW,
            )

        self.assertEqual(api.create_calls, create_calls_before_update)
        self.assertEqual(api.update_calls, 1)


if __name__ == "__main__":
    unittest.main()
