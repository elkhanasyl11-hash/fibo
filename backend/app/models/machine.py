"""Machine registry table. One row per physical machine in a workshop.

criticality, downtime_cost_per_hour_kzt and avg_repair_hours feed the KZT priority formula
in modules/machine/priority.py. maintenance_interval_hours feeds the "overdue maintenance" signal,
tool_changed_at the tool-wear minutes, batch_value_kzt the extra loss for food profiles.
"""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UTCDateTime

if TYPE_CHECKING:
    from app.models.baseline import Baseline
    from app.models.incident import Incident
    from app.models.manual import Manual
    from app.models.reading import Reading
    from app.models.risk_score import RiskScore
    from app.models.workshop import Workshop


class Machine(TimestampMixin, Base):
    __tablename__ = "machines"
    __table_args__ = (CheckConstraint("criticality BETWEEN 1 AND 3", name="criticality"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    workshop_id: Mapped[int] = mapped_column(ForeignKey("workshops.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    type: Mapped[str] = mapped_column(String(50))
    model: Mapped[str | None] = mapped_column(String(100))
    criticality: Mapped[int] = mapped_column(default=2)
    downtime_cost_per_hour_kzt: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    avg_repair_hours: Mapped[float] = mapped_column(default=4.0)
    last_maintenance_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    maintenance_interval_hours: Mapped[float | None]
    batch_value_kzt: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    tool_changed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    is_demo: Mapped[bool] = mapped_column(default=False)

    workshop: Mapped["Workshop"] = relationship(back_populates="machines")
    readings: Mapped[list["Reading"]] = relationship(
        back_populates="machine", cascade="all, delete-orphan", passive_deletes=True
    )
    risk_scores: Mapped[list["RiskScore"]] = relationship(
        back_populates="machine", cascade="all, delete-orphan", passive_deletes=True
    )
    baselines: Mapped[list["Baseline"]] = relationship(
        back_populates="machine", cascade="all, delete-orphan", passive_deletes=True
    )
    manuals: Mapped[list["Manual"]] = relationship(
        back_populates="machine", cascade="all, delete-orphan", passive_deletes=True
    )
    incidents: Mapped[list["Incident"]] = relationship(
        back_populates="machine", cascade="all, delete-orphan", passive_deletes=True
    )
