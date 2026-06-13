import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete
from backend.core.database import init_db, async_session, close_db
from backend.models.user import User
from backend.core.security import get_password_hash
from backend.main import app

client = TestClient(app)

@pytest.mark.asyncio
async def test_email_check_endpoints():
    # Initialize the DB (calls metadata.create_all)
    await init_db()

    async with async_session() as session:
        # Clean up existing test data
        await session.execute(delete(User))
        await session.commit()

        # 1. Create a password user
        pwd_user = User(
            id="test-pwd-user-id",
            email="pwd@example.com",
            hashed_password=get_password_hash("password123"),
            full_name="Password User",
            is_active=True
        )
        session.add(pwd_user)
        await session.commit()

    try:
        # 2. Test check-email for nonexistent user
        response = client.post(
            "/api/users/check-email",
            json={"email": "nonexistent@example.com"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["exists"] is False
        assert data["auth_type"] == "none"

        # 3. Test check-email for password user
        response = client.post(
            "/api/users/check-email",
            json={"email": "pwd@example.com"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["exists"] is True
        assert data["auth_type"] == "password"

    finally:
        # Cleanup
        async with async_session() as session:
            await session.execute(delete(User))
            await session.commit()

        await close_db()
