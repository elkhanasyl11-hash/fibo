"""Shared field types for API schemas.

Money: amounts in tenge. Accepted as a number or string with at most 2 decimals, always returned
as a string with exactly 2 decimals ("15000.00"), so JavaScript never rounds it as a float.

UTCDatetime: request datetimes must carry a timezone ("2026-11-07T10:00:00Z" or "+05:00").
A datetime without timezone is ambiguous (Almaty time? UTC?) and is rejected with 422.
"""

from decimal import Decimal
from typing import Annotated

from pydantic import AwareDatetime, BaseModel, Field, PlainSerializer


def _money_to_str(value: Decimal) -> str:
    return f"{value:.2f}"


Money = Annotated[
    Decimal,
    Field(ge=0, max_digits=14, decimal_places=2, examples=["15000.00"]),
    PlainSerializer(_money_to_str, return_type=str, when_used="json"),
]

UTCDatetime = AwareDatetime


def reject_explicit_nulls(model: BaseModel, fields: set[str]) -> None:
    """PATCH bodies: leaving a field out means "keep it", but an explicit null on a column that
    cannot be empty would only fail later in the database (500). Reject it here with a clear 422."""
    nulls = sorted(name for name in fields if name in model.model_fields_set and getattr(model, name) is None)
    if nulls:
        raise ValueError(f"these fields cannot be null: {', '.join(nulls)}")
