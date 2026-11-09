"""Workshop authorization for browser sessions; internal clients retain their shared-key scope."""

from fastapi import Request
from sqlalchemy import select

from app.core.errors import AuthError, ForbiddenError, NotFoundError
from app.core.passwords import read_token
from app.db.session import SessionLocal
from app.models.attachment import Attachment
from app.models.baseline import Baseline
from app.models.incident import Incident
from app.models.machine import Machine
from app.models.manual import Manual
from app.models.user import User


async def authorize_browser(request: Request, token: str) -> None:
    user_id = read_token(token)
    async with SessionLocal() as session:
        user = await session.get(User, user_id) if user_id else None
        if user is None:
            raise AuthError("Sign in again")
        request.state.workshop_id = user.workshop_id
        if request.url.path.startswith("/api/v1/auth/"):
            return
        ids = dict(request.query_params)
        ids.update(request.path_params)
        if request.headers.get("content-type", "").startswith("application/json"):
            try:
                body = await request.json()
                if isinstance(body, dict):
                    if (
                        request.url.path.startswith("/api/v1/users/")
                        and "role" in body
                        and body["role"] != user.role.value
                    ):
                        raise ForbiddenError("Account roles cannot be changed through a browser session")
                    for key in ("workshop_id", "machine_id", "user_id", "created_by_user_id"):
                        if key in body and body[key] is not None:
                            ids[f"body_{key}"] = body[key]
            except ValueError:
                pass  # request validation will produce 422
        elif "multipart/form-data" in request.headers.get("content-type", ""):
            form = await request.form()
            if form.get("machine_id"):
                ids["body_machine_id"] = form["machine_id"]
        for key, raw in ids.items():
            key = key.removeprefix("body_")
            if key not in {
                "workshop_id",
                "machine_id",
                "incident_id",
                "manual_id",
                "user_id",
                "created_by_user_id",
            }:
                continue
            try:
                value = int(raw)
            except (ValueError, TypeError):
                continue
            owner = None
            if key == "workshop_id":
                owner = value
            elif key == "machine_id":
                owner = await session.scalar(select(Machine.workshop_id).where(Machine.id == value))
            elif key in {"user_id", "created_by_user_id"}:
                owner = await session.scalar(select(User.workshop_id).where(User.id == value))
                if key == "user_id" and request.method in {"PATCH", "DELETE"} and value != user.id:
                    raise ForbiddenError("You may only change your own account")
            else:
                model = Incident if key == "incident_id" else Manual
                owner = await session.scalar(
                    select(Machine.workshop_id)
                    .join(model, model.machine_id == Machine.id)
                    .where(model.id == value)
                )
            if owner is not None and owner != user.workshop_id:
                raise NotFoundError("Resource not found")
        path = request.url.path
        if path == "/api/v1/workshops" or path == "/api/v1/users" and request.method == "POST":
            raise ForbiddenError("Use registration to create an account and workshop")
        if path == "/api/v1/incidents" and not any(key in ids for key in ("workshop_id", "machine_id")):
            raise ForbiddenError("A workshop or machine filter is required")
        if path.startswith("/api/v1/media/"):
            file_path = request.path_params.get("file_path")
            conditions = [
                select(Machine.workshop_id)
                .join(model, model.machine_id == Machine.id)
                .where(model.file_path == file_path)
                for model in (Manual, Baseline)
            ]
            conditions.append(
                select(Machine.workshop_id)
                .join(Incident, Incident.machine_id == Machine.id)
                .join(Attachment, Attachment.incident_id == Incident.id)
                .where(Attachment.file_path == file_path)
            )
            for statement in conditions:
                if await session.scalar(statement) == user.workshop_id:
                    return
            raise NotFoundError("File not found")
