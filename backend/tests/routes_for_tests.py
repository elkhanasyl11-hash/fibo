"""Extra endpoints mounted only in tests, to trigger each kind of error on purpose."""

from fastapi import FastAPI

from app.core.errors import NotFoundError


async def raise_not_found() -> None:
    raise NotFoundError("Machine 42 not found", details={"machine_id": 42})


async def needs_int(count: int) -> dict:
    return {"count": count}


async def crash() -> None:
    raise RuntimeError("secret internal detail that must not leak")


def install(app: FastAPI) -> None:
    app.add_api_route("/api/v1/_test/not-found", raise_not_found, methods=["GET"])
    app.add_api_route("/api/v1/_test/needs-int", needs_int, methods=["GET"])
    app.add_api_route("/api/v1/_test/crash", crash, methods=["GET"])
