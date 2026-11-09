"""Fibo Machine: is the latest reading unusual compared with this machine's own history?

Isolation Forest isolates points with random splits; points that are isolated after few splits are
unusual. We fit it per machine on its numeric readings and ask whether the latest one is an outlier.

  - Only columns that the latest reading has are used (plus numeric `extra` values, e.g. humidity).
    operating_hours is excluded: it is a counter that always grows, so the newest value would
    always look "unusual".
  - Needs at least 20 complete readings, otherwise: not an anomaly, reason "insufficient history".
  - contamination=0.05 (we expect ~5% unusual readings), fixed random_state for repeatable results.
CPU work: call via asyncio.to_thread.
"""

from dataclasses import dataclass

import numpy as np
from sklearn.ensemble import IsolationForest

MIN_HISTORY = 20
CORE_COLUMNS = ("spindle_rpm", "load_pct", "temperature_c")


@dataclass
class AnomalyResult:
    is_anomaly: bool
    reason: str
    columns: list[str]


def _row_values(row: dict, columns: list[str]) -> list[float] | None:
    values = []
    for column in columns:
        value = row.get(column)
        if value is None:
            value = (row.get("extra") or {}).get(column)
        if value is None:
            return None
        values.append(float(value))
    return values


def detect_anomaly(rows: list[dict]) -> AnomalyResult:
    """rows: readings as dicts (oldest -> newest) with core columns and optional `extra`."""
    if not rows:
        return AnomalyResult(False, "insufficient history", [])
    latest = rows[-1]
    columns = [c for c in CORE_COLUMNS if latest.get(c) is not None]
    columns += sorted(k for k, v in (latest.get("extra") or {}).items() if isinstance(v, int | float))
    if not columns:
        return AnomalyResult(False, "latest reading has no numeric values", [])

    matrix = [values for row in rows if (values := _row_values(row, columns)) is not None]
    if len(matrix) < MIN_HISTORY:
        return AnomalyResult(False, "insufficient history", columns)

    forest = IsolationForest(n_estimators=100, contamination=0.05, random_state=42)
    forest.fit(np.array(matrix))
    is_outlier = forest.predict(np.array([_row_values(latest, columns)]))[0] == -1
    reason = "latest reading is unusual for this machine" if is_outlier else "latest reading is typical"
    return AnomalyResult(bool(is_outlier), reason, columns)
