#!/usr/bin/env python3
"""Mobi LinkedIn Scout — on-demand Hermes job runner.

This script is the ONLY thing that talks to the Scout job endpoints. It has two
sub-commands and no LLM logic of its own — the decisions live in the Hermes
prompt (see ../ops/scout-hermes-job.md), which writes an outcomes file that this
script uploads.

  fetch   GET a batch of unprocessed candidates and write them to a JSON file.
  submit  Read an outcomes JSON file and POST it to the job endpoint.

Secrets:
  MOBI_SCOUT_BASE_URL   e.g. https://mobi-linkedin-ops.vercel.app
  MOBI_SCOUT_JOB_TOKEN  the SCOUT_JOB_TOKEN configured on the server.

They are read from the environment, or from a mode-0600 env file given by
--env-file / MOBI_SCOUT_ENV_FILE (KEY=VALUE lines). The token is never printed,
never placed in a URL, and only ever sent in the Authorization header. Only the
Python standard library is used, so there is nothing to install.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from typing import NoReturn

TIMEOUT_SECONDS = 20
APPROVED_BASE_URL = "https://mobi-linkedin-ops.vercel.app"
REQUIRED_PROVIDER = "openai-codex"
REQUIRED_MODEL = "gpt-5.6-sol"
FETCH_PATH = "/api/scout/job"
SUBMIT_PATH = "/api/scout/job"


def _fail(message: str) -> NoReturn:
    # Errors go to stderr and never include the token or a response body secret.
    print("scout_job: " + message, file=sys.stderr)
    sys.exit(1)


def _parse_env_file(path):
    """Parse a KEY=VALUE env file, refusing anything more permissive than 0600."""
    try:
        mode = os.stat(path).st_mode & 0o777
    except OSError as exc:
        _fail("cannot read env file: {}".format(exc.strerror or "error"))
    if mode & 0o077:
        _fail(
            "env file {} must be mode 0600 (owner-only); it is {:o}".format(path, mode)
        )
    values = {}
    with open(path, "r", encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            values[key.strip()] = val.strip().strip('"').strip("'")
    return values


def _load_config(env_file):
    env_file = env_file or os.environ.get("MOBI_SCOUT_ENV_FILE")
    file_values = _parse_env_file(env_file) if env_file else {}

    base_url = os.environ.get("MOBI_SCOUT_BASE_URL") or file_values.get(
        "MOBI_SCOUT_BASE_URL"
    )
    token = os.environ.get("MOBI_SCOUT_JOB_TOKEN") or file_values.get(
        "MOBI_SCOUT_JOB_TOKEN"
    )
    if not base_url:
        _fail("MOBI_SCOUT_BASE_URL is not set.")
    if not token:
        _fail("MOBI_SCOUT_JOB_TOKEN is not set.")
    normalized_base = base_url.strip().rstrip("/")
    if normalized_base != APPROVED_BASE_URL:
        _fail("MOBI_SCOUT_BASE_URL must be the approved production Scout URL.")
    return APPROVED_BASE_URL, token


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse redirects so urllib can never forward the bearer token elsewhere."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _request(method, url, token, payload=None):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", "Bearer " + token)  # header only, never a URL
    req.add_header("Accept", "application/json")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        opener = urllib.request.build_opener(_NoRedirect)
        with opener.open(req, timeout=TIMEOUT_SECONDS) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        # Surface only the status; do not echo the response body (defence in depth).
        _fail("server returned HTTP {} for {}".format(exc.code, method))
    except urllib.error.URLError as exc:
        _fail("network error: {}".format(getattr(exc, "reason", "unreachable")))
    except (ValueError, TimeoutError) as exc:
        _fail("bad or slow response: {}".format(exc))


def cmd_fetch(args):
    base_url, token = _load_config(args.env_file)
    status, data = _request("GET", base_url + FETCH_PATH, token)
    if status != 200:
        _fail("unexpected status {} from fetch".format(status))
    candidates = data.get("candidates", [])
    out = {
        "batchId": data.get("batchId"),
        "cap": data.get("cap"),
        "commentMaxLength": data.get("commentMaxLength"),
        "skipReasons": data.get("skipReasons"),
        "candidates": candidates,
    }
    _write_json(args.out, out)
    print("fetched {} candidate(s) → {}".format(len(candidates), args.out))


def cmd_submit(args):
    payload = _read_json(args.infile)
    if not isinstance(payload, dict) or "batchId" not in payload or "outcomes" not in payload:
        _fail("outcomes file must be an object with 'batchId' and 'outcomes'.")
    if payload.get("provider") != REQUIRED_PROVIDER:
        _fail("outcomes provider must be exactly openai-codex.")
    if payload.get("model") != REQUIRED_MODEL:
        _fail("outcomes model must be exactly gpt-5.6-sol.")
    if not isinstance(payload["outcomes"], list):
        _fail("'outcomes' must be a list.")
    if len(payload["outcomes"]) > 20:
        _fail("refusing to submit more than 20 outcomes.")
    base_url, token = _load_config(args.env_file)
    status, data = _request("POST", base_url + SUBMIT_PATH, token, payload)
    if status != 200:
        _fail("unexpected status {} from submit".format(status))
    result = {
        "queued": data.get("queued", 0),
        "skipped": data.get("skipped", 0),
        "results": data.get("results", []),
    }
    if args.out:
        _write_json(args.out, result)
    print("submitted: {} queued, {} skipped".format(result["queued"], result["skipped"]))


def _read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError) as exc:
        _fail("cannot read {}: {}".format(path, exc))


def _write_json(path, obj):
    try:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(obj, handle, indent=2)
            handle.write("\n")
    except OSError as exc:
        _fail("cannot write {}: {}".format(path, exc))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Mobi LinkedIn Scout job runner")
    parser.add_argument(
        "--env-file",
        help="Path to a mode-0600 KEY=VALUE env file (or set MOBI_SCOUT_ENV_FILE).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    fetch = sub.add_parser("fetch", help="Fetch a batch of candidates to a file.")
    fetch.add_argument("--out", required=True, help="Where to write candidates JSON.")
    fetch.set_defaults(func=cmd_fetch)

    submit = sub.add_parser("submit", help="Submit an outcomes file.")
    submit.add_argument("--in", dest="infile", required=True, help="Outcomes JSON file.")
    submit.add_argument("--out", help="Optional: write the server result here.")
    submit.set_defaults(func=cmd_submit)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
