#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import sys
from dataclasses import dataclass
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urlparse
from urllib.request import Request, urlopen

REPO_ROOT = Path(__file__).resolve().parent.parent
OPERATOR_DIR = Path(__file__).resolve().parent
DEFAULT_REPO = os.environ.get("PBP_OPERATOR_REPO", "victorres11/pbp-analysis")
DEFAULT_WORKFLOW = os.environ.get("PBP_OPERATOR_WORKFLOW_FILE", "brief-live-refresh.yml")
DEFAULT_BRANCH = os.environ.get("PBP_OPERATOR_BRANCH", "main")
TOKEN_ENV = "PBP_OPERATOR_GITHUB_TOKEN"


@dataclass(frozen=True)
class OperatorConfig:
    github_token: str
    repo: str
    workflow_file: str
    branch: str


class ProxyError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


class GitHubProxy:
    def __init__(self, config: OperatorConfig) -> None:
        escaped_repo = re.escape(config.repo)
        self._config = config
        self._dispatch_pattern = re.compile(
            rf"^/repos/{escaped_repo}/actions/workflows/[^/]+/dispatches$"
        )
        self._runs_pattern = re.compile(
            rf"^/repos/{escaped_repo}/actions/workflows/[^/]+/runs$"
        )
        self._release_tag_pattern = re.compile(rf"^/repos/{escaped_repo}/releases/tags/[^/]+$")
        self._release_asset_pattern = re.compile(rf"^/repos/{escaped_repo}/releases/assets/\d+$")
        self._run_artifacts_pattern = re.compile(rf"^/repos/{escaped_repo}/actions/runs/\d+/artifacts$")
        self._artifact_download_pattern = re.compile(rf"^/repos/{escaped_repo}/actions/artifacts/\d+/zip$")

    def request_json(
        self,
        path_or_url: str,
        *,
        method: str = "GET",
        accept: str = "application/vnd.github+json",
        body: Any = None,
    ) -> tuple[int, bytes]:
        status, content_type, payload, _headers = self._request(
            path_or_url,
            method=method,
            accept=accept,
            body=body,
        )
        if status == HTTPStatus.NO_CONTENT:
            return status, b""

        try:
            decoded = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ProxyError(HTTPStatus.BAD_GATEWAY, f"GitHub response was not UTF-8 decodable: {exc}") from exc

        if content_type.startswith("application/json") or accept == "application/octet-stream":
            try:
                normalized = json.loads(decoded)
            except json.JSONDecodeError:
                normalized = decoded
        else:
            normalized = decoded

        return HTTPStatus.OK, json.dumps(normalized).encode("utf-8")

    def request_binary(
        self,
        path_or_url: str,
        *,
        accept: str = "application/octet-stream",
    ) -> tuple[int, str, bytes]:
        status, content_type, payload, _headers = self._request(
            path_or_url,
            method="GET",
            accept=accept,
            body=None,
        )
        return status, content_type or "application/octet-stream", payload

    def _request(
        self,
        path_or_url: str,
        *,
        method: str,
        accept: str,
        body: Any,
    ) -> tuple[int, str, bytes, dict[str, str]]:
        normalized_url, normalized_path = self._normalize_target(path_or_url)
        normalized_method = method.upper()
        self._validate_request(normalized_path, normalized_method)

        headers = {
            "Accept": accept,
            "Authorization": f"Bearer {self._config.github_token}",
            "User-Agent": "pbp-operator-proxy/1.0",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode("utf-8")

        request = Request(normalized_url, data=data, headers=headers, method=normalized_method)
        try:
            with urlopen(request, timeout=30) as response:
                payload = response.read()
                response_headers = {key: value for key, value in response.headers.items()}
                return response.status, response.headers.get_content_type(), payload, response_headers
        except HTTPError as exc:
            message = self._extract_error_message(exc)
            raise ProxyError(exc.code, message) from exc
        except URLError as exc:
            raise ProxyError(HTTPStatus.BAD_GATEWAY, f"GitHub request failed: {exc.reason}") from exc

    def _normalize_target(self, path_or_url: str) -> tuple[str, str]:
        if not isinstance(path_or_url, str) or not path_or_url:
            raise ProxyError(HTTPStatus.BAD_REQUEST, "Missing GitHub target path.")

        parsed = urlparse(path_or_url)
        if parsed.scheme:
            if parsed.scheme != "https" or parsed.netloc != "api.github.com":
                raise ProxyError(HTTPStatus.BAD_REQUEST, "Only GitHub API URLs are allowed.")
            path = parsed.path
            query = f"?{parsed.query}" if parsed.query else ""
            return path_or_url, f"{path}{query}"

        if not path_or_url.startswith("/"):
            raise ProxyError(HTTPStatus.BAD_REQUEST, "GitHub API paths must start with '/'.")
        return f"https://api.github.com{path_or_url}", path_or_url

    def _validate_request(self, path_with_query: str, method: str) -> None:
        parsed = urlparse(path_with_query)
        path = parsed.path
        if self._dispatch_pattern.fullmatch(path):
            if method != "POST":
                raise ProxyError(HTTPStatus.METHOD_NOT_ALLOWED, "Workflow dispatch requires POST.")
            return

        if method != "GET":
            raise ProxyError(HTTPStatus.METHOD_NOT_ALLOWED, "Only GET is allowed for this GitHub resource.")

        if self._runs_pattern.fullmatch(path):
            return
        if self._release_tag_pattern.fullmatch(path):
            return
        if self._release_asset_pattern.fullmatch(path):
            return
        if self._run_artifacts_pattern.fullmatch(path):
            return
        if self._artifact_download_pattern.fullmatch(path):
            return

        raise ProxyError(HTTPStatus.FORBIDDEN, "That GitHub resource is not exposed by the operator proxy.")

    def _extract_error_message(self, error: HTTPError) -> str:
        payload = error.read()
        if not payload:
            return f"GitHub API request failed ({error.code})."
        try:
            decoded = payload.decode("utf-8")
        except UnicodeDecodeError:
            return f"GitHub API request failed ({error.code})."
        try:
            message = json.loads(decoded).get("message")
        except json.JSONDecodeError:
            message = decoded.strip()
        if not message:
            return f"GitHub API request failed ({error.code})."
        return f"{message} ({error.code})"


class OperatorRequestHandler(SimpleHTTPRequestHandler):
    server_version = "PbpOperator/1.0"

    def __init__(self, *args: Any, directory: str | None = None, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(OPERATOR_DIR), **kwargs)

    @property
    def config(self) -> OperatorConfig:
        return self.server.operator_config  # type: ignore[attr-defined]

    @property
    def proxy(self) -> GitHubProxy:
        return self.server.github_proxy  # type: ignore[attr-defined]

    def do_GET(self) -> None:  # noqa: N802
        self._handle_request(head_only=False)

    def do_HEAD(self) -> None:  # noqa: N802
        self._handle_request(head_only=True)

    def _handle_request(self, *, head_only: bool) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._redirect("/operator/", head_only=head_only)
            return
        if parsed.path == "/operator":
            self._redirect("/operator/", head_only=head_only)
            return
        if parsed.path == "/health":
            self._send_json(
                HTTPStatus.OK,
                {
                    "status": "ok",
                    "repo": self.config.repo,
                    "workflow_file": self.config.workflow_file,
                    "branch": self.config.branch,
                    "has_github_token": bool(self.config.github_token),
                    "operator_dir": str(OPERATOR_DIR),
                },
                include_body=not head_only,
            )
            return
        if head_only and parsed.path == "/api/operator/download":
            self.send_error(HTTPStatus.METHOD_NOT_ALLOWED)
            return
        if parsed.path == "/api/operator/download":
            self._handle_download(parsed.query)
            return
        if parsed.path.startswith("/operator/"):
            self._serve_operator_asset(parsed.path.removeprefix("/operator/"), include_body=not head_only)
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/api/operator/github":
            self._handle_github_proxy()
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def log_message(self, format: str, *args: Any) -> None:
        sys.stderr.write(f"[pbp-operator] {self.address_string()} - {format % args}\n")

    def _handle_github_proxy(self) -> None:
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_payload = self.rfile.read(content_length) if content_length else b"{}"
            payload = json.loads(raw_payload.decode("utf-8"))
            status, response_payload = self.proxy.request_json(
                payload.get("pathOrUrl", ""),
                method=payload.get("method", "GET"),
                accept=payload.get("accept", "application/vnd.github+json"),
                body=payload.get("body"),
            )
            self.send_response(status)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(response_payload)))
            self.end_headers()
            if response_payload:
                self.wfile.write(response_payload)
        except json.JSONDecodeError:
            self._send_json(HTTPStatus.BAD_REQUEST, {"message": "Request body must be valid JSON."})
        except ProxyError as exc:
            self._send_json(exc.status, {"message": exc.message})
        except Exception as exc:  # pragma: no cover - defensive fallback
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"message": f"Operator proxy failed: {exc}"})

    def _handle_download(self, query: str) -> None:
        params = parse_qs(query, keep_blank_values=False)
        path_or_url = params.get("pathOrUrl", [""])[0]
        filename = params.get("filename", [""])[0]
        accept = params.get("accept", ["application/octet-stream"])[0]

        try:
            status, content_type, payload = self.proxy.request_binary(path_or_url, accept=accept)
        except ProxyError as exc:
            self._send_json(exc.status, {"message": exc.message})
            return

        safe_name = filename.strip() or "download"
        self.send_response(status)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Content-Disposition", f'attachment; filename="{safe_name}"')
        self.end_headers()
        self.wfile.write(payload)

    def _redirect(self, location: str, *, head_only: bool = False) -> None:
        self.send_response(HTTPStatus.FOUND)
        self.send_header("Location", location)
        self.end_headers()
        if head_only:
            return

    def _serve_operator_asset(self, relative_path: str, *, include_body: bool) -> None:
        normalized = relative_path.lstrip("/") or "index.html"
        candidate = (OPERATOR_DIR / normalized).resolve()
        if OPERATOR_DIR not in candidate.parents and candidate != OPERATOR_DIR:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        if not candidate.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        payload = candidate.read_bytes()
        content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"

        self.send_response(HTTPStatus.OK)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if include_body:
            self.wfile.write(payload)

    def _send_json(self, status: int, payload: Any, *, include_body: bool = True) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        if include_body:
            self.wfile.write(encoded)


def load_config() -> OperatorConfig:
    token = os.environ.get(TOKEN_ENV, "").strip()
    if not token:
        raise SystemExit(f"{TOKEN_ENV} must be set before starting the operator server.")
    return OperatorConfig(
        github_token=token,
        repo=DEFAULT_REPO,
        workflow_file=DEFAULT_WORKFLOW,
        branch=DEFAULT_BRANCH,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve the private operator UI with a server-side GitHub proxy.")
    parser.add_argument("--host", default=os.environ.get("PBP_OPERATOR_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PBP_OPERATOR_PORT", "8787")))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config()
    server = ThreadingHTTPServer((args.host, args.port), OperatorRequestHandler)
    server.operator_config = config  # type: ignore[attr-defined]
    server.github_proxy = GitHubProxy(config)  # type: ignore[attr-defined]
    print(
        f"Serving operator UI for {config.repo} on http://{args.host}:{args.port}/operator/",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
