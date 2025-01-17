import pytest
from unittest.mock import AsyncMock, patch
from example_agents_project.db import (
    create_database_if_not_exists,
    init_db,
    store_user_token,
    update_user_token,
    has_user_token,
    get_user_token,
    delete_user_token,
    UserToken,
    DB_NAME,
    QUERY_DBS,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import text


@pytest.mark.asyncio
@patch("example_agents_project.db.create_async_engine")
@patch("example_agents_project.db.AsyncSessionLocal")
async def test_create_database_if_not_exists(
    mock_async_session_local, mock_create_async_engine
):
    """Test database creation if it does not exist."""
    mock_conn = AsyncMock()
    mock_result = AsyncMock()
    mock_result.fetchone.return_value = None  # Simulate database not existing

    mock_conn.execute = AsyncMock(return_value=mock_result)
    mock_create_async_engine.return_value.connect.return_value.__aenter__.return_value = (
        mock_conn
    )

    await create_database_if_not_exists()

    execute_call = mock_conn.execute.call_args[0]
    assert str(execute_call[0]) == QUERY_DBS
    assert execute_call[1] == {"dbname": DB_NAME}
    mock_result.fetchone.assert_called_once()


@pytest.mark.asyncio
@patch("example_agents_project.db.create_database_if_not_exists")
@patch("example_agents_project.db.AsyncSessionLocal")
async def test_init_db(mock_async_session_local, mock_create_database_if_not_exists):
    """Test database initialization."""
    await init_db()
    mock_create_database_if_not_exists.assert_called_once()


@pytest.mark.asyncio
@patch("example_agents_project.db.AsyncSessionLocal")
async def test_store_user_token(mock_async_session_local):
    """Test storing a user token."""
    mock_session = AsyncMock()
    mock_session.add = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_async_session_local.return_value.__aenter__.return_value = mock_session

    user_id = "user123"
    data = {
        "access_token": "access_token_value",
        "refresh_token": "refresh_token_value",
        "expires_in": 3600,
        "scope": "scope_value",
    }

    await store_user_token(user_id, data)

    # Get the UserToken object that was passed to add
    token = mock_session.add.call_args[0][0]
    assert isinstance(token, UserToken)
    assert token.user_id == user_id
    assert token.access_token == data["access_token"]
    mock_session.add.assert_called_once()
    mock_session.commit.assert_called_once()


@pytest.mark.asyncio
@patch("example_agents_project.db.AsyncSessionLocal")
async def test_update_user_token(mock_async_session_local):
    """Test updating a user token."""
    mock_session = AsyncMock()
    mock_session.get = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_async_session_local.return_value.__aenter__.return_value = mock_session

    user_id = "user123"
    data = {
        "access_token": "new_access_token",
        "expires_in": 3600,
        "scope": "new_scope",
    }

    mock_token = UserToken(
        user_id=user_id,
        access_token="old_token",
        refresh_token="old_refresh",
        expires_at=None,
        scopes="old_scope",
    )
    mock_session.get.return_value = mock_token

    await update_user_token(user_id, data)

    mock_session.get.assert_called_once()
    mock_session.commit.assert_called_once()
    assert mock_token.access_token == data["access_token"]
    assert mock_token.scopes == data["scope"]


@pytest.mark.asyncio
@patch("example_agents_project.db.AsyncSessionLocal")
async def test_has_user_token(mock_async_session_local):
    """Test checking if a user token exists."""
    mock_session = AsyncMock()
    mock_session.get = AsyncMock()
    mock_async_session_local.return_value.__aenter__.return_value = mock_session

    user_id = "user123"
    mock_token = UserToken(
        user_id=user_id,
        access_token="token",
        refresh_token="refresh",
        expires_at=None,
        scopes="scope",
    )
    mock_session.get.return_value = mock_token

    result = await has_user_token(user_id)

    mock_session.get.assert_called_once()
    assert result is True


@pytest.mark.asyncio
@patch("example_agents_project.db.AsyncSessionLocal")
async def test_get_user_token(mock_async_session_local):
    """Test retrieving a user token."""
    mock_session = AsyncMock()
    mock_async_session_local.return_value.__aenter__.return_value = mock_session

    user_id = "user123"
    mock_session.get.return_value = UserToken(
        user_id=user_id,
        access_token="token",
        refresh_token="refresh",
        expires_at=None,
        scopes="scope",
    )

    result = await get_user_token(user_id)

    assert result["access_token"] == "token"
    assert result["scopes"] == ["scope"]


@pytest.mark.asyncio
@patch("example_agents_project.db.AsyncSessionLocal")
async def test_delete_user_token(mock_async_session_local):
    """Test deleting a user token."""
    mock_session = AsyncMock()
    mock_async_session_local.return_value.__aenter__.return_value = mock_session

    user_id = "user123"
    mock_session.get.return_value = UserToken(
        user_id=user_id,
        access_token="token",
        refresh_token="refresh",
        expires_at=None,
        scopes="scope",
    )

    await delete_user_token(user_id)

    mock_session.delete.assert_called_once()


@pytest.mark.asyncio
@patch("example_agents_project.db.AsyncSessionLocal")
async def test_has_user_token_false(mock_async_session_local):
    """Test checking if a user token does not exist."""
    mock_session = AsyncMock()
    mock_async_session_local.return_value.__aenter__.return_value = mock_session

    user_id = "user123"
    mock_session.get.return_value = None  # Simulate token not found

    result = await has_user_token(user_id)

    assert result is False


@pytest.mark.asyncio
@patch("example_agents_project.db.AsyncSessionLocal")
async def test_get_user_token_not_found(mock_async_session_local):
    """Test retrieving a user token that does not exist."""
    mock_session = AsyncMock()
    mock_async_session_local.return_value.__aenter__.return_value = mock_session

    user_id = "user123"
    mock_session.get.return_value = None  # Simulate token not found

    with pytest.raises(Exception, match="Tokens not found"):
        await get_user_token(user_id)


@pytest.mark.asyncio
@patch("example_agents_project.db.AsyncSessionLocal")
async def test_delete_user_token_not_found(mock_async_session_local):
    """Test deleting a user token that does not exist."""
    mock_session = AsyncMock()
    mock_async_session_local.return_value.__aenter__.return_value = mock_session

    user_id = "user123"
    mock_session.get.return_value = None  # Simulate token not found

    await delete_user_token(user_id)

    mock_session.delete.assert_not_called()  # Ensure delete was not called
