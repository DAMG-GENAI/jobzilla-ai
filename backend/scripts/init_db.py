"""
Initialize Database Tables

Run this script to create all database tables.
"""

import asyncio
import os
import sys

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.database import create_tables
from app.db.models import Base


async def init_db():
    """Initialize the database with all tables."""
    print("🗄️  Initializing database...")
    print(f"   Database URL: {os.getenv('DATABASE_URL', 'postgresql://...')[:50]}...")

    try:
        await create_tables()
        print("✅ Database tables created successfully!")
        print()
        print("📋 Tables created:")
        for table in Base.metadata.tables:
            print(f"   - {table}")
    except Exception as e:
        print(f"❌ Error creating tables: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(init_db())
