"""Actual OpenTakeoff MCP subprocess runtime adapter.

This module launches a pinned local ``opentakeoff-mcp`` Node package and speaks
MCP JSON-RPC over stdio. It keeps stdout reserved for MCP protocol, captures
bounded redacted stderr diagnostics, and exposes only benchmark-supported tools.
"""

from __future__ import annotations

import json
import os
import queue
import re
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.takeoff.worker import OpenTakeoffScaleConfirmation, OpenTakeoffWorkerErrorCode

OPEN_TAKEOFF_MCP_PACKAGE = "opentakeoff-mcp"
OPEN_TAKEOFF_MCP_VERSION = "0.1.1"
OPEN_TAKEOFF_MCP_INTEGRITY = (
    "sha512-AEVE+dxJn3/YS/7xo8QC8g5mC+m1r0eq3lp/OWXeTehd2rg3YL4I2tJjP7VayQW3TcRW7p9VFmWzKhBdhLH3rg=="
)
OPEN_TAKEOFF_MCP_LICENSE = "Apache-2.0"
OPEN_TAKEOFF_MCP_REPOSITORY = "git+https://github.com/Kentucky-ai/opentakeoff.git"

DEFAULT_RUNTIME_COMMAND = (
    "node",
    "node_modules/opentakeoff-mcp/dist/server.js",
)


class OpenTakeoffRuntimeError(RuntimeError):
    def __init__(self, category: OpenTakeoffWorkerErrorCode, message: str) -> None:
        super().__init__(message)
        self.category = category


@dataclass(frozen=True)
class OpenTakeoffRuntimeConfig:
    command: tuple[str, ...] = DEFAULT_RUNTIME_COMMAND
    cwd: Path = Path(__file__).resolve().parents[3]
    startup_timeout_seconds: float = 10.0
    tool_timeout_seconds: float = 20.0
    shutdown_grace_seconds: float = 2.0
    max_stdout_line_bytes: int = 5_000_000
    max_tool_content_bytes: int = 5_000_000
    max_stderr_bytes: int = 20_000
    max_pdf_bytes: int = 75 * 1024 * 1024
    max_pages: int = 250
    temp_root: Path | None = None


@dataclass
class OpenTakeoffRuntimeDiagnostics:
    engine_version: str = OPEN_TAKEOFF_MCP_VERSION
    package: str = OPEN_TAKEOFF_MCP_PACKAGE
    command: tuple[str, ...] = DEFAULT_RUNTIME_COMMAND
    started_at: float | None = None
    completed_at: float | None = None
    operation_timings_ms: dict[str, int] = field(default_factory=dict)
    stderr_tail: str = ""
    cleaned_temp_dir: bool = False
    cancelled: bool = False
    forced_termination: bool = False


def _redact_diagnostic(text: str) -> str:
    text = re.sub(r"/[A-Za-z0-9._~+/@:-]+", "[redacted-path]", text)
    text = re.sub(r"[A-Za-z0-9._ -]+\.pdf\b", "[redacted-pdf]", text, flags=re.IGNORECASE)
    text = re.sub(r"(token|secret|password|key)=\S+", r"\1=[redacted]", text, flags=re.IGNORECASE)
    return text


class OpenTakeoffMCPClient:
    """Small MCP stdio client for the pinned OpenTakeoff runtime."""

    def __init__(self, config: OpenTakeoffRuntimeConfig | None = None) -> None:
        self.config = config or OpenTakeoffRuntimeConfig()
        self._process: subprocess.Popen[str] | None = None
        self._stdout_queue: queue.Queue[dict[str, Any]] = queue.Queue()
        self._stderr_chunks: list[str] = []
        self._reader_threads: list[threading.Thread] = []
        self._next_id = 1
        self._closed = False
        self._temp_dir: Path | None = None
        self.diagnostics = OpenTakeoffRuntimeDiagnostics(command=self.config.command)

    @property
    def engine_version(self) -> str:
        return f"{OPEN_TAKEOFF_MCP_PACKAGE}@{OPEN_TAKEOFF_MCP_VERSION}"

    @property
    def stderr_tail(self) -> str:
        text = "".join(self._stderr_chunks)
        return text[-self.config.max_stderr_bytes :]

    def start(self) -> None:
        if self._process is not None:
            return
        executable = shutil.which(self.config.command[0])
        if executable is None:
            raise OpenTakeoffRuntimeError(
                OpenTakeoffWorkerErrorCode.PROVIDER_START_FAILED,
                f"OpenTakeoff executable not found: {self.config.command[0]}",
            )
        self._temp_dir = Path(tempfile.mkdtemp(prefix="mobi-opentakeoff-", dir=self.config.temp_root))
        env = os.environ.copy()
        env.setdefault("NODE_ENV", "production")
        try:
            self._process = subprocess.Popen(
                [executable, *self.config.command[1:]],
                cwd=self.config.cwd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                env=env,
                start_new_session=True,
            )
        except OSError as exc:
            self._cleanup_temp_dir()
            raise OpenTakeoffRuntimeError(OpenTakeoffWorkerErrorCode.PROVIDER_START_FAILED, str(exc)) from exc
        self.diagnostics.started_at = time.monotonic()
        self._reader_threads = [
            threading.Thread(target=self._read_stdout, daemon=True),
            threading.Thread(target=self._read_stderr, daemon=True),
        ]
        for thread in self._reader_threads:
            thread.start()
        init = self._request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "mobi-opentakeoff-worker", "version": "1"},
            },
            timeout=self.config.startup_timeout_seconds,
        )
        server_info = init.get("result", {}).get("serverInfo", {})
        server_version = server_info.get("version")
        if server_version:
            self.diagnostics.engine_version = str(server_version)

    def _read_stdout(self) -> None:
        assert self._process and self._process.stdout
        while True:
            line = self._process.stdout.readline(self.config.max_stdout_line_bytes + 1)
            if line == "":
                break
            if len(line.encode("utf-8")) > self.config.max_stdout_line_bytes:
                self._stdout_queue.put({"error": {"message": "stdout line exceeded limit"}})
                self._drain_oversized_stdout_line()
                continue
            try:
                self._stdout_queue.put(json.loads(line))
            except json.JSONDecodeError as exc:
                self._stdout_queue.put({"error": {"message": f"invalid MCP JSON: {exc}"}})

    def _drain_oversized_stdout_line(self) -> None:
        assert self._process and self._process.stdout
        while True:
            chunk = self._process.stdout.readline(1024)
            if chunk == "" or chunk.endswith("\n"):
                return

    def _read_stderr(self) -> None:
        assert self._process and self._process.stderr
        for chunk in self._process.stderr:
            self._stderr_chunks.append(_redact_diagnostic(chunk))
            joined = "".join(self._stderr_chunks)
            if len(joined) > self.config.max_stderr_bytes:
                self._stderr_chunks = [joined[-self.config.max_stderr_bytes :]]

    def _raise_protocol_error(self, message: dict[str, Any]) -> None:
        self.close(force=True)
        raise OpenTakeoffRuntimeError(
            OpenTakeoffWorkerErrorCode.PROVIDER_PROTOCOL_ERROR,
            str(message.get("error") or "Unexpected MCP protocol message"),
        )

    def _request(self, method: str, params: dict[str, Any] | None = None, *, timeout: float | None = None) -> dict[str, Any]:
        self.start() if self._process is None and method != "initialize" else None
        if self._process is None or self._process.stdin is None:
            raise OpenTakeoffRuntimeError(OpenTakeoffWorkerErrorCode.PROVIDER_CRASH, "OpenTakeoff process is not running")
        if self._process.poll() is not None:
            raise OpenTakeoffRuntimeError(OpenTakeoffWorkerErrorCode.PROVIDER_CRASH, "OpenTakeoff process exited")
        request_id = self._next_id
        self._next_id += 1
        payload = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}}
        try:
            self._process.stdin.write(json.dumps(payload) + "\n")
            self._process.stdin.flush()
        except BrokenPipeError as exc:
            self.close(force=True)
            raise OpenTakeoffRuntimeError(OpenTakeoffWorkerErrorCode.PROVIDER_CRASH, "OpenTakeoff stdin closed") from exc
        deadline = time.monotonic() + (timeout or self.config.tool_timeout_seconds)
        while time.monotonic() < deadline:
            if self._process.poll() is not None:
                self.close(force=True)
                raise OpenTakeoffRuntimeError(OpenTakeoffWorkerErrorCode.PROVIDER_CRASH, "OpenTakeoff process exited")
            try:
                message = self._stdout_queue.get(timeout=max(0.01, min(0.1, deadline - time.monotonic())))
            except queue.Empty:
                continue
            if "error" in message and message.get("id") not in (request_id, None):
                self._raise_protocol_error(message)
            if "error" in message and message.get("id") is None:
                self._raise_protocol_error(message)
            if message.get("id") != request_id:
                self._raise_protocol_error(message)
            if "error" in message:
                self._raise_protocol_error(message)
            return message
        self.close(force=True)
        raise OpenTakeoffRuntimeError(OpenTakeoffWorkerErrorCode.PROVIDER_TIMEOUT, f"MCP request timed out: {method}")

    def _call_tool(self, name: str, arguments: dict[str, Any] | None = None, *, timeout: float | None = None) -> dict[str, Any]:
        started = time.monotonic()
        response = self._request("tools/call", {"name": name, "arguments": arguments or {}}, timeout=timeout)
        self.diagnostics.operation_timings_ms[name] = int((time.monotonic() - started) * 1000)
        result = response.get("result", {})
        if result.get("isError"):
            text = self._content_text(result)
            category = OpenTakeoffWorkerErrorCode.PROVIDER_PROTOCOL_ERROR
            if "Set the scale" in text:
                category = OpenTakeoffWorkerErrorCode.SCALE_MISSING
            raise OpenTakeoffRuntimeError(category, text)
        return self._content_json(result)

    def _content_text(self, result: dict[str, Any]) -> str:
        pieces = []
        total = 0
        for item in result.get("content", []):
            if item.get("type") != "text":
                continue
            text = str(item.get("text", ""))
            total += len(text.encode("utf-8"))
            if total > self.config.max_tool_content_bytes:
                self.close(force=True)
                raise OpenTakeoffRuntimeError(
                    OpenTakeoffWorkerErrorCode.PROVIDER_PROTOCOL_ERROR,
                    "MCP tool content exceeded output limit",
                )
            pieces.append(text)
        return "\n".join(pieces)

    def _content_json(self, result: dict[str, Any]) -> dict[str, Any]:
        text = self._content_text(result)
        if not text:
            return {}
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            raise OpenTakeoffRuntimeError(OpenTakeoffWorkerErrorCode.PROVIDER_PROTOCOL_ERROR, "MCP tool returned non-JSON text")

    def _pdf_page_count_before_provider(self, path: Path) -> int:
        pdfinfo = shutil.which("pdfinfo")
        if pdfinfo is None:
            raise OpenTakeoffRuntimeError(OpenTakeoffWorkerErrorCode.UNSUPPORTED_DOCUMENT, "pdfinfo is required for preflight page count")
        try:
            completed = subprocess.run(
                [pdfinfo, str(path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=5,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise OpenTakeoffRuntimeError(OpenTakeoffWorkerErrorCode.PROVIDER_TIMEOUT, "PDF preflight page-count timed out") from exc
        if completed.returncode != 0:
            raise OpenTakeoffRuntimeError(OpenTakeoffWorkerErrorCode.UNSUPPORTED_DOCUMENT, "PDF preflight failed")
        for line in completed.stdout.splitlines():
            if line.startswith("Pages:"):
                return int(line.split(":", 1)[1].strip())
        raise OpenTakeoffRuntimeError(OpenTakeoffWorkerErrorCode.UNSUPPORTED_DOCUMENT, "PDF page count missing")

    def _validate_pdf(self, path: Path) -> None:
        if not path.is_file():
            raise OpenTakeoffRuntimeError(OpenTakeoffWorkerErrorCode.DOCUMENT_NOT_FOUND, "Document not found")
        if path.suffix.lower() != ".pdf":
            raise OpenTakeoffRuntimeError(OpenTakeoffWorkerErrorCode.UNSUPPORTED_DOCUMENT, "Only PDF documents are supported")
        if path.stat().st_size > self.config.max_pdf_bytes:
            raise OpenTakeoffRuntimeError(OpenTakeoffWorkerErrorCode.RESOURCE_LIMIT, "PDF exceeds worker size limit")
        if self._pdf_page_count_before_provider(path) > self.config.max_pages:
            raise OpenTakeoffRuntimeError(OpenTakeoffWorkerErrorCode.RESOURCE_LIMIT, "PDF exceeds worker page limit")

    def load_plan(self, path: Path) -> dict[str, Any]:
        self._validate_pdf(path)
        return self._call_tool("load_plan", {"path": str(path)})

    def sheet_info(self, sheet: str) -> dict[str, Any]:
        return self._call_tool("sheet_info", {"sheet": sheet})

    def read_sheet_text(self, sheet: str, region: dict[str, float] | None = None) -> dict[str, Any]:
        args: dict[str, Any] = {"sheet": sheet}
        if region:
            args["region"] = region
        return self._call_tool("read_sheet_text", args)

    def set_scale(self, sheet: str, scale: OpenTakeoffScaleConfirmation) -> dict[str, Any]:
        args: dict[str, Any] = {"sheet": sheet}
        if scale.units_per_px:
            args["upp"] = scale.units_per_px
        elif scale.scale_label:
            args["label"] = scale.scale_label
        else:
            raise OpenTakeoffRuntimeError(OpenTakeoffWorkerErrorCode.SCALE_UNCONFIRMED, "Scale confirmation is missing")
        return self._call_tool("set_scale", args)

    def measure_line(self, sheet: str, pts: list[tuple[float, float]], condition: str) -> dict[str, Any]:
        return self._call_tool("measure_line", {"sheet": sheet, "pts": pts, "condition": condition})

    def measure_polygon(self, sheet: str, verts: list[tuple[float, float]], condition: str) -> dict[str, Any]:
        return self._call_tool("measure_polygon", {"sheet": sheet, "verts": verts, "condition": condition, "role": "floor_area"})

    def takeoff_summary(self) -> dict[str, Any]:
        return self._call_tool("takeoff_summary", {})

    def export_takeoff(self) -> dict[str, Any]:
        return self._call_tool("export_takeoff", {})

    def cancel(self) -> None:
        self.diagnostics.cancelled = True
        self.close(force=True)

    def close(self, *, force: bool = False) -> None:
        if self._closed:
            return
        self._closed = True
        proc = self._process
        if proc and proc.poll() is None:
            try:
                if proc.stdin:
                    proc.stdin.close()
            except OSError:
                pass
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                proc.wait(timeout=self.config.shutdown_grace_seconds)
            except subprocess.TimeoutExpired:
                if force:
                    self.diagnostics.forced_termination = True
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                proc.wait(timeout=5)
        self.diagnostics.completed_at = time.monotonic()
        self.diagnostics.stderr_tail = self.stderr_tail
        self._cleanup_temp_dir()

    def _cleanup_temp_dir(self) -> None:
        if self._temp_dir and self._temp_dir.exists():
            shutil.rmtree(self._temp_dir, ignore_errors=True)
            self.diagnostics.cleaned_temp_dir = not self._temp_dir.exists()
        elif self._temp_dir:
            self.diagnostics.cleaned_temp_dir = True
