"""Workshops, web users and Telegram bot registration."""

from tests.conftest import BOT_HEADERS


async def test_create_workshop_generates_invite_code(client, make_workshop):
    workshop = await make_workshop("bakery")
    assert len(workshop["invite_code"]) == 6 and workshop["invite_code"].isalnum()
    assert workshop["is_demo"] is False
    response = await client.get(f"/api/v1/workshops/{workshop['id']}")
    assert response.json()["invite_code"] == workshop["invite_code"]


async def test_unknown_profile_is_422(client):
    response = await client.post("/api/v1/workshops", json={"name": "X", "profile": "brewery"})
    assert response.status_code == 422


async def test_bot_register_and_lookup(client, make_workshop, make_machine):
    workshop = await make_workshop()
    machine = await make_machine(workshop["id"])
    body = {
        "telegram_id": 5001,
        "full_name": "Айбек",
        "invite_code": f" {workshop['invite_code'].lower()} ",
        "role": "operator",
        "language": "kk",
    }
    response = await client.post("/api/v1/bot/register", json=body, headers=BOT_HEADERS)
    assert response.status_code == 201, response.text
    assert response.json()["workshop_id"] == workshop["id"]

    again = await client.post("/api/v1/bot/register", json=body, headers=BOT_HEADERS)
    assert again.status_code == 409

    info = await client.get("/api/v1/bot/users/5001", headers=BOT_HEADERS)
    assert info.status_code == 200
    data = info.json()
    assert data["user"]["language"] == "kk"
    assert data["workshop"]["id"] == workshop["id"]
    assert [m["id"] for m in data["machines"]] == [machine["id"]]


async def test_bot_register_rejects_bad_invite_and_owner_role(client):
    body = {"telegram_id": 5002, "full_name": "X", "invite_code": "NOPE99", "role": "operator"}
    assert (await client.post("/api/v1/bot/register", json=body, headers=BOT_HEADERS)).status_code == 404
    body["role"] = "owner"
    assert (await client.post("/api/v1/bot/register", json=body, headers=BOT_HEADERS)).status_code == 422


async def test_bot_endpoints_require_bot_token(client):
    assert (await client.get("/api/v1/bot/users/1")).status_code == 401
    wrong = {"X-Fibo-Bot-Token": "wrong"}
    assert (await client.get("/api/v1/bot/users/1", headers=wrong)).status_code == 401
    assert (await client.get("/api/v1/bot/users/999999", headers=BOT_HEADERS)).status_code == 404


async def test_web_user_crud(client, make_workshop):
    workshop = await make_workshop()
    created = await client.post(
        "/api/v1/users", json={"full_name": "Гульнара", "role": "owner", "workshop_id": workshop["id"]}
    )
    assert created.status_code == 201
    user_id = created.json()["id"]
    patched = await client.patch(f"/api/v1/users/{user_id}", json={"language": "kk"})
    assert patched.json()["language"] == "kk"
    listed = await client.get("/api/v1/users", params={"workshop_id": workshop["id"]})
    assert [u["id"] for u in listed.json()] == [user_id]
    missing_ws = await client.post(
        "/api/v1/users", json={"full_name": "X", "role": "owner", "workshop_id": 99999}
    )
    assert missing_ws.status_code == 404
