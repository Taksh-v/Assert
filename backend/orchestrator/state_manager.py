import logging
from typing import Dict, Any, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.models.reasoning_execution import ReasoningExecution

logger = logging.getLogger(__name__)

class StateManager:
    """
    Persists and manages workflow state in Postgres using ReasoningExecution.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_execution(self, workspace_id: str, query: str, initial_state: Dict[str, Any]) -> str:
        execution = ReasoningExecution(
            workspace_id=workspace_id,
            query=query,
            status="running",
            state_snapshot=initial_state
        )
        self.db.add(execution)
        await self.db.commit()
        await self.db.refresh(execution)
        return execution.id

    async def update_state(self, execution_id: str, state_update: Dict[str, Any], status: Optional[str] = None):
        stmt = select(ReasoningExecution).where(ReasoningExecution.id == execution_id)
        result = await self.db.execute(stmt)
        execution = result.scalars().first()
        
        if not execution:
            raise ValueError(f"Execution {execution_id} not found")

        current_state = execution.state_snapshot or {}
        current_state.update(state_update)
        
        execution.state_snapshot = current_state
        if status:
            execution.status = status
            
        await self.db.commit()

    async def get_state(self, execution_id: str) -> Dict[str, Any]:
        stmt = select(ReasoningExecution).where(ReasoningExecution.id == execution_id)
        result = await self.db.execute(stmt)
        execution = result.scalars().first()
        return execution.state_snapshot if execution else {}
