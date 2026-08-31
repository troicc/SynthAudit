"""Explicit local route envelope for the SynthEx paper-draft namespace."""

from __future__ import annotations

import hashlib
import json

from synthaudit import __version__
from synthaudit.adapters.models import AdapterWarningV1, RouteAdapterResultV1
from synthaudit.adapters.synthex.models import SynthExPaperDraftInput, SynthExPaperDraftRouteInput
from synthaudit.adapters.synthex.paper_draft import (
    SYNTHEX_REPOSITORY,
    SYNTHEX_UPSTREAM_COMMIT,
    SynthExPaperDraftAdapter,
    _object,
    _sequence,
)
from synthaudit.schema.common import MoleculeRecord, MoleculeRole, ProvenanceRecord
from synthaudit.schema.route_ir import RouteIRV1, RouteStepIRV1

SYNTHEX_DRAFT_ROUTE_ID = "synthaudit.synthex-paper-draft-route/0.1"


def _molecule_records(values: object, role: MoleculeRole) -> tuple[MoleculeRecord, ...]:
    result: list[MoleculeRecord] = []
    for value in _sequence(values, label=f"{role.value} molecules"):
        if not isinstance(value, str):
            raise ValueError(f"{role.value} molecule entries must be mapped SMILES strings")
        result.append(MoleculeRecord(mapped_smiles=value, role=role))
    return tuple(result)


class SynthExPaperDraftRouteAdapter:
    """Normalize only SynthAudit's declared draft route envelope."""

    adapter_id = SYNTHEX_DRAFT_ROUTE_ID

    def normalize(self, source: SynthExPaperDraftRouteInput) -> RouteAdapterResultV1:
        envelope = _object(source.payload, label="SynthEx paper-draft route")
        declared = envelope.get("schema_version", envelope.get("schema"))
        if declared != SYNTHEX_DRAFT_ROUTE_ID:
            raise ValueError(f"draft route schema must explicitly equal {SYNTHEX_DRAFT_ROUTE_ID!r}")
        target_smiles = envelope.get("target")
        if not isinstance(target_smiles, str):
            raise ValueError("draft route target must be mapped SMILES")
        raw_steps = _sequence(envelope.get("steps"), label="route steps")
        steps: list[RouteStepIRV1] = []
        warnings: list[AdapterWarningV1] = [
            AdapterWarningV1(
                code="unofficial_paper_draft_route",
                message="this local route envelope is not official SynthEx RouteJSON",
            )
        ]
        unsupported_fields: list[str] = []
        for index, raw_step in enumerate(raw_steps):
            step = _object(raw_step, label=f"steps[{index}]")
            step_id = step.get("step_id")
            if not isinstance(step_id, str) or not step_id:
                raise ValueError(f"steps[{index}].step_id must be non-empty")
            reaction_payload = _object(step.get("reaction"), label=f"steps[{index}].reaction")
            mapped_product = step.get("mapped_product_smiles")
            if not isinstance(mapped_product, str):
                mapped_product = reaction_payload.get("mapped_product_smiles")
            normalized = SynthExPaperDraftAdapter().normalize(
                SynthExPaperDraftInput(
                    payload=reaction_payload,
                    mapped_product_smiles=mapped_product,
                    reaction_id=f"{source.route_id or envelope.get('route_id', 'route')}:{step_id}",
                )
            )
            warnings.extend(normalized.warnings)
            unsupported_fields.extend(
                f"steps[{index}].reaction.{value}" for value in normalized.unsupported_fields
            )
            depends_on = _sequence(step.get("depends_on", []), label=f"steps[{index}].depends_on")
            consumes = _sequence(step.get("consumes", []), label=f"steps[{index}].consumes")
            produces = _sequence(step.get("produces", []), label=f"steps[{index}].produces")
            if not all(isinstance(value, str) for value in (*depends_on, *consumes, *produces)):
                raise ValueError(f"steps[{index}] dependency and material IDs must be strings")
            strategy_text = step.get("strategy_text")
            if strategy_text is not None and not isinstance(strategy_text, str):
                raise ValueError(f"steps[{index}].strategy_text must be text")
            key_step = step.get("key_step", False)
            if not isinstance(key_step, bool):
                raise ValueError(f"steps[{index}].key_step must be boolean")
            step_metadata = step.get("metadata", {})
            if not isinstance(step_metadata, dict):
                raise ValueError(f"steps[{index}].metadata must be an object")
            steps.append(
                RouteStepIRV1(
                    step_id=step_id,
                    reaction=normalized.reaction_ir,
                    depends_on=tuple(depends_on),
                    consumes=tuple(consumes),
                    produces=tuple(produces),
                    strategy_text=strategy_text,
                    key_step=key_step,
                    metadata=step_metadata,
                )
            )
            known_step_fields = {
                "step_id",
                "reaction",
                "mapped_product_smiles",
                "depends_on",
                "consumes",
                "produces",
                "strategy_text",
                "key_step",
                "metadata",
            }
            unsupported_fields.extend(
                f"steps[{index}].{key}" for key in step if key not in known_step_fields
            )

        known_route_fields = {
            "schema",
            "schema_version",
            "route_id",
            "target",
            "starting_materials",
            "intermediates",
            "steps",
            "strategy_text",
            "metadata",
        }
        unsupported_fields.extend(key for key in envelope if key not in known_route_fields)
        serialized = json.dumps(source.payload, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(serialized.encode()).hexdigest()
        route_id = source.route_id or str(envelope.get("route_id") or f"draft-{digest[:16]}")
        route_metadata = envelope.get("metadata", {})
        if not isinstance(route_metadata, dict):
            raise ValueError("route metadata must be an object")
        strategy_text = envelope.get("strategy_text")
        if strategy_text is not None and not isinstance(strategy_text, str):
            raise ValueError("route strategy_text must be text")
        route = RouteIRV1(
            route_id=route_id,
            target=MoleculeRecord(mapped_smiles=target_smiles, role=MoleculeRole.PRODUCT),
            starting_materials=_molecule_records(
                envelope.get("starting_materials", []), MoleculeRole.STARTING_MATERIAL
            ),
            intermediates=_molecule_records(
                envelope.get("intermediates", []), MoleculeRole.INTERMEDIATE
            ),
            steps=tuple(steps),
            strategy_text=strategy_text,
            provenance=(
                ProvenanceRecord(
                    source=SYNTHEX_REPOSITORY,
                    source_commit=SYNTHEX_UPSTREAM_COMMIT,
                    adapter=SYNTHEX_DRAFT_ROUTE_ID,
                    adapter_version=__version__,
                    metadata={"official_compatibility": False, "upstream_license": "absent"},
                ),
            ),
            metadata={
                **route_metadata,
                "adapter_namespace": SYNTHEX_DRAFT_ROUTE_ID,
                "official_compatibility": False,
                "source_sha256": digest,
                "unsupported_fields": sorted(unsupported_fields),
            },
        )
        return RouteAdapterResultV1(
            adapter_id=self.adapter_id,
            route_ir=route,
            warnings=tuple(warnings),
            unsupported_fields=tuple(sorted(unsupported_fields)),
            source_payload=source.payload,
        )

    def to_route_ir(self, source: SynthExPaperDraftRouteInput) -> RouteIRV1:
        return self.normalize(source).route_ir
