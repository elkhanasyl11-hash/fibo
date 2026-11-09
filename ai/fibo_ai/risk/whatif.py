"""Vectorized what-if maintenance simulation."""

from collections.abc import Callable, Coroutine
from typing import Any

from fibo_ai.schemas.risk import RiskRequest, RiskResult, WhatIfRequest, WhatIfResult


async def simulate_what_if(
    req: WhatIfRequest,
    predict_fn: Callable[[RiskRequest], Coroutine[Any, Any, RiskResult]],
) -> WhatIfResult:
    """Run before/after simulation under simulated maintenance overrides."""
    before = await predict_fn(req.current)

    # Apply overrides to deep copy of current request
    modified_dict = req.current.model_dump()
    for key, val in req.overrides.items():
        if key in modified_dict.get("readings", {}):
            modified_dict["readings"][key] = val
        elif key in modified_dict.get("context", {}):
            modified_dict["context"][key] = val
        elif key in modified_dict.get("signals", {}):
            modified_dict["signals"][key] = val

    modified_req = RiskRequest.model_validate(modified_dict)
    after = await predict_fn(modified_req)

    delta_index = round(after.risk_index - before.risk_index, 4)
    delta_priority = int(before.priority_kzt - after.priority_kzt)

    return WhatIfResult(
        request_id=f"whatif-{before.request_id}",
        model_version=before.model_version,
        config_version=before.config_version,
        machine_id=req.machine_id,
        before=before,
        after=after,
        delta_index=delta_index,
        delta_priority_kzt=delta_priority,
        changed_factors=list(req.overrides.keys()),
        degraded=[],
    )
