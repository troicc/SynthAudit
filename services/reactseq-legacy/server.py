"""Minimal Python-3.7-compatible JSONL wrapper around an operator checkout."""

import importlib
import json
import os
import platform
import subprocess
import sys

EXPECTED = "9838a3058e32e1c0ee04b2bab0448104dc293384"


def respond(request, success, result=None, error=None):
    return {
        "protocol_version": "synthaudit.reactseq-bridge/1",
        "request_id": request.get("request_id", "missing"),
        "success": success,
        "upstream_commit": os.environ.get("REACTSEQ_UPSTREAM_COMMIT", "0" * 40),
        "result": result or {},
        "error": error,
        "runtime": {"python": platform.python_version()},
    }


def handle(request):
    configured = os.environ.get("REACTSEQ_UPSTREAM_COMMIT", "")
    if configured != EXPECTED or request.get("upstream_commit") != EXPECTED:
        return respond(request, False, error={"type": "UpstreamCommitMismatch"})
    source = os.environ.get("REACTSEQ_SOURCE")
    if not source:
        return respond(request, False, error={"type": "MissingReactSeqSource"})
    actual_commit = subprocess.check_output(
        ["git", "-C", source, "rev-parse", "HEAD"], universal_newlines=True
    ).strip()
    if actual_commit != EXPECTED:
        return respond(
            request,
            False,
            error={"type": "CheckoutCommitMismatch", "actual_commit": actual_commit},
        )
    if request.get("operation") == "inspect_runtime":
        return respond(request, True, result={"available": True, "source": source})
    sys.path.insert(0, source)
    module = importlib.import_module("e_smiles")
    payload = request.get("payload", {})
    if request.get("operation") == "convert_reaction":
        value = module.get_e_smiles(payload["mapped_reaction_smiles"])
        return respond(request, True, result={"reactseq": value})
    if request.get("operation") == "reconstruct_precursors":
        value = module.merge_smiles_only(payload["reactseq"])
        return respond(request, True, result={"precursor_smiles": value})
    return respond(request, False, error={"type": "UnsupportedOperation"})


for line in sys.stdin:
    try:
        request_object = json.loads(line)
        response_object = handle(request_object)
    except Exception as exc:  # boundary must serialize upstream failures
        response_object = respond(
            locals().get("request_object", {}),
            False,
            error={"type": type(exc).__name__, "message": str(exc)},
        )
    sys.stdout.write(json.dumps(response_object, sort_keys=True) + "\n")
    sys.stdout.flush()
