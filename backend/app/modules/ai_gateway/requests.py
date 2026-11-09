"""Backend rows -> request parts of the AI service (its schemas forbid extra fields, D81).

machine_context  -> MachineContext (criticality low|medium|high, KZT as integers)
machine_readings -> MachineReadings (backend reading names -> AI names, tool wear in hours)
"""

from app.db.base import utcnow
from app.models.machine import Machine
from app.modules.machine.feature_map import ReadingValues

CRITICALITY = {1: "low", 2: "medium", 3: "high"}  # backend criticality 1..3


def machine_context(machine: Machine) -> dict:
    since_pm = None
    if machine.last_maintenance_at is not None:
        since_pm = round((utcnow() - machine.last_maintenance_at).total_seconds() / 3600, 1)
    return {
        "criticality": CRITICALITY.get(machine.criticality, "medium"),
        "expected_repair_hours": float(machine.avg_repair_hours),
        "cost_per_hour_kzt": int(machine.downtime_cost_per_hour_kzt or 0),
        "batch_value_kzt": int(machine.batch_value_kzt) if machine.batch_value_kzt is not None else None,
        "hours_since_last_pm": since_pm,
        "pm_interval_h": machine.maintenance_interval_hours,
    }


def machine_readings(latest: ReadingValues, tool_wear_min: float | None, ambient_c: float | None) -> dict:
    values = {
        "spindle_rpm": latest.spindle_rpm,
        "spindle_load_pct": latest.load_pct,
        "temp_c": latest.temperature_c,
        "ambient_temp_c": ambient_c,
        "tool_hours": round(tool_wear_min / 60, 3) if tool_wear_min is not None else None,
        "runtime_h": latest.operating_hours,
    }
    return {name: value for name, value in values.items() if value is not None}
