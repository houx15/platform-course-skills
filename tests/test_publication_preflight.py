import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from course_toolkit.course_compiler import canonical_json_hash
from course_toolkit.decisions import DecisionStore
from course_toolkit.issues import IssueStore
from course_toolkit.jsonio import write_json_atomic
from course_toolkit.publication import (
    PUBLICATION_DECISION_ID,
    PUBLICATION_PREFLIGHT_RELATIVE_PATH,
    PublicationBlocked,
    PublicationReviewEvidence,
    RemoteDiscoverySnapshot,
    build_asset_manifest,
    prepare_publication_preflight,
    publication_preflight_status,
    write_asset_manifest,
    write_publish_state,
    new_publish_state,
)
from course_toolkit.workflow import (
    complete_gate,
    G7_EVIDENCE_KEYS,
    hash_path,
    new_session,
    save_session,
    verify_g5_compilation,
    verify_g6_validation,
)
from tests.helpers import ROOT
from tests.test_publication_manifest import NOW, prepare_g6


def complete_through_g8(root: Path) -> None:
    session = new_session("course-local-a", [], NOW)
    for gate_id in ("G0", "G1", "G2", "G3", "G4"):
        complete_gate(session, gate_id, NOW)
    complete_gate(session, "G5", NOW, gate_evidence=verify_g5_compilation(root))
    complete_gate(session, "G6", NOW, gate_evidence=verify_g6_validation(root))
    complete_gate(
        session,
        "G7",
        NOW,
        gate_evidence={key: "e" * 64 for key in G7_EVIDENCE_KEYS},
    )
    complete_gate(session, "G8", NOW)
    save_session(root, session)


def review_evidence(root: Path) -> PublicationReviewEvidence:
    preview = root / ".course-work/preview-manifest.json"
    review = root / ".course-work/review-report.json"
    write_json_atomic(preview, {"renderer": "student-runtime", "result": "clear"})
    write_json_atomic(review, {"review": "approved", "openAnnotations": 0})
    report = json.loads(
        (root / ".course-work/course-validation-report.json").read_text(encoding="utf-8")
    )
    return PublicationReviewEvidence(
        schema_version="1.0",
        status="approved",
        renderer_backed=True,
        course_definition_hash=report["courseDefinitionHash"],
        validation_report_hash=hash_path(
            root / ".course-work/course-validation-report.json"
        ),
        preview_manifest_hash=hash_path(preview),
        review_report_hash=hash_path(review),
        reviewed_at=NOW,
    )


def not_found_discovery() -> RemoteDiscoverySnapshot:
    return RemoteDiscoverySnapshot(
        schema_version="1.0",
        lookup_slug="evidence-course",
        status="not-found",
        observed_at=NOW,
    )


class PublicationPreflightTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        prepare_g6(self.root)
        complete_through_g8(self.root)
        write_asset_manifest(
            self.root,
            build_asset_manifest(self.root, "course-local-a"),
        )
        write_publish_state(
            self.root,
            new_publish_state("course-local-a", "evidence-course"),
        )
        self.review = review_evidence(self.root)

    def tearDown(self):
        self.temporary.cleanup()

    def prepare(self, **overrides):
        values = {
            "root": self.root,
            "discovery": not_found_discovery(),
            "review_evidence": self.review,
            "intended_status": "preview",
            "visibility": "private",
            "now": NOW,
        }
        values.update(overrides)
        return prepare_publication_preflight(**values)

    def test_preflight_is_deterministic_and_requests_exact_approval(self):
        first = self.prepare()
        second = self.prepare()

        self.assertEqual(first, second)
        self.assertEqual(first["mode"], "create")
        self.assertEqual(first["intendedStatus"], "preview")
        self.assertEqual(first["visibility"], "private")
        self.assertTrue(first["assets"]["upload"])
        self.assertEqual(first["assets"]["reuse"], [])
        self.assertTrue(first["limitations"]["liveAdapterRequired"])
        self.assertTrue((self.root / PUBLICATION_PREFLIGHT_RELATIVE_PATH).is_file())
        decision = DecisionStore.load(
            self.root / ".course-work/decisions.json"
        ).get(PUBLICATION_DECISION_ID)
        self.assertEqual(decision.status, "pending")
        self.assertEqual(decision.options, ("approve", "revise"))
        self.assertEqual(decision.context_hash, canonical_json_hash(first))

    def test_changed_visibility_invalidates_prior_approval(self):
        first = self.prepare()
        decisions = DecisionStore.load(self.root / ".course-work/decisions.json")
        decisions.confirm(
            PUBLICATION_DECISION_ID,
            {"choice": "approve", "rationale": "Ready for private preview."},
            NOW,
        )
        decisions.save()
        self.assertTrue(publication_preflight_status(self.root)["approved"])

        second = self.prepare(visibility="unlisted")

        self.assertNotEqual(canonical_json_hash(first), canonical_json_hash(second))
        status = publication_preflight_status(self.root)
        self.assertFalse(status["approved"])
        self.assertEqual(status["decisionStatus"], "pending")

    def test_changed_course_after_approval_is_immediately_stale(self):
        self.prepare()
        decisions = DecisionStore.load(self.root / ".course-work/decisions.json")
        decisions.confirm(
            PUBLICATION_DECISION_ID,
            {"choice": "approve", "rationale": "The exact dry run is approved."},
            NOW,
        )
        decisions.save()
        course_path = self.root / "course/course.json"
        course = json.loads(course_path.read_text(encoding="utf-8"))
        course["course"]["title"] = "Changed after approval"
        write_json_atomic(course_path, course)

        status = publication_preflight_status(self.root)

        self.assertFalse(status["current"])
        self.assertFalse(status["approved"])
        self.assertIn("course-definition-changed", status["staleReasons"])

    def test_stale_review_evidence_blocks_and_registers_g9_issue(self):
        stale = copy.copy(self.review)
        stale = PublicationReviewEvidence(
            **{
                **stale.__dict__,
                "course_definition_hash": "0" * 64,
            }
        )

        with self.assertRaisesRegex(PublicationBlocked, "review evidence"):
            self.prepare(review_evidence=stale)

        issue = next(
            issue
            for issue in IssueStore.load(
                self.root / ".course-work/issues.json"
            ).all()
            if issue.code == "publication-review-stale" and issue.status == "active"
        )
        self.assertEqual(issue.gate_id, "G9")
        self.assertEqual(issue.source, "publisher")

    def test_stale_asset_manifest_blocks_and_registers_g9_issue(self):
        manifest_path = self.root / ".course-work/asset-manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["courseDefinitionHash"] = "0" * 64
        write_json_atomic(manifest_path, manifest)

        with self.assertRaisesRegex(PublicationBlocked, "asset manifest"):
            self.prepare()

        codes = {
            issue.code
            for issue in IssueStore.load(
                self.root / ".course-work/issues.json"
            ).all()
            if issue.status == "active"
        }
        self.assertIn("publication-asset-state-stale", codes)

    def test_identity_conflict_blocks_and_registers_g9_issue(self):
        found = RemoteDiscoverySnapshot(
            schema_version="1.0",
            lookup_slug="evidence-course",
            status="found",
            observed_at=NOW,
            course_local_id="someone-else",
            remote_course_id="remote-1",
            remote_status="preview",
            remote_revision="revision-1",
            definition_hash="a" * 64,
        )

        with self.assertRaisesRegex(PublicationBlocked, "already exists"):
            self.prepare(discovery=found)

        codes = {
            issue.code
            for issue in IssueStore.load(
                self.root / ".course-work/issues.json"
            ).all()
            if issue.status == "active"
        }
        self.assertIn("publication-identity-conflict", codes)


class PublicationPreflightCliTests(unittest.TestCase):
    def test_init_state_is_idempotent_and_refuses_identity_replacement(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            save_session(root, new_session("course-local-a", [], NOW))
            command = [
                sys.executable,
                str(ROOT / "scripts/prepare-publication.py"),
                "init-state",
                str(root),
                "--json",
            ]
            first = subprocess.run(
                [*command, "--slug", "evidence-course"],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            repeated = subprocess.run(
                [*command, "--slug", "evidence-course"],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            conflict = subprocess.run(
                [*command, "--slug", "different-course"],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(repeated.returncode, 0, repeated.stderr)
        self.assertEqual(conflict.returncode, 2)
        self.assertIn("refusing to replace", conflict.stdout)

    def test_cli_prepares_and_reports_local_status_without_network(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            prepare_g6(root)
            complete_through_g8(root)
            write_asset_manifest(root, build_asset_manifest(root, "course-local-a"))
            write_publish_state(
                root,
                new_publish_state("course-local-a", "evidence-course"),
            )
            evidence_path = root / ".course-work/publication-review-evidence.json"
            discovery_path = root / ".course-work/remote-discovery.json"
            write_json_atomic(evidence_path, review_evidence(root).as_dict())
            write_json_atomic(discovery_path, not_found_discovery().as_dict())

            prepared = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/prepare-publication.py"),
                    "preflight",
                    str(root),
                    "--discovery",
                    str(discovery_path),
                    "--review-evidence",
                    str(evidence_path),
                    "--intended-status",
                    "preview",
                    "--visibility",
                    "private",
                    "--json",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            status = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/prepare-publication.py"),
                    "status",
                    str(root),
                    "--json",
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

        self.assertEqual(prepared.returncode, 0, prepared.stderr)
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertEqual(json.loads(prepared.stdout)["preflight"]["mode"], "create")
        self.assertFalse(json.loads(status.stdout)["status"]["approved"])


if __name__ == "__main__":
    unittest.main()
