
import asyncio
import logging
from datetime import datetime
from backend.core.database import async_session, init_db
from backend.core.security import get_password_hash
from backend.models.user import User
from backend.models.workspace import Workspace
from backend.models.workspace_member import WorkspaceMember, WorkspaceRole
from sqlalchemy import select

from sqlalchemy.pool import NullPool

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def create_admin():
    logger.info("🛠 Checking for admin user...")
    # Use a separate engine for provisioning to ensure pool isolation
    from backend.core.database import db_url, _connect_args
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    
    prov_engine = create_async_engine(
        db_url, 
        connect_args=_connect_args,
        poolclass=NullPool
    )
    
    # We still use the shared Base/models, but a dedicated engine/session for this script
    ProvSession = sessionmaker(prov_engine, class_=AsyncSession, expire_on_commit=False)
    
    # Ensure tables exist
    from backend.core.database import Base
    async with prov_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    email = "admin@assest.ai"
    password = "admin-password"
    
    async with ProvSession() as session:
        # 1. Check if admin exists
        stmt = select(User).where(User.email == email)
        result = await session.execute(stmt)
        admin = result.scalars().first()
        
        if admin:
            logger.info("✅ Admin user already exists.")
            return

        logger.info(f"👤 Creating admin user: {email}")
        admin = User(
            email=email,
            hashed_password=get_password_hash(password),
            full_name="Admin",
            is_active=True,
            is_superuser=True
        )
        session.add(admin)
        await session.flush()
        
        # 2. Check for default workspace
        stmt = select(Workspace).where(Workspace.slug == "default-workspace")
        result = await session.execute(stmt)
        workspace = result.scalars().first()
        
        if not workspace:
            logger.info("🏢 Creating default workspace...")
            workspace = Workspace(
                name="Default Workspace",
                slug="default-workspace"
            )
            session.add(workspace)
            await session.flush()
        
        # 3. Add admin to workspace as OWNER
        stmt = select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace.id,
            WorkspaceMember.user_id == admin.id
        )
        result = await session.execute(stmt)
        membership = result.scalars().first()
        
        if not membership:
            logger.info("🔗 Adding admin to default workspace...")
            membership = WorkspaceMember(
                workspace_id=workspace.id,
                user_id=admin.id,
                role=WorkspaceRole.OWNER
            )
            session.add(membership)
        
        # 4. Seed demo connectors
        from backend.models.connector import Connector, ConnectorType, ConnectorStatus
        connectors_to_add = [
            {
                "type": ConnectorType.NOTION,
                "config": {"mock": True, "workspace_name": "Demo Notion"},
                "status": ConnectorStatus.ACTIVE
            },
            {
                "type": ConnectorType.GOOGLE_DRIVE,
                "config": {"mock": True, "folder_id": "root"},
                "status": ConnectorStatus.ACTIVE
            },
            {
                "type": ConnectorType.SLACK,
                "config": {"mock": True, "channels": ["general"]},
                "status": ConnectorStatus.ACTIVE
            }
        ]

        for c_data in connectors_to_add:
            stmt = select(Connector).where(
                Connector.workspace_id == workspace.id,
                Connector.type == c_data["type"]
            )
            res = await session.execute(stmt)
            if not res.scalars().first():
                logger.info(f"🔌 Adding {c_data['type']} connector...")
                connector = Connector(
                    workspace_id=workspace.id,
                    type=c_data["type"],
                    config=c_data["config"],
                    status=c_data["status"],
                    last_synced_at=datetime.utcnow()
                )
                session.add(connector)
        
        await session.commit()
        logger.info("🚀 Admin user and workspace setup complete.")

if __name__ == "__main__":
    asyncio.run(create_admin())
