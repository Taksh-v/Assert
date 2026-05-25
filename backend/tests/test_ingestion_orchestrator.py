import asyncio


def test_legacy_orchestrator_runs():
    from backend.ingestion.orchestrator import LegacyIngestionOrchestrator

    inst = LegacyIngestionOrchestrator()
    chunks = asyncio.run(inst.run("dummy source"))
    assert isinstance(chunks, list)
