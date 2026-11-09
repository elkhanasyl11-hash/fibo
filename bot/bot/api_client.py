"""The ONLY place where the bot talks to the Fibo backend.

Every request carries the shared secret (X-Fibo-Bot-Token) and has a 30 s timeout. Backend
errors arrive in the API's single error shape and are raised as FiboApiError(status, code); the
handlers turn them into short, friendly messages (texts.py). Network problems become
FiboApiError(status=0, code="unreachable").
"""

import httpx


class FiboApiError(Exception):
    def __init__(self, status: int, code: str, message: str = "") -> None:
        super().__init__(f"{status} {code}: {message}")
        self.status, self.code, self.message = status, code, message


class FiboApi:
    def __init__(
        self,
        base_url: str,
        bot_secret: str,
        timeout_s: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout_s,
            transport=transport,
            headers={"X-Fibo-Bot-Token": bot_secret},
        )

    async def close(self) -> None:
        await self.client.aclose()

    async def _request(self, method: str, path: str, **kwargs) -> dict | list:
        try:
            response = await self.client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise FiboApiError(0, "unreachable", type(exc).__name__) from exc
        if response.status_code >= 400:
            try:
                error = response.json()["error"]
                raise FiboApiError(response.status_code, error["code"], error["message"])
            except (ValueError, KeyError, TypeError):
                raise FiboApiError(response.status_code, "http_error", response.text[:200]) from None
        return response.json() if response.content else {}

    # --- users -------------------------------------------------------------------------------
    async def get_user(self, telegram_id: int) -> dict | None:
        """{user, workshop, machines} or None if this Telegram account is not registered."""
        try:
            return await self._request("GET", f"/bot/users/{telegram_id}")
        except FiboApiError as exc:
            if exc.status == 404:
                return None
            raise

    async def register(
        self, telegram_id: int, full_name: str, invite_code: str, role: str, language: str
    ) -> dict:
        body = {
            "telegram_id": telegram_id,
            "full_name": full_name,
            "invite_code": invite_code,
            "role": role,
            "language": language,
        }
        return await self._request("POST", "/bot/register", json=body)

    async def link_account(self, telegram_id: int, token: str) -> dict:
        """Attach this Telegram to a web account (owner) from the site's t.me/...?start=own… link."""
        return await self._request("POST", "/bot/link", json={"telegram_id": telegram_id, "token": token})

    # --- machines ----------------------------------------------------------------------------
    async def profiles(self) -> list[dict]:
        return await self._request("GET", "/profiles")

    async def create_machine(self, workshop_id: int, name: str, type_: str, criticality: int) -> dict:
        body = {"workshop_id": workshop_id, "name": name, "type": type_, "criticality": criticality}
        return await self._request("POST", "/machines", json=body)

    async def upload_audio_baseline(
        self, machine_id: int, data: bytes, filename: str, content_type: str = "audio/ogg"
    ) -> dict:
        files = {"file": (filename, data, content_type)}
        return await self._request("POST", f"/machines/{machine_id}/baselines/audio", files=files)

    async def upload_photo_baseline(self, machine_id: int, data: bytes) -> dict:
        files = {"file": ("photo.jpg", data, "image/jpeg")}
        return await self._request("POST", f"/machines/{machine_id}/baselines/photo", files=files)

    async def upload_manual(self, machine_id: int, data: bytes, filename: str) -> dict:
        files = {"file": (filename, data, "application/pdf")}
        return await self._request("POST", f"/machines/{machine_id}/manuals", files=files)

    async def get_manual(self, manual_id: int) -> dict:
        return await self._request("GET", f"/manuals/{manual_id}")

    # --- readings ----------------------------------------------------------------------------
    async def read_panel(self, machine_id: int, data: bytes) -> dict:
        """Suggested values from a display photo; nothing is saved by the backend."""
        files = {"file": ("panel.jpg", data, "image/jpeg")}
        return await self._request(
            "POST", "/readings/panel-photo", data={"machine_id": str(machine_id)}, files=files
        )

    async def create_reading(
        self,
        machine_id: int,
        values: dict[str, float],
        extra_fields: list[str],
        user_id: int | None,
        source: str = "panel",
    ) -> dict:
        body = {
            "machine_id": machine_id,
            "source": source,
            "created_by_user_id": user_id,
            **{k: v for k, v in values.items() if k not in extra_fields},
        }
        extra = {k: v for k, v in values.items() if k in extra_fields}
        if extra:
            body["extra"] = extra
        return await self._request("POST", "/readings", json=body)

    # --- incidents ---------------------------------------------------------------------------
    async def ingest_voice(
        self,
        telegram_id: int,
        machine_id: int,
        data: bytes,
        filename: str,
        mode: str = "auto",
        content_type: str = "audio/ogg",
    ) -> int:
        form = {"telegram_id": str(telegram_id), "machine_id": str(machine_id), "mode": mode}
        files = {"file": (filename, data, content_type)}
        return (await self._request("POST", "/ingest/voice", data=form, files=files))["incident_id"]

    async def ingest_photo(self, telegram_id: int, machine_id: int, data: bytes, caption: str | None) -> int:
        form = {"telegram_id": str(telegram_id), "machine_id": str(machine_id)}
        if caption:
            form["caption"] = caption
        files = {"file": ("photo.jpg", data, "image/jpeg")}
        return (await self._request("POST", "/ingest/photo", data=form, files=files))["incident_id"]

    async def ingest_text(self, telegram_id: int, machine_id: int, text: str) -> int:
        body = {"telegram_id": telegram_id, "machine_id": machine_id, "text": text[:2000]}
        return (await self._request("POST", "/ingest/text", json=body))["incident_id"]

    async def get_incident(self, incident_id: int) -> dict:
        return await self._request("GET", f"/incidents/{incident_id}")

    async def manual_excerpts(self, incident_id: int) -> list[dict]:
        return (await self._request("GET", f"/incidents/{incident_id}/manual-excerpts"))["excerpts"]

    async def resolve(self, incident_id: int) -> dict:
        return await self._request("PATCH", f"/incidents/{incident_id}/resolve")

    async def escalate(self, incident_id: int) -> dict:
        return await self._request("POST", f"/incidents/{incident_id}/escalate")
