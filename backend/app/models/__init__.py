"""All ORM models. Importing this package registers every table on Base.metadata.

Alembic (alembic/env.py) and the tests import it so that metadata is complete.
"""

from app.models.attachment import Attachment
from app.models.baseline import Baseline
from app.models.incident import Incident
from app.models.machine import Machine
from app.models.manual import Manual
from app.models.reading import Reading
from app.models.risk_score import RiskScore
from app.models.user import User
from app.models.workshop import Workshop

__all__ = [
    "Attachment",
    "Baseline",
    "Incident",
    "Machine",
    "Manual",
    "Reading",
    "RiskScore",
    "User",
    "Workshop",
]
