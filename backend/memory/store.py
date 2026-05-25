import asyncio
from typing import Protocol, Any, Dict, runtime_checkable, Optional


@runtime_checkable
class MemoryStore(Protocol):
    """Protocol for an in-memory snapshotable store."""

    name: str

    async def set(self, key: str, value: Any) -> None:
        ...

    async def get(self, key: str) -> Optional[Any]:
        ...

    async def delete(self, key: str) -> None:
        ...

    async def snapshot(self) -> Dict[str, Any]:
        """Return a serializable snapshot of the store."""

    async def restore(self, snapshot: Dict[str, Any]) -> None:
        """Restore store state from a snapshot."""

    async def close(self) -> None:
        ...


class InMemoryMemoryStore:
    """Simple async-friendly in-memory MemoryStore used for tests and local runs."""

    name = "inmemory"

    def __init__(self) -> None:
        self._data: Dict[str, Any] = {}
        self._lock = asyncio.Lock()

    async def set(self, key: str, value: Any) -> None:
        async with self._lock:
            self._data[key] = value

    async def get(self, key: str):
        async with self._lock:
            return self._data.get(key)

    async def delete(self, key: str) -> None:
        async with self._lock:
            self._data.pop(key, None)

    async def snapshot(self) -> Dict[str, Any]:
        async with self._lock:
            # shallow copy is fine for small test data
            return dict(self._data)

    async def restore(self, snapshot: Dict[str, Any]) -> None:
        async with self._lock:
            self._data = dict(snapshot)

    async def close(self) -> None:
        async with self._lock:
            self._data.clear()
