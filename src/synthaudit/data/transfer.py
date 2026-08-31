"""User-authorized data acquisition with no import-time or implicit network access."""

from __future__ import annotations

import hashlib
import urllib.parse
import urllib.request
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import Field, model_validator

from synthaudit import __version__
from synthaudit.application.workflows import read_json
from synthaudit.schema.common import ProvenanceRecord, StrictModel


class DataArtifactSpecV1(StrictModel):
    artifact_id: str = Field(min_length=1)
    source_uri: str = Field(min_length=1)
    destination: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    media_type: str = "application/octet-stream"
    license_status: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_destination(self) -> DataArtifactSpecV1:
        candidate = PurePosixPath(self.destination)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise ValueError("artifact destination must be a safe relative path")
        return self


class DataDownloadManifestV1(StrictModel):
    schema_version: Literal["synthaudit.data-download-manifest/1"] = (
        "synthaudit.data-download-manifest/1"
    )
    dataset_id: str = Field(min_length=1)
    dataset_version: str = Field(min_length=1)
    artifacts: tuple[DataArtifactSpecV1, ...] = Field(min_length=1)
    provenance: tuple[ProvenanceRecord, ...] = Field(min_length=1)


class DownloadedArtifactV1(StrictModel):
    artifact_id: str
    destination: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    byte_length: int = Field(ge=0)
    source_uri: str
    license_status: str


class DataDownloadResultV1(StrictModel):
    schema_version: Literal["synthaudit.data-download-result/1"] = (
        "synthaudit.data-download-result/1"
    )
    dataset_id: str
    dataset_version: str
    network_access_used: bool
    artifacts: tuple[DownloadedArtifactV1, ...]
    notice: Literal[
        "Data acquisition requires an explicit manifest, license status and checksum; downloaded reactions are not experimental validation."
    ] = (
        "Data acquisition requires an explicit manifest, license status and checksum; "
        "downloaded reactions are not experimental validation."
    )
    provenance: tuple[ProvenanceRecord, ...] = Field(min_length=1)


def _read_source(uri: str, *, manifest_dir: Path, allow_network: bool) -> tuple[bytes, bool]:
    parsed = urllib.parse.urlparse(uri)
    if parsed.scheme in {"http", "https"}:
        if not allow_network:
            raise PermissionError(
                "remote data access is disabled; rerun with --allow-network after reviewing the manifest"
            )
        with urllib.request.urlopen(uri, timeout=60) as response:
            return response.read(), True
    if parsed.scheme == "file":
        source = Path(urllib.request.url2pathname(parsed.path))
    elif not parsed.scheme:
        source = Path(uri)
        if not source.is_absolute():
            source = manifest_dir / source
    else:
        raise ValueError(f"unsupported data source URI scheme: {parsed.scheme!r}")
    return source.read_bytes(), False


def download_from_manifest(
    manifest_path: str | Path,
    output_dir: str | Path,
    *,
    allow_network: bool = False,
    overwrite: bool = False,
) -> DataDownloadResultV1:
    """Copy or explicitly download each artifact and verify it before committing bytes."""
    manifest_file = Path(manifest_path)
    manifest = DataDownloadManifestV1.model_validate(read_json(manifest_file))
    output_root = Path(output_dir)
    downloaded: list[DownloadedArtifactV1] = []
    used_network = False
    for artifact in manifest.artifacts:
        target = output_root / artifact.destination
        if target.exists() and not overwrite:
            raise FileExistsError(f"refusing to overwrite existing artifact: {target}")
        content, remote = _read_source(
            artifact.source_uri,
            manifest_dir=manifest_file.parent,
            allow_network=allow_network,
        )
        used_network = used_network or remote
        digest = hashlib.sha256(content).hexdigest()
        if digest != artifact.sha256:
            raise ValueError(
                f"checksum mismatch for {artifact.artifact_id}: expected {artifact.sha256}, got {digest}"
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        downloaded.append(
            DownloadedArtifactV1(
                artifact_id=artifact.artifact_id,
                destination=str(target),
                sha256=digest,
                byte_length=len(content),
                source_uri=artifact.source_uri,
                license_status=artifact.license_status,
            )
        )
    return DataDownloadResultV1(
        dataset_id=manifest.dataset_id,
        dataset_version=manifest.dataset_version,
        network_access_used=used_network,
        artifacts=tuple(downloaded),
        provenance=(
            *manifest.provenance,
            ProvenanceRecord(
                source="synthaudit",
                source_version=__version__,
                adapter="download_from_manifest",
                adapter_version="1",
                license="Apache-2.0",
            ),
        ),
    )
