"""Explicit, checksum-verified data transfer boundaries."""

from synthaudit.data.transfer import (
    DataArtifactSpecV1,
    DataDownloadManifestV1,
    DataDownloadResultV1,
    download_from_manifest,
)

__all__ = [
    "DataArtifactSpecV1",
    "DataDownloadManifestV1",
    "DataDownloadResultV1",
    "download_from_manifest",
]
