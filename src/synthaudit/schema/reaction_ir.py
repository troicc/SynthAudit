"""Versioned canonical single-reaction representation."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, JsonValue, model_validator

from synthaudit.schema.common import (
    MoleculeRecord,
    MoleculeRole,
    ProvenanceRecord,
    ReactionConditions,
    SourcePayloadReference,
    StrictModel,
)
from synthaudit.schema.edits import AtomStateEdit, AttachmentEdit, CoreEdit, StereoEdit


class ReactionIRV1(StrictModel):
    """Canonical representation of mapped-product to mapped-precursor edits."""

    schema_version: Literal["synthaudit.reaction-ir/1"] = "synthaudit.reaction-ir/1"
    reaction_id: str = Field(min_length=1)
    direction: Literal["retrosynthesis"] = "retrosynthesis"
    product: MoleculeRecord
    expected_precursors: tuple[MoleculeRecord, ...] = ()
    core_edits: tuple[CoreEdit, ...] = ()
    attachment_edits: tuple[AttachmentEdit, ...] = ()
    atom_state_edits: tuple[AtomStateEdit, ...] = ()
    stereo_edits: tuple[StereoEdit, ...] = ()
    conditions: ReactionConditions | None = None
    stage_metadata: dict[str, JsonValue] = Field(default_factory=dict)
    provenance: tuple[ProvenanceRecord, ...] = ()
    source_payload_reference: SourcePayloadReference | None = None
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_roles_and_ids(self) -> ReactionIRV1:
        if self.product.role != MoleculeRole.PRODUCT:
            raise ValueError("ReactionIR product must have role='product'")
        if any(item.role != MoleculeRole.PRECURSOR for item in self.expected_precursors):
            raise ValueError("expected precursors must have role='precursor'")
        edit_ids = [
            edit.edit_id
            for edit in (
                *self.core_edits,
                *self.attachment_edits,
                *self.atom_state_edits,
                *self.stereo_edits,
            )
            if edit.edit_id is not None
        ]
        if len(edit_ids) != len(set(edit_ids)):
            raise ValueError("edit_id values must be unique within a reaction")
        return self

    @property
    def edit_count(self) -> int:
        """Return the number of declared edits across all execution stages."""
        return sum(
            map(
                len,
                (
                    self.core_edits,
                    self.attachment_edits,
                    self.atom_state_edits,
                    self.stereo_edits,
                ),
            )
        )
