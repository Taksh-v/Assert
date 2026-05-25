import asyncio

from backend.ingestion.runner import IngestionRunner
from backend.memory.store import InMemoryMemoryStore


class SimpleTemplate:
    def __init__(self):
        self.transformers = []


async def test_runner_writes_memory_state():
    mem = InMemoryMemoryStore()
    runner = IngestionRunner(document_store=None, index_adapter=None, templates=None, default_template=SimpleTemplate(), memory_store=mem)

    class RawDoc:
        source_url = "file.txt"

    raw = RawDoc()
    # run the process
    await runner.process(raw, "ws1")

    state = await mem.get("package:ws1::state")
    # title may be empty string; ensure there is a key with ws1 and 'persisted' somewhere
    snap = await mem.snapshot()
    # find any key that starts with package:ws1 and verify persisted
    found = False
    for k, v in snap.items():
        if k.startswith("package:ws1:") and v == "persisted":
            found = True
            break

    assert found, f"expected persisted state in memory snapshot, got {snap}"
    await mem.close()
