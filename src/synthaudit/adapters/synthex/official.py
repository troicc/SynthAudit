"""Official SynthEx boundary, unavailable until schemas are published and pinned."""

from __future__ import annotations

from typing import NoReturn

from synthaudit.adapters.synthex.errors import UpstreamSpecificationUnavailable


class SynthExOfficialAdapter:
    """Never delegates to the paper-draft adapter."""

    def to_reaction_ir(self, payload: object) -> NoReturn:
        del payload
        raise UpstreamSpecificationUnavailable(
            "official SynthEx ReactionJSON is unavailable at "
            "schwallergroup/synthex@5f41a6b21e3906fde93e84c88bb91f9dc4d37e6f; "
            "the paper-draft adapter is a separate explicit namespace"
        )

    def to_route_ir(self, payload: object) -> NoReturn:
        del payload
        raise UpstreamSpecificationUnavailable(
            "official SynthEx RouteJSON is unavailable at "
            "schwallergroup/synthex@5f41a6b21e3906fde93e84c88bb91f9dc4d37e6f; "
            "no draft adapter is called implicitly"
        )
