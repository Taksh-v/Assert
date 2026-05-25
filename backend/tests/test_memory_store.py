import asyncio

from backend.memory.store import InMemoryMemoryStore


async def test_snapshot_and_restore():
    s1 = InMemoryMemoryStore()
    await s1.set("a", 1)
    await s1.set("b", {"x": 2})

    snap = await s1.snapshot()

    s2 = InMemoryMemoryStore()
    await s2.restore(snap)

    assert await s2.get("a") == 1
    assert await s2.get("b") == {"x": 2}

    await s1.close()
    await s2.close()
