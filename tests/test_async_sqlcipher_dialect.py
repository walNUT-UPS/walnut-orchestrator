import pytest
import asyncio
from typing import AsyncGenerator

from sqlalchemy import (
    Column,
    Integer,
    String,
    select,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
    async_sessionmaker,
)
from sqlalchemy.orm import declarative_base

# Import the dialect to ensure it's registered
from walnut.database import sqlcipher_dialect

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    name = Column(String)
    fullname = Column(String)
    nickname = Column(String)

    def __repr__(self):
        return f"<User(id={self.id}, name='{self.name}', fullname='{self.fullname}', nickname='{self.nickname}')>"


@pytest.fixture
async def async_sqlcipher_engine():
    """Fixture for an in-memory async SQLCipher engine."""
    # A secure, memorable key for testing purposes
    key = "test_key_that_is_long_enough_for_aes_256"

    # Use the custom dialect with an in-memory database
    engine = create_async_engine(
        f"sqlite+sqlcipher:///:memory:?key={key}",
        echo=False, # Set to True for debugging SQL
    )

    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Dispose of the engine
    await engine.dispose()


@pytest.fixture
async def async_sqlcipher_session(async_sqlcipher_engine) -> AsyncGenerator[AsyncSession, None]:
    """Fixture for a session with the async SQLCipher engine."""
    session_factory = async_sessionmaker(async_sqlcipher_engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session


@pytest.mark.asyncio
async def test_async_dialect_connection(async_sqlcipher_session: AsyncSession):
    """Test that we can connect to the encrypted database."""
    assert async_sqlcipher_session.is_active

    # Check if the dialect is our custom one
    assert async_sqlcipher_session.bind.dialect.name == "sqlite"
    assert async_sqlcipher_session.bind.dialect.driver == "sqlcipher"


@pytest.mark.asyncio
async def test_async_dialect_crud_operations(async_sqlcipher_session: AsyncSession):
    """Test basic CRUD operations using the async dialect."""
    session = async_sqlcipher_session

    # 1. Create
    new_user = User(name="john_doe", fullname="John Doe", nickname="Johnny")
    session.add(new_user)
    await session.commit()
    await session.refresh(new_user)

    assert new_user.id is not None
    assert new_user.name == "john_doe"

    # 2. Read
    stmt = select(User).where(User.name == "john_doe")
    result = await session.execute(stmt)
    user_from_db = result.scalar_one_or_none()

    assert user_from_db is not None
    assert user_from_db.id == new_user.id
    assert user_from_db.fullname == "John Doe"

    # 3. Update
    user_from_db.nickname = "JD"
    await session.commit()
    await session.refresh(user_from_db)

    assert user_from_db.nickname == "JD"

    # Verify the update
    stmt_updated = select(User).where(User.id == user_from_db.id)
    result_updated = await session.execute(stmt_updated)
    user_updated = result_updated.scalar_one()

    assert user_updated.nickname == "JD"

    # 4. Delete
    await session.delete(user_updated)
    await session.commit()

    # Verify deletion
    stmt_deleted = select(User).where(User.id == user_from_db.id)
    result_deleted = await session.execute(stmt_deleted)
    user_deleted = result_deleted.scalar_one_or_none()

    assert user_deleted is None


@pytest.mark.asyncio
async def test_add_multiple_users(async_sqlcipher_session: AsyncSession):
    """Test adding multiple users in a single transaction."""
    session = async_sqlcipher_session

    users_to_add = [
        User(name="jane_doe", fullname="Jane Doe", nickname="Janey"),
        User(name="peter_pan", fullname="Peter Pan", nickname="Pete"),
    ]

    session.add_all(users_to_add)
    await session.commit()

    # Verify that both users were added
    stmt = select(User).order_by(User.name)
    result = await session.execute(stmt)
    all_users = result.scalars().all()

    assert len(all_users) == 2
    assert all_users[0].name == "jane_doe"
    assert all_users[1].name == "peter_pan"
