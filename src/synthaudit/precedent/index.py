"""Deterministic, versioned local reference-reaction index."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from pathlib import Path

from synthaudit import __version__
from synthaudit.novelty.fingerprints import MORGAN_BITS, MORGAN_RADIUS, rdkit_version
from synthaudit.novelty.models import FingerprintSpecificationV1
from synthaudit.precedent.models import (
    ReferenceIndexArtifactV1,
    ReferenceIndexManifestV1,
    ReferenceReactionV1,
)
from synthaudit.schema.common import ProvenanceRecord


def _records_payload(records: Sequence[ReferenceReactionV1]) -> str:
    values = [item.model_dump(mode="json") for item in records]
    return json.dumps(values, sort_keys=True, separators=(",", ":"))


class ReferenceIndex:
    """Small/local reference corpus; no network or implicit dataset download."""

    def __init__(self, artifact: ReferenceIndexArtifactV1) -> None:
        expected = hashlib.sha256(_records_payload(artifact.records).encode()).hexdigest()
        if artifact.manifest.records_sha256 != expected:
            raise ValueError("reference-index records SHA-256 mismatch")
        self.artifact = artifact

    @property
    def records(self) -> tuple[ReferenceReactionV1, ...]:
        return self.artifact.records

    @property
    def manifest(self) -> ReferenceIndexManifestV1:
        return self.artifact.manifest

    @classmethod
    def build(
        cls,
        records: Sequence[ReferenceReactionV1],
        *,
        corpus_id: str,
        corpus_version: str,
    ) -> ReferenceIndex:
        ordered = tuple(
            sorted(records, key=lambda item: (item.source_dataset, item.source_reaction_id))
        )
        digest = hashlib.sha256(_records_payload(ordered).encode()).hexdigest()
        specification = FingerprintSpecificationV1(
            algorithm="Morgan and SynthAudit stage-specific hashed fingerprints",
            radius=MORGAN_RADIUS,
            bit_length=MORGAN_BITS,
            use_chirality=True,
            implementation="RDKit/SynthAudit",
            implementation_version=f"rdkit-{rdkit_version()};synthaudit-{__version__}",
            parameters={
                "reaction_difference_bits": MORGAN_BITS * 2,
                "semantic_bits": MORGAN_BITS,
                "primary_novelty": "one_minus_maximum_reference_tanimoto",
            },
        )
        manifest = ReferenceIndexManifestV1(
            corpus_id=corpus_id,
            corpus_version=corpus_version,
            record_count=len(ordered),
            records_sha256=digest,
            fingerprint_specification=specification,
            source_licenses=tuple(sorted({item.data_license_status for item in ordered})),
            provenance=(
                ProvenanceRecord(
                    source="synthaudit",
                    source_version=__version__,
                    adapter="ReferenceIndex.build",
                    adapter_version="1",
                    artifact_sha256=digest,
                    license="Apache-2.0",
                ),
            ),
        )
        return cls(ReferenceIndexArtifactV1(manifest=manifest, records=ordered))

    @classmethod
    def load(cls, path: str | Path) -> ReferenceIndex:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(ReferenceIndexArtifactV1.model_validate(payload))

    def save(self, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(self.artifact.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return target

    def class_frequency(self, reaction_class: str) -> int:
        return sum(item.reaction_class == reaction_class for item in self.records)
