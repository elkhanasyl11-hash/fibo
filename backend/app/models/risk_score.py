"""Risk scores table: one row per risk computation for a machine (history kept for charts).

failure_probability is the calibrated XGBoost output, or NULL when the model does not apply
(e.g. food or sewing machines). risk_index (0..1) combines all available signals; priority_kzt is
the expected-loss ranking value. inputs_used lists which signals were available, shap_factors
explains the score. model_version records which model artifacts produced it.
"""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import JSON, CheckConstraint, ForeignKey, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UTCDateTime, utcnow

if TYPE_CHECKING:
    from app.models.machine import Machine


class RiskScore(Base):
    __tablename__ = "risk_scores"
    __table_args__ = (
        CheckConstraint("risk_index >= 0 AND risk_index <= 1", name="risk_index_range"),
        # "latest score per machine" and the risk-history chart both filter by machine, sort by time.
        Index("ix_risk_scores_machine_id_computed_at", "machine_id", "computed_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    machine_id: Mapped[int] = mapped_column(ForeignKey("machines.id", ondelete="CASCADE"), index=True)
    computed_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    failure_probability: Mapped[float | None]
    risk_index: Mapped[float]
    priority_kzt: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, index=True)
    shap_factors: Mapped[list] = mapped_column(JSON, default=list)
    is_anomaly: Mapped[bool] = mapped_column(default=False)
    inputs_used: Mapped[list] = mapped_column(JSON, default=list)
    model_version: Mapped[str] = mapped_column(String(50), default="none")

    # lazy="joined": the machine is loaded in the same query as the score, so is_demo below can be
    # read without another database round trip (async sessions cannot lazy-load later).
    machine: Mapped["Machine"] = relationship(back_populates="risk_scores", lazy="joined")

    @property
    def is_demo(self) -> bool:
        """A score is demo data exactly when its machine is (not a separate column)."""
        return self.machine.is_demo
