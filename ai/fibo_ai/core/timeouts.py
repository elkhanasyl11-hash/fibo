import asyncio
import time
from collections.abc import Awaitable
from typing import TypeVar

from fibo_ai.core.errors import LLMUnavailableError

T = TypeVar("T")


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, recovery_timeout_s: float = 30.0) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout_s = recovery_timeout_s
        self.consecutive_failures = 0
        self.last_failure_time = 0.0
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN

    def record_success(self) -> None:
        self.consecutive_failures = 0
        self.state = "CLOSED"

    def record_failure(self) -> None:
        self.consecutive_failures += 1
        self.last_failure_time = time.time()
        if self.consecutive_failures >= self.failure_threshold:
            self.state = "OPEN"

    def can_attempt(self) -> bool:
        if self.state == "CLOSED":
            return True
        if self.state == "OPEN":
            if time.time() - self.last_failure_time > self.recovery_timeout_s:
                self.state = "HALF_OPEN"
                return True
            return False
        if self.state == "HALF_OPEN":
            return True
        return False


async def with_timeout(
    coro: Awaitable[T],
    timeout_s: float,
    stage_name: str = "stage",
) -> T:
    try:
        return await asyncio.wait_for(coro, timeout=timeout_s)
    except TimeoutError as err:
        raise LLMUnavailableError(
            f"Timeout of {timeout_s}s exceeded in {stage_name}",
            details={"stage": stage_name, "timeout_s": timeout_s},
        ) from err
