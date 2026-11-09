from datetime import datetime
from typing import Literal, Protocol

from fibo_ai.schemas.assistant import (
    DowntimeRecord,
    IncidentRecord,
    MachineAggregate,
    MachineRecord,
    RiskRow,
)


def _in_range(value: str, since: str, until: str) -> bool:
    def parse(item: str) -> datetime:
        return datetime.fromisoformat(item.replace("Z", "+00:00"))

    return parse(since) <= parse(value) < parse(until)


class DataRepository(Protocol):
    async def get_incidents(
        self,
        *,
        workshop_id: str,
        since: str,
        until: str,
        machine_id: str | None = None,
        status: str | None = None,
        limit: int = 200,
    ) -> list[IncidentRecord]: ...

    async def get_downtime(
        self,
        *,
        workshop_id: str,
        since: str,
        until: str,
        machine_id: str | None = None,
    ) -> list[DowntimeRecord]: ...

    async def top_machines(
        self,
        *,
        workshop_id: str,
        since: str,
        until: str,
        by: Literal["incidents", "downtime_hours", "loss_kzt"],
        limit: int = 5,
    ) -> list[MachineAggregate]: ...

    async def get_risk_ranking(self, *, workshop_id: str) -> list[RiskRow]: ...

    async def get_machine(self, *, workshop_id: str, machine_id: str) -> MachineRecord | None: ...


class FakeRepository:
    """In-memory synthetic repository for testing and Phase 0/demo operations."""

    def __init__(self) -> None:
        self.machines = [
            MachineRecord(
                id="ЧПУ-1",
                name="Токарный ЧПУ-1 (CK6140)",
                profile="metalworking",
                rated_rpm=3000.0,
                rated_torque_nm=55.0,
            ),
            MachineRecord(
                id="ЧПУ-2",
                name="Фрезерный ЧПУ-2 (VMC850)",
                profile="metalworking",
                rated_rpm=8000.0,
                rated_torque_nm=45.0,
            ),
            MachineRecord(
                id="ЧПУ-3",
                name="Фрезерный ЧПУ-3 (VMC650)",
                profile="metalworking",
                rated_rpm=6000.0,
                rated_torque_nm=40.0,
            ),
            MachineRecord(
                id="Пила-1",
                name="Ленточная пила BS-280",
                profile="metalworking",
                rated_rpm=1400.0,
                rated_torque_nm=75.0,
            ),
        ]
        self.incidents = [
            IncidentRecord(
                id="inc-101",
                workshop_id="ws-shymkent-01",
                machine_id="ЧПУ-2",
                created_at="2026-10-12T09:30:00Z",
                level="critical",
                status="resolved",
                loss_kzt=180000,
                downtime_hours=6.0,
            ),
            IncidentRecord(
                id="inc-102",
                workshop_id="ws-shymkent-01",
                machine_id="ЧПУ-2",
                created_at="2026-10-24T14:15:00Z",
                level="attention",
                status="resolved",
                loss_kzt=90000,
                downtime_hours=3.0,
            ),
            IncidentRecord(
                id="inc-103",
                workshop_id="ws-shymkent-01",
                machine_id="ЧПУ-1",
                created_at="2026-10-18T11:00:00Z",
                level="attention",
                status="resolved",
                loss_kzt=45000,
                downtime_hours=2.0,
            ),
        ]

    async def get_incidents(
        self,
        *,
        workshop_id: str,
        since: str,
        until: str,
        machine_id: str | None = None,
        status: str | None = None,
        limit: int = 200,
    ) -> list[IncidentRecord]:
        results = [inc for inc in self.incidents if inc.workshop_id == workshop_id]
        results = [inc for inc in results if _in_range(inc.created_at, since, until)]
        if machine_id:
            results = [inc for inc in results if inc.machine_id == machine_id]
        if status:
            results = [inc for inc in results if inc.status == status]
        return results[:limit]

    async def get_downtime(
        self,
        *,
        workshop_id: str,
        since: str,
        until: str,
        machine_id: str | None = None,
    ) -> list[DowntimeRecord]:
        if workshop_id != "ws-shymkent-01":
            return []
        results = [
            DowntimeRecord(
                id="dt-01",
                machine_id="ЧПУ-2",
                start_time="2026-10-12T09:30:00Z",
                end_time="2026-10-12T15:30:00Z",
                hours=6.0,
                reason="Перегрев подшипника шпинделя",
            ),
            DowntimeRecord(
                id="dt-02",
                machine_id="ЧПУ-2",
                start_time="2026-10-24T14:15:00Z",
                end_time="2026-10-24T17:15:00Z",
                hours=3.0,
                reason="Замена изношенного резца",
            ),
            DowntimeRecord(
                id="dt-03",
                machine_id="ЧПУ-1",
                start_time="2026-10-18T11:00:00Z",
                end_time="2026-10-18T13:00:00Z",
                hours=2.0,
                reason="Очистка стружкосборника",
            ),
        ]
        results = [row for row in results if _in_range(row.start_time, since, until)]
        if machine_id:
            results = [row for row in results if row.machine_id == machine_id]
        return results

    async def top_machines(
        self,
        *,
        workshop_id: str,
        since: str,
        until: str,
        by: Literal["incidents", "downtime_hours", "loss_kzt"],
        limit: int = 5,
    ) -> list[MachineAggregate]:
        incidents = await self.get_incidents(workshop_id=workshop_id, since=since, until=until, limit=200)
        downtime = await self.get_downtime(workshop_id=workshop_id, since=since, until=until)
        machine_ids = {row.machine_id for row in incidents} | {row.machine_id for row in downtime}
        aggregates = []
        for machine_id in machine_ids:
            machine = await self.get_machine(workshop_id=workshop_id, machine_id=machine_id)
            if not machine:
                continue
            inc = [row for row in incidents if row.machine_id == machine_id]
            dt = [row for row in downtime if row.machine_id == machine_id]
            aggregates.append(
                MachineAggregate(
                    machine_id=machine_id,
                    machine_name=machine.name,
                    incidents_count=len(inc),
                    downtime_hours=sum(row.hours for row in dt),
                    loss_kzt=sum(row.loss_kzt for row in inc),
                )
            )
        if by == "downtime_hours":
            aggregates.sort(key=lambda row: (-row.downtime_hours, row.machine_id))
        elif by == "loss_kzt":
            aggregates.sort(key=lambda row: (-row.loss_kzt, row.machine_id))
        else:
            aggregates.sort(key=lambda row: (-row.incidents_count, row.machine_id))
        return aggregates[:limit]

    async def get_risk_ranking(self, *, workshop_id: str) -> list[RiskRow]:
        if workshop_id != "ws-shymkent-01":
            return []
        return [
            RiskRow(
                machine_id="ЧПУ-2",
                machine_name="Фрезерный ЧПУ-2 (VMC850)",
                risk_index=0.84,
                priority_kzt=315000,
                risk_band="high",
            ),
            RiskRow(
                machine_id="ЧПУ-1",
                machine_name="Токарный ЧПУ-1 (CK6140)",
                risk_index=0.48,
                priority_kzt=90000,
                risk_band="medium",
            ),
            RiskRow(
                machine_id="Пила-1",
                machine_name="Ленточная пила BS-280",
                risk_index=0.18,
                priority_kzt=25000,
                risk_band="low",
            ),
        ]

    async def get_machine(self, *, workshop_id: str, machine_id: str) -> MachineRecord | None:
        if workshop_id != "ws-shymkent-01":
            return None
        for m in self.machines:
            if m.id == machine_id:
                return m
        return None
