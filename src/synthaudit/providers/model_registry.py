"""Local-only registry for fitted evidence models and their immutable manifests."""

from __future__ import annotations

from collections.abc import Iterator

from synthaudit.models.evidence import EvidenceModelManifestV1, EvidenceStage
from synthaudit.models.training import TrainedEvidenceModel


class InMemoryEvidenceModelRegistry:
    """Resolve explicitly registered models without network or implicit artifact loading."""

    def __init__(self) -> None:
        self._models: dict[str, TrainedEvidenceModel] = {}

    def register(self, model: TrainedEvidenceModel) -> EvidenceModelManifestV1:
        model_id = model.manifest.model_id
        existing = self._models.get(model_id)
        if (
            existing is not None
            and existing.manifest.configuration_sha256 != model.manifest.configuration_sha256
        ):
            raise ValueError(f"model ID collision with a different configuration: {model_id}")
        self._models[model_id] = model
        return model.manifest

    def resolve(
        self,
        model_id: str,
        *,
        expected_stage: EvidenceStage | None = None,
        expected_configuration_sha256: str | None = None,
    ) -> TrainedEvidenceModel:
        try:
            model = self._models[model_id]
        except KeyError as error:
            raise LookupError(
                f"model is not registered locally; no artifact was downloaded: {model_id}"
            ) from error
        if expected_stage is not None and model.manifest.stage != expected_stage:
            raise ValueError(
                f"registered model stage {model.manifest.stage.value} does not match "
                f"{expected_stage.value}"
            )
        if (
            expected_configuration_sha256 is not None
            and model.manifest.configuration_sha256 != expected_configuration_sha256
        ):
            raise ValueError("registered model configuration digest does not match the request")
        return model

    def manifests(self) -> tuple[EvidenceModelManifestV1, ...]:
        return tuple(self._models[key].manifest for key in sorted(self._models))

    def __len__(self) -> int:
        return len(self._models)

    def __iter__(self) -> Iterator[str]:
        return iter(sorted(self._models))
