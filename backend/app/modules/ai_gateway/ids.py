"""Backend database ids -> AI service ids (integration contract section 4.1).

The AI service stores artifacts by these strings, so they must be stable and unambiguous across
workshops: two workshops can both own a machine called "ЧПУ-2", but never the same `m-<id>`.
Display names travel separately (catalog_machines / machine name in the card).
"""


def ws_id(workshop_id: int) -> str:
    return f"ws-{workshop_id}"


def m_id(machine_id: int) -> str:
    return f"m-{machine_id}"


def manual_id(manual_db_id: int) -> str:
    return f"man-{manual_db_id}"
