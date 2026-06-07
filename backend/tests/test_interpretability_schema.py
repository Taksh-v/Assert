import pytest
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload
from datetime import datetime
from backend.core.database import init_db, close_db, async_session
from backend.models.user import User
from backend.models.workspace import Workspace
from backend.models.audit_ledger import AuditLedger
from backend.models.token_ledger import TokenLedger


@pytest.mark.asyncio
async def test_audit_and_token_ledger_schemas():
    # Initialize the DB (calls metadata.create_all)
    await init_db()

    async with async_session() as session:
        # Clear any existing test data to isolate the run
        await session.execute(delete(TokenLedger))
        await session.execute(delete(AuditLedger))
        await session.execute(delete(Workspace))
        await session.execute(delete(User))
        await session.commit()

        # 1. Create a dummy Workspace and User for Foreign Key mapping
        test_workspace = Workspace(
            id="test-ws-ledger-id",
            name="Ledger Test Workspace",
            slug="ledger-test-workspace"
        )
        test_user = User(
            id="test-user-ledger-id",
            email="ledger@test.com",
            hashed_password="hashed_password",
            full_name="Ledger Tester"
        )

        session.add(test_workspace)
        session.add(test_user)
        await session.commit()

        # 2. Add an AuditLedger record
        audit_record = AuditLedger(
            action_type="query",
            execution_tier="fast_rag",
            user_id=test_user.id,
            workspace_id=test_workspace.id,
            payload={"question": "What is the policy on database backups?", "results_count": 2},
            signature="test-cryptographic-signature"
        )
        session.add(audit_record)
        await session.commit()

        # Verify insertion and fields of AuditLedger
        assert audit_record.id is not None
        assert audit_record.timestamp is not None

        # 3. Add TokenLedger records associated with the AuditLedger record
        token_log_1 = TokenLedger(
            audit_id=audit_record.id,
            model_name="openai/gpt-4o",
            prompt_tokens=150,
            completion_tokens=45,
            cached_tokens=0,
            cost_usd=0.003
        )
        token_log_2 = TokenLedger(
            audit_id=audit_record.id,
            model_name="groq/llama-3.3-70b-versatile",
            prompt_tokens=500,
            completion_tokens=120,
            cached_tokens=1000,
            cost_usd=0.0005
        )
        session.add(token_log_1)
        session.add(token_log_2)
        await session.commit()

        # Verify insertion of TokenLedger
        assert token_log_1.id is not None
        assert token_log_2.id is not None

        # Close session and start a new one to force db query roundtrip
        # and ensure everything was properly committed and is retrieved fresh
        pass

    async with async_session() as session:
        # 4. Query AuditLedger and verify relationships eagerly using selectinload
        stmt = (
            select(AuditLedger)
            .where(AuditLedger.id == audit_record.id)
            .options(
                selectinload(AuditLedger.workspace),
                selectinload(AuditLedger.user),
                selectinload(AuditLedger.tokens)
            )
        )
        res = await session.execute(stmt)
        queried_audit = res.scalar_one()

        assert queried_audit.action_type == "query"
        assert queried_audit.execution_tier == "fast_rag"
        assert queried_audit.payload["question"] == "What is the policy on database backups?"
        assert queried_audit.signature == "test-cryptographic-signature"

        # Check relationships
        assert queried_audit.workspace.name == "Ledger Test Workspace"
        assert queried_audit.user.email == "ledger@test.com"
        assert len(queried_audit.tokens) == 2

        # Check token ledger fields
        token_models = {t.model_name for t in queried_audit.tokens}
        assert "openai/gpt-4o" in token_models
        assert "groq/llama-3.3-70b-versatile" in token_models

        gpt4_token_log = next(t for t in queried_audit.tokens if t.model_name == "openai/gpt-4o")
        assert gpt4_token_log.prompt_tokens == 150
        assert gpt4_token_log.completion_tokens == 45
        assert gpt4_token_log.cost_usd == 0.003

        # Clean up database tables
        await session.execute(delete(TokenLedger))
        await session.execute(delete(AuditLedger))
        await session.execute(delete(Workspace))
        await session.execute(delete(User))
        await session.commit()

    await close_db()
