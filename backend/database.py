from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text
from config import get_settings

settings = get_settings()

engine = create_async_engine(settings.database_url, echo=False)
async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    # Import models to ensure they're registered with Base.metadata
    import models  # noqa: F401

    print(f"Initializing database with tables: {list(Base.metadata.tables.keys())}")

    # Enable pgvector extension
    async with engine.begin() as conn:
        try:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            print("pgvector extension enabled")
        except Exception as e:
            print(f"pgvector extension warning: {e}")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        print("Database tables created successfully")

    # Run migrations in separate transactions
    migrations = [
        ("jira_configs", "gitlab_url", "VARCHAR(512)"),
        ("jira_configs", "gitlab_token", "TEXT"),
        ("jira_projects", "gitlab_projects", "TEXT"),
        ("jira_projects", "custom_instructions", "TEXT"),
        ("jira_projects", "embeddings_enabled", "BOOLEAN DEFAULT FALSE"),
    ]
    for table, column, col_type in migrations:
        try:
            async with engine.begin() as conn:
                await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
                print(f"Migration: Added column {column} to {table}")
        except Exception as e:
            error_str = str(e).lower()
            if "already exists" in error_str or "duplicate column" in error_str:
                pass  # Column already exists, that's fine
            else:
                print(f"Migration warning for {table}.{column}: {e}")
