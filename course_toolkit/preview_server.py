import json
import mimetypes
import secrets
import subprocess
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import unquote, urlsplit

from course_toolkit.annotations import AnnotationStore, CourseAnnotation
from course_toolkit.hashing import canonical_json_hash
from course_toolkit.jsonio import load_json, write_json_atomic
from course_toolkit.preview_evidence import record_preview_evidence


LOOPBACK_HOST = "127.0.0.1"
MAX_JSON_BYTES = 2 * 1024 * 1024
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_STATIC_DIR = ROOT / "course_toolkit" / "runtime_dist" / "preview"
CONTRACT_VALIDATOR = ROOT / "course_toolkit" / "runtime_dist" / "validate-course-definition.mjs"


def preview_scope_notice(url: str) -> str:
    return (
        f"本地预览：{url}\n"
        "这个链接只能在这台电脑上查看。若要让其他人预览，需要先保存或发布到学生端。"
    )


def _safe_file(base: Path, raw_relative: str) -> Path:
    decoded = unquote(raw_relative)
    candidate = Path(decoded)
    if (
        not decoded
        or decoded.startswith("/")
        or "\\" in decoded
        or candidate.is_absolute()
        or any(part in {"", ".", ".."} for part in candidate.parts)
    ):
        raise ValueError("unsafe preview path")
    current = base.resolve()
    if base.is_symlink() or not current.is_dir():
        raise PermissionError("preview root is unavailable")
    for part in candidate.parts:
        current = current / part
        if current.is_symlink():
            raise PermissionError("preview path crosses a symlink")
    resolved = current.resolve()
    resolved_base = base.resolve()
    if resolved_base not in resolved.parents:
        raise PermissionError("preview path escapes its root")
    if not resolved.is_file():
        raise FileNotFoundError(decoded)
    return resolved


def _validate_annotation_document(payload: object, path: Path) -> None:
    if not isinstance(payload, dict):
        raise ValueError("annotation document must be an object")
    if set(payload) != {"schemaVersion", "annotations"}:
        raise ValueError("annotation document has unknown or missing fields")
    if payload.get("schemaVersion") != "1.0":
        raise ValueError("unsupported annotation schemaVersion")
    raw = payload.get("annotations")
    if not isinstance(raw, list):
        raise ValueError("annotations must be an array")
    annotations = [CourseAnnotation.from_dict(item) for item in raw]
    AnnotationStore(path, annotations)


class CoursePreviewHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: Tuple[str, int], root: Path, static_dir: Path, *, inspection: bool = False):
        self.course_project_root = root.resolve()
        self.course_root = self.course_project_root / "course"
        self.static_dir = static_dir.resolve()
        self.annotations_path = self.course_project_root / ".course-work" / "annotations.json"
        self.inspection = inspection
        self.inspection_nonce = secrets.token_urlsafe(24) if inspection else None
        self.inspection_observations_path = self.course_project_root / ".course-work" / "visual-check" / "inspection-observations.json"
        self.pinned_document = load_json(self.course_root / "course.json")
        self.pinned_definition_hash = canonical_json_hash(self.pinned_document)
        self.slice_block_ids = {
            page["id"]: {
                block["id"]
                for block in page.get("blocks", [])
                if isinstance(block, dict) and isinstance(block.get("id"), str)
            }
            for part in self.pinned_document.get("course", {}).get("parts", [])
            for page in part.get("slices", [])
            if isinstance(page, dict) and isinstance(page.get("id"), str)
        }
        self.known_slice_ids = set(self.slice_block_ids)
        self.expected_inspection_states = [
            f"{part['id']}/{page['id']}/default"
            for part in self.pinned_document.get("course", {}).get("parts", [])
            for page in part.get("slices", [])
            if isinstance(part, dict)
            and isinstance(part.get("id"), str)
            and isinstance(page, dict)
            and isinstance(page.get("id"), str)
        ]
        super().__init__(address, CoursePreviewRequestHandler)

class CoursePreviewRequestHandler(BaseHTTPRequestHandler):
    server: CoursePreviewHTTPServer

    def log_message(self, format: str, *args: object) -> None:
        return

    def _send_bytes(
        self,
        status: int,
        body: bytes,
        content_type: str,
        *,
        no_store: bool = False,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        if no_store:
            self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, status: int, payload: object) -> None:
        body = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        self._send_bytes(status, body, "application/json; charset=utf-8", no_store=True)

    def _error(self, status: int, code: str, message: str) -> None:
        self._send_json(status, {"ok": False, "error": {"code": code, "message": message}})

    def _read_json(self) -> object:
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            raise ValueError("Content-Length is required")
        try:
            length = int(raw_length)
        except ValueError as exc:
            raise ValueError("invalid Content-Length") from exc
        if length < 0 or length > MAX_JSON_BYTES:
            raise ValueError("JSON body exceeds preview size limit")
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("request body must be valid UTF-8 JSON") from exc

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        try:
            if path == "/__course_preview/document":
                self._send_json(HTTPStatus.OK, self.server.pinned_document)
                return
            if path == "/__course_preview/inspection/config":
                if not self.server.inspection:
                    self._error(HTTPStatus.NOT_FOUND, "inspection_disabled", "inspection mode is not active")
                    return
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "inspection": True,
                        "nonce": self.server.inspection_nonce,
                        "definitionHash": self.server.pinned_definition_hash,
                        "expectedStates": self.server.expected_inspection_states,
                    },
                )
                return
            if path == "/__course_preview/annotations":
                if self.server.annotations_path.is_file():
                    payload = load_json(self.server.annotations_path)
                else:
                    payload = {"schemaVersion": "1.0", "annotations": []}
                self._send_json(HTTPStatus.OK, payload)
                return
            if path.startswith("/course-assets/"):
                asset = _safe_file(self.server.course_root, path[len("/course-assets/") :])
                mime = mimetypes.guess_type(asset.name)[0] or "application/octet-stream"
                self._send_bytes(HTTPStatus.OK, asset.read_bytes(), mime)
                return
            relative = "index.html" if path == "/" else path.lstrip("/")
            static_file = _safe_file(self.server.static_dir, relative)
            mime = mimetypes.guess_type(static_file.name)[0] or "application/octet-stream"
            self._send_bytes(HTTPStatus.OK, static_file.read_bytes(), mime, no_store=True)
        except ValueError as exc:
            self._error(HTTPStatus.BAD_REQUEST, "unsafe-path", str(exc))
        except PermissionError as exc:
            self._error(HTTPStatus.FORBIDDEN, "path-forbidden", str(exc))
        except FileNotFoundError:
            self._error(HTTPStatus.NOT_FOUND, "not-found", "preview resource not found")
        except Exception as exc:
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, "preview-read-error", str(exc))

    def do_PUT(self) -> None:
        path = urlsplit(self.path).path
        if path != "/__course_preview/annotations":
            self._error(HTTPStatus.METHOD_NOT_ALLOWED, "write-forbidden", "preview writes are limited to annotations")
            return
        try:
            payload = self._read_json()
            _validate_annotation_document(payload, self.server.annotations_path)
            write_json_atomic(self.server.annotations_path, payload)
            self._send_json(HTTPStatus.OK, {"ok": True})
        except ValueError as exc:
            self._error(HTTPStatus.BAD_REQUEST, "invalid-annotations", str(exc))
        except Exception as exc:
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, "annotation-write-error", str(exc))

    def do_POST(self) -> None:
        path = urlsplit(self.path).path
        if path == "/__course_preview/inspection/observations":
            if not self.server.inspection:
                self._error(HTTPStatus.METHOD_NOT_ALLOWED, "inspection_disabled", "inspection mode is not active")
                return
            try:
                payload = self._read_json()
                observation = _validate_inspection_observation(payload, self.server)
                existing = (
                    load_json(self.server.inspection_observations_path)
                    if self.server.inspection_observations_path.is_file()
                    else {"schemaVersion": "1.0", "definitionHash": self.server.pinned_definition_hash, "observations": []}
                )
                observations = [item for item in existing.get("observations", []) if item.get("stateId") != observation["stateId"]]
                observations.append(observation)
                observations.sort(key=lambda item: item["stateId"])
                write_json_atomic(
                    self.server.inspection_observations_path,
                    {"schemaVersion": "1.0", "definitionHash": self.server.pinned_definition_hash, "observations": observations},
                )
                self._send_json(HTTPStatus.OK, {"ok": True, "stateId": observation["stateId"]})
            except ValueError as exc:
                self._error(HTTPStatus.BAD_REQUEST, "invalid-inspection-observation", str(exc))
            except Exception as exc:
                self._error(HTTPStatus.INTERNAL_SERVER_ERROR, "inspection-write-error", str(exc))
            return
        if path != "/__course_preview/evidence":
            self._error(HTTPStatus.METHOD_NOT_ALLOWED, "write-forbidden", "unsupported preview write")
            return
        try:
            payload = self._read_json()
            manifest = record_preview_evidence(self.server.course_project_root, payload)
            self._send_json(
                HTTPStatus.OK,
                {"ok": True, "definitionHash": manifest["definitionHash"]},
            )
        except ValueError as exc:
            self._error(HTTPStatus.BAD_REQUEST, "invalid-preview-evidence", str(exc))
        except Exception as exc:
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, "evidence-write-error", str(exc))

    def do_DELETE(self) -> None:
        self._error(HTTPStatus.METHOD_NOT_ALLOWED, "delete-forbidden", "preview has no delete endpoint")


def create_preview_server(
    root: Path,
    *,
    host: str = LOOPBACK_HOST,
    port: int = 0,
    static_dir: Optional[Path] = None,
    inspection: bool = False,
) -> CoursePreviewHTTPServer:
    if host != LOOPBACK_HOST:
        raise ValueError("course preview may bind only to 127.0.0.1")
    selected_static = static_dir or DEFAULT_STATIC_DIR
    return CoursePreviewHTTPServer((host, port), root, selected_static, inspection=inspection)


def _validate_inspection_observation(payload: object, server: CoursePreviewHTTPServer) -> dict:
    fields = {"nonce", "definitionHash", "stateId", "sliceId", "viewport", "blocks", "overflow", "runtimeErrors"}
    if not isinstance(payload, dict) or set(payload) != fields:
        raise ValueError("inspection observation has unknown or missing fields")
    if payload.get("nonce") != server.inspection_nonce or payload.get("definitionHash") != server.pinned_definition_hash:
        raise ValueError("inspection nonce or definition hash does not match this launch")
    slice_id = payload.get("sliceId")
    if slice_id not in server.known_slice_ids:
        raise ValueError("inspection observation refers to an unknown Slice")
    state_id = payload.get("stateId")
    if state_id not in server.expected_inspection_states or not state_id.endswith(f"/{slice_id}/default"):
        raise ValueError("inspection stateId does not match its Slice")
    viewport = payload.get("viewport")
    if not isinstance(viewport, dict) or set(viewport) != {"width", "height"} or not all(isinstance(viewport.get(key), int) and viewport[key] > 0 for key in ("width", "height")):
        raise ValueError("inspection viewport is invalid")
    blocks = payload.get("blocks")
    if not isinstance(blocks, list):
        raise ValueError("inspection blocks must be an array")
    normalized_blocks = []
    seen = set()
    for block in blocks:
        if not isinstance(block, dict) or set(block) != {"blockId", "x", "y", "width", "height", "visible", "enabled"}:
            raise ValueError("inspection Block observation is invalid")
        block_id = block.get("blockId")
        if block_id not in server.slice_block_ids[slice_id] or block_id in seen:
            raise ValueError("inspection Block ID is unknown or duplicated")
        seen.add(block_id)
        if not all(isinstance(block.get(key), (int, float)) and not isinstance(block.get(key), bool) for key in ("x", "y", "width", "height")):
            raise ValueError("inspection Block rectangle is invalid")
        if not isinstance(block.get("visible"), bool) or not isinstance(block.get("enabled"), bool):
            raise ValueError("inspection Block state is invalid")
        normalized_blocks.append(block)
    overflow = payload.get("overflow")
    if not isinstance(overflow, dict) or set(overflow) != {"horizontal", "vertical"} or not all(isinstance(overflow.get(key), bool) for key in overflow):
        raise ValueError("inspection overflow observation is invalid")
    errors = payload.get("runtimeErrors")
    if not isinstance(errors, list) or any(not isinstance(item, str) for item in errors):
        raise ValueError("inspection runtimeErrors must be strings")
    return {
        "stateId": state_id,
        "sliceId": slice_id,
        "viewport": viewport,
        "blocks": sorted(normalized_blocks, key=lambda item: item["blockId"]),
        "overflow": overflow,
        "runtimeErrors": errors,
    }


def validate_preview_prerequisites(root: Path, *, static_dir: Optional[Path] = None) -> dict:
    root = root.resolve()
    selected_static = (static_dir or DEFAULT_STATIC_DIR).resolve()
    index = selected_static / "index.html"
    document_path = root / "course" / "course.json"
    if selected_static.is_symlink() or not index.is_file():
        raise ValueError("preview runtime bundle is missing")
    if document_path.is_symlink() or not document_path.is_file():
        raise ValueError("course/course.json is missing")
    if not CONTRACT_VALIDATOR.is_file():
        raise ValueError("bundled CourseDefinition validator is missing")
    completed = subprocess.run(
        ["node", str(CONTRACT_VALIDATOR), str(document_path), "--json"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError("CourseDefinition validator returned unreadable output") from exc
    if completed.returncode != 0 or payload.get("ok") is not True:
        issues = payload.get("issues") if isinstance(payload, dict) else None
        detail = issues[0].get("message") if isinstance(issues, list) and issues and isinstance(issues[0], dict) else payload.get("error", "invalid CourseDefinition")
        raise ValueError(f"course/course.json is not previewable: {detail}")
    return payload


def validate_inspection_prerequisites(root: Path, *, static_dir: Optional[Path] = None) -> dict:
    # Inspection is an action in the authoring flow, not a historical-evidence
    # gate. Older courses may not have G5/G6 records, but they can still be
    # inspected whenever their current CourseDefinition renders successfully.
    return validate_preview_prerequisites(root, static_dir=static_dir)
