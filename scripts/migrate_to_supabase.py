import asyncio
import os
import sys
from dotenv import load_dotenv

# Add backend directory to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from supabase import create_client, Client

from backend.core.database import async_session
from backend.models.user import User

load_dotenv()

async def migrate_users():
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") # We need service_role key to use admin API
    
    if not supabase_url or not supabase_key:
        print("❌ Error: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in .env")
        return
        
    supabase: Client = create_client(supabase_url, supabase_key)
    
    async with async_session() as session:
        # Find all users that don't have a supabase_id yet
        stmt = select(User).where(User.supabase_id == None)
        result = await session.execute(stmt)
        users = result.scalars().all()
        
        if not users:
            print("✅ No local users found that need migrating.")
            return
            
        print(f"Found {len(users)} users to migrate...")
        
        for user in users:
            print(f"Migrating {user.email}...")
            
            try:
                # 1. First check if they already exist in Supabase by email
                try:
                    # Admin API isn't fully robust in the python client for listing users by email
                    # A safer approach is to just try to create them, or invite them.
                    # Since we don't know their plain text password, we must auto-generate one
                    # or use admin API to create them.
                    
                    # Create user via admin API
                    temp_password = f"Temp_{os.urandom(8).hex()}!"
                    
                    response = supabase.auth.admin.create_user({
                        "email": user.email,
                        "password": temp_password,
                        "email_confirm": True,
                        "user_metadata": {"full_name": user.full_name}
                    })
                    
                    new_supabase_id = response.user.id
                    print(f"  → Created in Supabase with ID: {new_supabase_id}")
                    
                    # Update local database
                    user.supabase_id = new_supabase_id
                    user.hashed_password = None
                    await session.commit()
                    
                    print(f"  → Linked locally.")
                    print(f"  ⚠️ Note: User {user.email} must reset their password to log in, as their local bcrypt password could not be migrated.")
                    
                except Exception as e:
                    if "already registered" in str(e).lower() or "already exists" in str(e).lower():
                        print(f"  → User already exists in Supabase Auth. Will link on next login.")
                    else:
                        print(f"  ❌ Error migrating {user.email}: {e}")
            except Exception as e:
                print(f"  ❌ Failed processing {user.email}: {e}")
                
        print("Migration complete!")

if __name__ == "__main__":
    asyncio.run(migrate_users())
