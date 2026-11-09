"""Bot manual upload helpers."""

from bot.handlers.manuals import wait_until_indexed


class FakeApi:
    def __init__(self, statuses):
        self.statuses, self.calls = statuses, 0

    async def get_manual(self, manual_id):
        status = self.statuses[min(self.calls, len(self.statuses) - 1)]
        self.calls += 1
        return {"id": manual_id, "index_status": status, "page_count": 12}


async def _no_sleep(_seconds):
    return None


async def test_waits_until_ready():
    result = await wait_until_indexed(FakeApi(["pending", "indexing", "ready"]), 1, sleep=_no_sleep)
    assert result["index_status"] == "ready"


async def test_gives_up_when_stuck():
    assert await wait_until_indexed(FakeApi(["indexing"]), 1, sleep=_no_sleep) is None
