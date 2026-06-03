from typing import Dict, Any, Protocol, runtime_checkable

@runtime_checkable
class ToolProtocol(Protocol):
    name: str
    def run(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        ...

@runtime_checkable
class AgentProtocol(Protocol):
    def handle(self, inputs: Dict[str, Any], tools: Dict[str, ToolProtocol]) -> Dict[str, Any]:
        ...
