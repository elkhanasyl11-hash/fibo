"""Manual upload + background indexing, and the RAG acceptance test: the card cites only retrieved pages."""

from tests.conftest import BOT_HEADERS
from tests.pdf_samples import manual_pdf, standard_manual
from tests.test_pipeline import say, upload


async def _upload(client, machine_id, data, name="passport.pdf", content_type="application/pdf"):
    return await client.post(
        f"/api/v1/machines/{machine_id}/manuals", files={"file": (name, data, content_type)}
    )


async def test_manual_is_indexed_with_scan_warning(client, make_workshop, make_machine):
    machine = await make_machine((await make_workshop())["id"])
    response = await _upload(client, machine["id"], standard_manual())
    assert response.status_code == 202 and response.json()["index_status"] == "pending"
    manual = (await client.get(f"/api/v1/manuals/{response.json()['id']}")).json()
    assert manual["index_status"] == "ready" and manual["page_count"] == 4
    assert manual["original_filename"] == "passport.pdf"
    assert manual["error_message"] == "Warning: pages without text (scanned?): 4"
    listed = (await client.get(f"/api/v1/machines/{machine['id']}/manuals")).json()
    assert [m["id"] for m in listed] == [manual["id"]]


async def test_scanned_only_pdf_fails_clearly(client, make_workshop, make_machine):
    machine = await make_machine((await make_workshop())["id"])
    manual_id = (await _upload(client, machine["id"], manual_pdf(["", ""]))).json()["id"]
    manual = (await client.get(f"/api/v1/manuals/{manual_id}")).json()
    assert manual["index_status"] == "failed" and "scanned" in manual["error_message"]


async def test_non_pdf_is_rejected(client, make_workshop, make_machine):
    machine = await make_machine((await make_workshop())["id"])
    assert (
        await _upload(client, machine["id"], b"hello", name="x.txt", content_type="text/plain")
    ).status_code == 415


async def test_card_cites_only_retrieved_pages(client, make_workshop, make_machine, monkeypatch):
    """Spec acceptance (phase 7): the mock LLM always adds page 999; only real retrieved pages survive."""
    workshop = await make_workshop()
    machine = await make_machine(workshop["id"])
    await _upload(client, machine["id"], standard_manual())
    body = {
        "telegram_id": 770000 + machine["id"],
        "full_name": "Айбек",
        "invite_code": workshop["invite_code"],
        "role": "operator",
    }
    assert (await client.post("/api/v1/bot/register", json=body, headers=BOT_HEADERS)).status_code == 201

    say(monkeypatch, "Шпиндель гудит на высоких оборотах")
    incident_id = (await upload(client, body["telegram_id"], machine["id"])).json()["incident_id"]
    incident = (await client.get(f"/api/v1/incidents/{incident_id}")).json()
    assert incident["status"] == "open"
    assert 2 in incident["manual_pages"]  # the spindle page was retrieved and cited
    assert 999 not in incident["manual_pages"]  # the invented page was dropped
    assert "Паспорт: стр." in incident["card_text"] and "999" not in incident["card_text"]

    excerpts = (
        await client.get(f"/api/v1/incidents/{incident_id}/manual-excerpts", headers=BOT_HEADERS)
    ).json()
    assert 2 in [e["page"] for e in excerpts["excerpts"]]


async def test_health_reports_chroma(client):
    assert (await client.get("/api/v1/health")).json()["chroma"] == "ok"
