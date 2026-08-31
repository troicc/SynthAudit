"""Official-fail-closed and visibly namespaced SynthEx adapters."""

from synthaudit.adapters.synthex.models import (
    SynthExPaperDraftInput,
    SynthExPaperDraftRouteInput,
)
from synthaudit.adapters.synthex.official import SynthExOfficialAdapter
from synthaudit.adapters.synthex.paper_draft import (
    SYNTHEX_DRAFT_ID,
    SynthExPaperDraftAdapter,
)
from synthaudit.adapters.synthex.route_draft import (
    SYNTHEX_DRAFT_ROUTE_ID,
    SynthExPaperDraftRouteAdapter,
)

__all__ = [
    "SYNTHEX_DRAFT_ID",
    "SYNTHEX_DRAFT_ROUTE_ID",
    "SynthExOfficialAdapter",
    "SynthExPaperDraftAdapter",
    "SynthExPaperDraftInput",
    "SynthExPaperDraftRouteAdapter",
    "SynthExPaperDraftRouteInput",
]
