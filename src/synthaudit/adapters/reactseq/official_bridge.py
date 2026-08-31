"""Subprocess boundary for the pinned official legacy ReactSeq converter."""

from __future__ import annotations

import json
import subprocess
import uuid
from collections.abc import Sequence
from typing import Literal

from pydantic import ValidationError

from synthaudit.adapters.reactseq.adapter import REACTSEQ_UPSTREAM_COMMIT
from synthaudit.adapters.reactseq.errors import ReactSeqOfficialBridgeError
from synthaudit.adapters.reactseq.models import (
    ReactSeqBridgeRequest,
    ReactSeqBridgeResponse,
)


class ReactSeqOfficialBridge:
    """Call an explicitly configured JSONL worker; never auto-download or shell out."""

    def __init__(
        self,
        command: Sequence[str],
        *,
        expected_upstream_commit: str = REACTSEQ_UPSTREAM_COMMIT,
        timeout_seconds: float = 120.0,
    ) -> None:
        if not command:
            raise ValueError("official ReactSeq bridge command cannot be empty")
        self.command = tuple(command)
        self.expected_upstream_commit = expected_upstream_commit
        self.timeout_seconds = timeout_seconds

    def inspect_runtime(self) -> ReactSeqBridgeResponse:
        return self._request("inspect_runtime", {})

    def convert_reaction(self, mapped_reaction_smiles: str) -> ReactSeqBridgeResponse:
        return self._request("convert_reaction", {"mapped_reaction_smiles": mapped_reaction_smiles})

    def reconstruct_precursors(self, reactseq: str) -> ReactSeqBridgeResponse:
        return self._request("reconstruct_precursors", {"reactseq": reactseq})

    def _request(
        self,
        operation: Literal["convert_reaction", "reconstruct_precursors", "inspect_runtime"],
        payload: dict[str, str],
    ) -> ReactSeqBridgeResponse:
        request = ReactSeqBridgeRequest(
            request_id=str(uuid.uuid4()),
            operation=operation,
            upstream_commit=self.expected_upstream_commit,
            payload=payload,
        )
        try:
            completed = subprocess.run(
                self.command,
                input=request.model_dump_json() + "\n",
                text=True,
                capture_output=True,
                timeout=self.timeout_seconds,
                check=False,
                shell=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ReactSeqOfficialBridgeError(
                f"official ReactSeq bridge could not run: {exc}",
                details={"command": list(self.command)},
            ) from exc
        if completed.returncode != 0:
            raise ReactSeqOfficialBridgeError(
                "official ReactSeq bridge exited unsuccessfully",
                details={
                    "returncode": completed.returncode,
                    "stderr": completed.stderr[-4000:],
                },
            )
        lines = tuple(line for line in completed.stdout.splitlines() if line.strip())
        if len(lines) != 1:
            raise ReactSeqOfficialBridgeError(
                "official ReactSeq bridge must emit exactly one JSONL response",
                details={"response_lines": len(lines)},
            )
        try:
            response = ReactSeqBridgeResponse.model_validate_json(lines[0])
        except (ValidationError, json.JSONDecodeError) as exc:
            raise ReactSeqOfficialBridgeError(
                f"official ReactSeq bridge returned an invalid response: {exc}"
            ) from exc
        if response.request_id != request.request_id:
            raise ReactSeqOfficialBridgeError("official ReactSeq bridge request ID mismatch")
        if response.upstream_commit != self.expected_upstream_commit:
            raise ReactSeqOfficialBridgeError(
                "official ReactSeq bridge upstream commit mismatch",
                details={
                    "expected": self.expected_upstream_commit,
                    "received": response.upstream_commit,
                },
            )
        if not response.success:
            raise ReactSeqOfficialBridgeError(
                "official ReactSeq operation failed",
                details=response.error or {},
            )
        return response
