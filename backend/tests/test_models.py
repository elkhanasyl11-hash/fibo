"""Database models: constraints, enum storage, UTC timestamps, cascades."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.db.base import IncidentInput, IncidentStatus, Profile, Role
from app.models import Incident, Machine, User, Workshop


async def _workshop(session, code: str) -> Workshop:
    workshop = Workshop(name="Test workshop", city="Шымкент", profile=Profile.METALWORKING, invite_code=code)
    session.add(workshop)
    await session.flush()
    return workshop


async def test_enum_is_stored_as_value_and_time_is_utc(session):
    workshop = await _workshop(session, "ENUM01")
    session.add(User(full_name="Оператор", role=Role.OPERATOR, workshop_id=workshop.id, telegram_id=111))
    await session.commit()

    raw_role = (await session.execute(text("SELECT role FROM users WHERE telegram_id = 111"))).scalar_one()
    assert raw_role == "operator"

    session.expire_all()
    user = (await session.scalars(select(User).where(User.telegram_id == 111))).one()
    assert user.role is Role.OPERATOR
    assert user.created_at.tzinfo is not None and user.created_at.utcoffset().total_seconds() == 0


async def test_machine_criticality_check(session):
    workshop = await _workshop(session, "CRIT01")
    session.add(Machine(workshop_id=workshop.id, name="Bad", type="lathe", criticality=5))
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()


async def test_naive_datetime_is_rejected(session):
    workshop = await _workshop(session, "NAIVE1")
    session.add(
        Machine(workshop_id=workshop.id, name="M", type="lathe", last_maintenance_at=datetime(2026, 1, 1))
    )
    with pytest.raises(Exception, match="Naive datetime"):
        await session.commit()
    await session.rollback()


async def test_deleting_workshop_cascades_and_user_delete_sets_null(session):
    workshop = await _workshop(session, "CASC01")
    user = User(full_name="Мастер", role=Role.MASTER, workshop_id=workshop.id)
    machine = Machine(
        workshop_id=workshop.id,
        name="ЧПУ-1",
        type="cnc_mill",
        downtime_cost_per_hour_kzt=Decimal("15000.00"),
        last_maintenance_at=datetime(2026, 10, 1, tzinfo=UTC),
    )
    session.add_all([user, machine])
    await session.flush()
    incident = Incident(machine_id=machine.id, user_id=user.id, input_type=IncidentInput.VOICE)
    session.add(incident)
    await session.commit()
    assert incident.status is IncidentStatus.RECEIVED
    assert incident.causes == [] and incident.safety_triggered is False

    await session.execute(text("DELETE FROM users WHERE id = :id"), {"id": user.id})
    await session.commit()
    user_id = (
        await session.execute(text("SELECT user_id FROM incidents WHERE id = :id"), {"id": incident.id})
    ).scalar_one()
    assert user_id is None

    await session.execute(text("DELETE FROM workshops WHERE id = :id"), {"id": workshop.id})
    await session.commit()
    remaining = (
        await session.execute(
            text("SELECT COUNT(*) FROM machines WHERE workshop_id = :id"), {"id": workshop.id}
        )
    ).scalar_one()
    assert remaining == 0
