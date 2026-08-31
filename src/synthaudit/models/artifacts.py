"""Explicit persistence boundary for locally trained evidence models."""

from __future__ import annotations

import hashlib
import json
import pickle
import platform
from pathlib import Path
from typing import Literal

from pydantic import Field

from synthaudit import __version__
from synthaudit.models.evidence import EvidenceModelManifestV1
from synthaudit.models.training import TrainedEvidenceModel
from synthaudit.schema.common import ProvenanceRecord, StrictModel


class EvidenceModelArtifactV1(StrictModel):
    schema_version: Literal["synthaudit.evidence-model-artifact/1"] = (
        "synthaudit.evidence-model-artifact/1"
    )
    artifact_file: str = Field(min_length=1)
    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    serialization: Literal["pickle_explicit_trusted_local_artifact"] = (
        "pickle_explicit_trusted_local_artifact"
    )
    python_version: str
    model_manifest: EvidenceModelManifestV1
    security_notice: Literal[
        "Only load this pickle artifact when its source is trusted and its SHA-256 matches."
    ] = "Only load this pickle artifact when its source is trusted and its SHA-256 matches."
    provenance: tuple[ProvenanceRecord, ...] = Field(min_length=1)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def save_evidence_model(
    model: TrainedEvidenceModel,
    artifact_path: str | Path,
    *,
    manifest_path: str | Path | None = None,
) -> EvidenceModelArtifactV1:
    target = Path(artifact_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("wb") as stream:
        pickle.dump(model, stream, protocol=pickle.HIGHEST_PROTOCOL)
    digest = _sha256(target)
    descriptor = EvidenceModelArtifactV1(
        artifact_file=target.name,
        artifact_sha256=digest,
        python_version=platform.python_version(),
        model_manifest=model.manifest,
        provenance=(
            ProvenanceRecord(
                source="synthaudit",
                source_version=__version__,
                adapter="save_evidence_model",
                adapter_version="1",
                artifact_sha256=digest,
                license="Apache-2.0",
            ),
        ),
    )
    descriptor_path = (
        Path(manifest_path) if manifest_path is not None else target.with_suffix(".manifest.json")
    )
    descriptor_path.write_text(
        json.dumps(descriptor.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return descriptor


def load_evidence_model(
    artifact_path: str | Path,
    manifest_path: str | Path,
    *,
    trust_artifact: bool,
) -> tuple[TrainedEvidenceModel, EvidenceModelArtifactV1]:
    if not trust_artifact:
        raise PermissionError(
            "pickle loading can execute code; pass explicit trust only for a reviewed local artifact"
        )
    artifact = Path(artifact_path)
    descriptor = EvidenceModelArtifactV1.model_validate_json(
        Path(manifest_path).read_text(encoding="utf-8")
    )
    actual = _sha256(artifact)
    if actual != descriptor.artifact_sha256:
        raise ValueError("evidence model artifact SHA-256 does not match its manifest")
    with artifact.open("rb") as stream:
        loaded = pickle.load(stream)
    if not isinstance(loaded, TrainedEvidenceModel):
        raise TypeError("artifact does not contain a TrainedEvidenceModel")
    model = loaded
    if model.manifest != descriptor.model_manifest:
        raise ValueError("serialized model manifest does not match its descriptor")
    return model, descriptor
