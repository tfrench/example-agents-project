import os
from datetime import datetime, timedelta
from cryptography.fernet import Fernet
from dotenv import load_dotenv
from sqlalchemy import Column, String, Text, text, TIMESTAMP
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
import logging

load_dotenv()

_logger = logging.getLogger(__name__)

DB_HOST = os.getenv("DB_HOST")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")

if not all([DB_HOST, DB_NAME, DB_USER, DB_PASSWORD, ENCRYPTION_KEY]):
    raise ValueError("One or more required environment variables are missing.")

fernet = Fernet(ENCRYPTION_KEY)

DATABASE_URL = f"postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}/{DB_NAME}"
_logger.info(f"Database URL: {DATABASE_URL}")

async_engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
)
Base = declarative_base()


class NoCredentialsFound(Exception):
    pass


class UserToken(Base):
    __tablename__ = "user_tokens"

    user_id = Column(String, primary_key=True, index=True)
    access_token = Column(Text, nullable=False)
    refresh_token = Column(Text, nullable=False)
    expires_at = Column(TIMESTAMP, nullable=False)
    scopes = Column(Text, nullable=False)


async def create_database_if_not_exists():
    """Creates the database if it doesn't exist."""
    db_url_without_dbname = (
        f"postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}/postgres"
    )
    async_engine_without_dbname = create_async_engine(db_url_without_dbname, echo=False)

    async with async_engine_without_dbname.connect() as conn:
        await conn.execution_options(isolation_level="AUTOCOMMIT")
        result = await conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :dbname"),
            {"dbname": DB_NAME},
        )
        if not result.fetchone():
            await conn.execute(text(f"CREATE DATABASE {DB_NAME}"))
            _logger.info(f"Database '{DB_NAME}' created successfully.")


async def init_db():
    """Initializes the PostgreSQL database with the required table."""
    await create_database_if_not_exists()  # Ensure the database exists
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def store_user_token(user_id: str, data: dict):
    """Stores (add/update) the user's tokens."""
    _logger.info(f"Storing user token for user {user_id}: {data}")
    expires_at = datetime.now() + timedelta(seconds=data["expires_in"])

    encrypted_access_token = fernet.encrypt(data["access_token"].encode()).decode()
    encrypted_refresh_token = fernet.encrypt(data["refresh_token"].encode()).decode()

    async with AsyncSessionLocal() as session:
        token = UserToken(
            user_id=user_id,
            access_token=encrypted_access_token,
            refresh_token=encrypted_refresh_token,
            expires_at=expires_at,
            scopes=data["scope"],
        )
        session.add(token)
        await session.commit()


async def update_user_token(user_id: str, data: dict):
    """Stores (add/update) the user's tokens."""
    _logger.info(f"Storing user token for user {user_id}: {data}")
    expires_at = datetime.now() + timedelta(seconds=data["expires_in"])

    encrypted_access_token = fernet.encrypt(data["access_token"].encode()).decode()

    async with AsyncSessionLocal() as session:
        token = await session.get(UserToken, user_id)
        token.access_token = encrypted_access_token  # no refresh token
        token.expires_at = expires_at
        token.scopes = data["scope"]
        await session.commit()


async def has_user_token(user_id: str) -> bool:
    async with AsyncSessionLocal() as session:
        token = await session.get(UserToken, user_id)
        return token is not None


async def get_user_token(user_id: str) -> dict:
    """Retrieves the stored credentials for a given user."""
    async with AsyncSessionLocal() as session:
        token = await session.get(UserToken, user_id)
        if not token:
            raise NoCredentialsFound("Tokens not found")

        access_token = fernet.decrypt(token.access_token.encode()).decode()
        refresh_token = fernet.decrypt(token.refresh_token.encode()).decode()

        return dict(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=token.expires_at,
            scopes=token.scopes.split(","),
        )


async def delete_user_token(user_id: str):
    """Deletes the stored tokens for a given user."""
    async with AsyncSessionLocal() as session:
        token = await session.get(UserToken, user_id)
        if token:
            await session.delete(token)
            await session.commit()
