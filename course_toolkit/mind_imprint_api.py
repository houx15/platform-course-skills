import json
import os
import http.client
import hashlib
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


DEFAULT_API_BASE = "https://mind-api.uni-robot.cn"
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
MAX_COVER_BYTES = 20 * 1024 * 1024
VALID_CATEGORIES = {
    "stance-value",
    "source-check",
    "media-literacy",
    "self-knowledge",
    "data-literacy",
    "research-process",
    "argument-writing",
}


class MindImprintApiError(RuntimeError):
    def __init__(self, message: str, *, status: Optional[int] = None, code: Optional[str] = None):
        super().__init__(message)
        self.status = status
        self.code = code


class AmbiguousRemoteWrite(MindImprintApiError):
    pass


@dataclass(frozen=True)
class RemoteCourse:
    slug: str
    status: str
    definition_hash: str
    definition: dict


class MindImprintAuthoringApi:
    # course-authoring-v1.4.0 supports a safe course-relative WebP cover path.
    supports_course_asset_cover = True

    def __init__(self, api_base: str, admin_key: str, *, timeout: float = 30.0):
        parsed = urllib.parse.urlsplit(api_base)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("api_base must be an HTTP(S) origin")
        if not admin_key:
            raise ValueError("OSS_ADMIN_KEY is required")
        self.api_base = api_base.rstrip("/")
        self.__admin_key = admin_key
        self.timeout = timeout

    def _sanitize(self, message: str) -> str:
        return message.replace(self.__admin_key, "[REDACTED]").replace("Authorization: Bearer", "Authorization: [REDACTED]")

    @classmethod
    def from_environment(
        cls,
        *,
        api_base: str = DEFAULT_API_BASE,
        timeout: float = 30.0,
    ) -> "MindImprintAuthoringApi":
        key = os.environ.get("OSS_ADMIN_KEY", "")
        if not key:
            raise MindImprintApiError("OSS_ADMIN_KEY is not set")
        return cls(api_base, key, timeout=timeout)

    def _decode(self, response) -> dict:
        raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise MindImprintApiError("remote response exceeded the safe size limit")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise MindImprintApiError("remote response was not valid JSON") from exc
        if not isinstance(payload, dict):
            raise MindImprintApiError("remote response must be a JSON object")
        return payload

    def _api_request(
        self,
        method: str,
        path: str,
        body: Optional[dict] = None,
        *,
        write: bool = False,
        allow_not_found: bool = False,
    ) -> Optional[dict]:
        data = None if body is None else json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        request = urllib.request.Request(
            self.api_base + path,
            data=data,
            method=method,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {self.__admin_key}",
                **({"Content-Type": "application/json"} if data is not None else {}),
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return self._decode(response)
        except urllib.error.HTTPError as exc:
            if allow_not_found and exc.code == 404:
                return None
            raw = exc.read(64 * 1024)
            code = None
            message = f"authoring API returned HTTP {exc.code}"
            try:
                error = json.loads(raw.decode("utf-8"))
                if isinstance(error, dict):
                    code = error.get("code") or error.get("error", {}).get("code")
                    remote_message = error.get("message") or error.get("error", {}).get("message")
                    if isinstance(remote_message, str) and remote_message:
                        message = self._sanitize(remote_message)
            except (UnicodeError, json.JSONDecodeError, AttributeError, TypeError):
                pass
            raise MindImprintApiError(self._sanitize(message), status=exc.code, code=code) from None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            error_type = AmbiguousRemoteWrite if write else MindImprintApiError
            raise error_type("authoring API request failed without a definitive response") from None

    def list_courses(self) -> list:
        payload = self._api_request("GET", "/api/v1/admin/courses")
        courses = payload.get("courses") if payload else None
        if not isinstance(courses, list):
            raise MindImprintApiError("course list response is invalid")
        return courses

    def get_course(self, slug: str) -> Optional[RemoteCourse]:
        payload = self._api_request(
            "GET",
            f"/api/v1/admin/courses/{urllib.parse.quote(slug, safe='')}/definition",
            allow_not_found=True,
        )
        if payload is None:
            return None
        definition = payload.get("definition")
        definition_hash = payload.get("hash")
        status = payload.get("status")
        if not isinstance(definition, dict) or not isinstance(definition_hash, str) or status not in {"preview", "published"}:
            raise MindImprintApiError("course readback response is invalid")
        return RemoteCourse(slug, status, definition_hash, definition)

    def plan_asset_upload(self, slug: str, relative_path: str, content_type: str, size: int) -> dict:
        payload = self._api_request(
            "POST",
            f"/api/v1/admin/courses/{urllib.parse.quote(slug, safe='')}/asset-upload-url",
            {"relativePath": relative_path, "contentType": content_type, "size": size},
            write=True,
        )
        required = {"putUrl", "objectKey", "requiredContentType", "maxBytes", "expiresAt"}
        if payload is None or not required.issubset(payload):
            raise MindImprintApiError("asset upload plan response is invalid")
        return payload

    def upload_asset(self, put_url: str, local_path: Path, required_content_type: str) -> Optional[str]:
        parsed = urllib.parse.urlsplit(put_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise MindImprintApiError("presigned upload URL is invalid")
        if local_path.is_symlink() or not local_path.is_file():
            raise MindImprintApiError("local upload asset is missing or unsafe")
        target = urllib.parse.urlunsplit(("", "", parsed.path or "/", parsed.query, ""))
        connection_type = (
            http.client.HTTPSConnection
            if parsed.scheme == "https"
            else http.client.HTTPConnection
        )
        connection = connection_type(parsed.hostname, parsed.port, timeout=self.timeout)
        try:
            connection.putrequest("PUT", target, skip_accept_encoding=True)
            connection.putheader("Content-Type", required_content_type)
            connection.putheader("Content-Length", str(local_path.stat().st_size))
            connection.endheaders()
            with local_path.open("rb") as source:
                while True:
                    chunk = source.read(1024 * 1024)
                    if not chunk:
                        break
                    connection.send(chunk)
            response = connection.getresponse()
            response.read(64 * 1024)
            if not 200 <= response.status < 300:
                raise MindImprintApiError(
                    f"OSS upload returned HTTP {response.status}",
                    status=response.status,
                )
            return response.getheader("ETag")
        except MindImprintApiError:
            raise
        except (http.client.HTTPException, TimeoutError, OSError):
            raise AmbiguousRemoteWrite("OSS upload failed without a definitive response") from None
        finally:
            connection.close()

    def save_definition(
        self,
        slug: str,
        definition: dict,
        *,
        blurb: str,
        card_ids: list[str],
        category: str,
        introduction: dict,
    ) -> dict:
        if category not in VALID_CATEGORIES:
            raise MindImprintApiError("category is not one of the seven supported course categories")
        expected_introduction_keys = {"hook", "whatYouDo", "takeaways", "alignment", "keywords"}
        if not isinstance(introduction, dict) or set(introduction) != expected_introduction_keys:
            raise MindImprintApiError("introduction does not match the student authoring v1.4.0 contract")
        payload = self._api_request(
            "PUT",
            f"/api/v1/admin/courses/{urllib.parse.quote(slug, safe='')}/definition",
            {
                "definition": definition,
                "blurb": blurb,
                "cardIds": card_ids,
                "category": category,
                "introduction": introduction,
            },
            write=True,
        )
        if payload is None or payload.get("slug") != slug or payload.get("status") not in {"preview", "published"}:
            raise MindImprintApiError("definition write response is invalid")
        return payload

    def ship(self, slug: str, *, cover: str, cover_asset_path: Optional[str] = None) -> dict:
        if cover and cover_asset_path:
            raise MindImprintApiError("stock cover and coverAssetPath are mutually exclusive")
        if cover_asset_path and not self.supports_course_asset_cover:
            raise MindImprintApiError(
                "the pinned student authoring API cannot bind a generated course cover"
            )
        if cover_asset_path and (
            not cover_asset_path.startswith("cover/")
            or not cover_asset_path.endswith(".webp")
            or ".." in cover_asset_path.split("/")
            or cover_asset_path.startswith("/")
        ):
            raise MindImprintApiError("coverAssetPath must be a safe cover/*.webp relative path")
        body = {"cover": cover}
        if cover_asset_path:
            body["coverAssetPath"] = cover_asset_path
        payload = self._api_request(
            "POST",
            f"/api/v1/admin/courses/{urllib.parse.quote(slug, safe='')}/ship",
            body,
            write=True,
        )
        if payload is None or payload.get("slug") != slug or payload.get("status") != "published":
            raise MindImprintApiError("ship response is invalid")
        return payload

    def verify_published_cover(
        self,
        slug: str,
        expected_sha256: str,
    ) -> dict:
        if not isinstance(expected_sha256, str) or re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None:
            raise MindImprintApiError("fixed catalog cover hash is invalid")
        matching = [course for course in self.list_courses() if isinstance(course, dict) and course.get("slug") == slug]
        if len(matching) != 1:
            raise MindImprintApiError("published course summary could not be identified uniquely")
        cover_url = matching[0].get("coverUrl")
        if not isinstance(cover_url, str) or not cover_url:
            raise MindImprintApiError("published course summary has no fixed coverUrl")
        parsed = urllib.parse.urlsplit(cover_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise MindImprintApiError("published course coverUrl is invalid")
        request = urllib.request.Request(cover_url, method="GET", headers={"Accept": "image/webp"})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read(MAX_COVER_BYTES + 1)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError):
            raise MindImprintApiError("published course coverUrl could not be read") from None
        if len(raw) > MAX_COVER_BYTES:
            raise MindImprintApiError("published course cover exceeded the safe size limit")
        remote_sha256 = hashlib.sha256(raw).hexdigest()
        if remote_sha256 != expected_sha256:
            raise MindImprintApiError("published course cover bytes do not match the approved upload")
        return {
            "coverUrlPresent": True,
            "sha256": remote_sha256,
            "sizeBytes": len(raw),
        }
