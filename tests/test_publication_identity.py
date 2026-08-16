import tempfile
import unittest
from pathlib import Path

from course_toolkit.publication import (
    PublishState,
    RemoteDiscoverySnapshot,
    PublicationBlocked,
    load_publish_state,
    new_publish_state,
    resolve_publication_identity,
    write_publish_state,
)


HASH = "a" * 64
NOW = "2026-08-16T00:00:00Z"


def discovery(status="not-found", **overrides):
    values = {
        "schema_version": "1.0",
        "lookup_slug": "evidence-course",
        "status": status,
        "observed_at": NOW,
    }
    if status == "found":
        values.update(
            course_local_id="course-local-a",
            remote_course_id="remote-course-1",
            remote_status="preview",
            remote_revision="revision-7",
            definition_hash=HASH,
            known_assets=(
                {
                    "sha256": "b" * 64,
                    "objectKey": "courses/course-local-a/assets/bb/file.pdf",
                },
            ),
        )
    values.update(overrides)
    return RemoteDiscoverySnapshot(**values)


class PublishStateTests(unittest.TestCase):
    def test_new_local_state_round_trips_without_remote_claims(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            state = new_publish_state("course-local-a", "evidence-course")

            write_publish_state(root, state)
            restored = load_publish_state(root)

        self.assertEqual(restored, state)
        self.assertIsNone(restored.remote_course_id)

    def test_remote_fields_cannot_exist_without_remote_identity(self):
        with self.assertRaisesRegex(ValueError, "remoteCourseId"):
            PublishState(
                schema_version="1.0",
                course_local_id="course-local-a",
                slug="evidence-course",
                remote_status=None,
                remote_course_id=None,
                last_known_remote_revision=None,
                last_uploaded_definition_hash=HASH,
                last_published_definition_hash=None,
                last_publish_operation_id=None,
                verified_at=None,
            )

    def test_publish_state_rejects_unknown_serialized_fields(self):
        data = new_publish_state("course-local-a", "evidence-course").as_dict()
        data["schemaRevision"] = "not-the-course-definition-schema-version"

        with self.assertRaisesRegex(ValueError, "Unknown publish state field"):
            PublishState.from_dict(data)


class PublicationIdentityResolutionTests(unittest.TestCase):
    def test_create_requires_explicit_not_found_discovery(self):
        state = new_publish_state("course-local-a", "evidence-course")

        resolution = resolve_publication_identity(state, discovery())

        self.assertEqual(resolution.mode, "create")
        self.assertIsNone(resolution.remote_course_id)
        self.assertIsNone(resolution.expected_remote_revision)

    def test_matching_verified_identity_resolves_update(self):
        state = PublishState(
            schema_version="1.0",
            course_local_id="course-local-a",
            slug="evidence-course",
            remote_course_id="remote-course-1",
            remote_status="preview",
            last_known_remote_revision="revision-7",
            last_uploaded_definition_hash=HASH,
            last_published_definition_hash=None,
            last_publish_operation_id="c" * 64,
            verified_at=NOW,
        )

        resolution = resolve_publication_identity(state, discovery("found"))

        self.assertEqual(resolution.mode, "update")
        self.assertEqual(resolution.remote_course_id, "remote-course-1")
        self.assertEqual(resolution.expected_remote_revision, "revision-7")

    def test_existing_slug_without_local_identity_is_never_silently_adopted(self):
        state = new_publish_state("course-local-a", "evidence-course")

        with self.assertRaisesRegex(PublicationBlocked, "already exists"):
            resolve_publication_identity(state, discovery("found"))

    def test_remote_id_mismatch_is_blocked(self):
        state = PublishState(
            schema_version="1.0",
            course_local_id="course-local-a",
            slug="evidence-course",
            remote_course_id="remote-course-1",
            remote_status="preview",
            last_known_remote_revision="revision-7",
            last_uploaded_definition_hash=HASH,
            last_published_definition_hash=None,
            last_publish_operation_id="c" * 64,
            verified_at=NOW,
        )

        with self.assertRaisesRegex(PublicationBlocked, "identity mismatch"):
            resolve_publication_identity(
                state,
                discovery("found", remote_course_id="remote-course-2"),
            )

    def test_remote_revision_drift_requires_reconciliation(self):
        state = PublishState(
            schema_version="1.0",
            course_local_id="course-local-a",
            slug="evidence-course",
            remote_course_id="remote-course-1",
            remote_status="preview",
            last_known_remote_revision="revision-6",
            last_uploaded_definition_hash=HASH,
            last_published_definition_hash=None,
            last_publish_operation_id="c" * 64,
            verified_at=NOW,
        )

        with self.assertRaisesRegex(PublicationBlocked, "revision changed"):
            resolve_publication_identity(state, discovery("found"))

    def test_ambiguous_and_unavailable_discovery_are_blockers(self):
        state = new_publish_state("course-local-a", "evidence-course")
        for status in ("ambiguous", "unavailable"):
            with self.subTest(status=status):
                with self.assertRaisesRegex(PublicationBlocked, status):
                    resolve_publication_identity(
                        state,
                        discovery(status, message=f"{status} discovery"),
                    )

    def test_discovery_rejects_duplicate_remote_asset_claims(self):
        duplicate = {
            "sha256": "b" * 64,
            "objectKey": "courses/course-local-a/assets/bb/other.pdf",
        }

        with self.assertRaisesRegex(ValueError, "duplicate sha256"):
            discovery("found", known_assets=discovery("found").known_assets + (duplicate,))


if __name__ == "__main__":
    unittest.main()
