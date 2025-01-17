import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timedelta
from fastapi import HTTPException
from google.oauth2.credentials import Credentials

from example_agents_project.credentials import (
    store_user_credentials,
    has_user_credentials,
    get_user_credentials,
    get_auth_url,
    get_access_token,
    refresh_access_token,
    revoke_credentials,
)


@pytest.mark.asyncio
@patch("example_agents_project.credentials.store_user_token", new_callable=AsyncMock)
async def test_store_user_credentials(mock_store):
    test_data = {"test": "data"}
    await store_user_credentials("test_user", test_data)
    mock_store.assert_called_once_with("test_user", test_data)


@pytest.mark.asyncio
@patch("example_agents_project.credentials.has_user_token", new_callable=AsyncMock)
async def test_has_user_credentials(mock_has):
    mock_has.return_value = True
    result = await has_user_credentials("test_user")
    assert result is True
    mock_has.assert_called_once_with("test_user")


@pytest.mark.asyncio
@patch("example_agents_project.credentials.get_user_token", new_callable=AsyncMock)
async def test_get_user_credentials_valid(mock_get):
    future_time = datetime.now() + timedelta(hours=1)
    mock_get.return_value = {
        "access_token": "test_token",
        "refresh_token": "test_refresh",
        "expires_at": future_time,
        "scopes": ["test_scope"],
    }

    result = await get_user_credentials("test_user")
    assert isinstance(result, Credentials)
    assert result.token == "test_token"
    mock_get.assert_called_once_with("test_user")


@pytest.mark.asyncio
@patch(
    "example_agents_project.credentials.refresh_access_token", new_callable=AsyncMock
)
@patch("example_agents_project.credentials.get_user_token", new_callable=AsyncMock)
async def test_get_user_credentials_expired(mock_get, mock_refresh):
    past_time = datetime.now() - timedelta(hours=1)
    future_time = datetime.now() + timedelta(hours=1)

    # First call returns expired token, second call returns refreshed token
    mock_get.side_effect = [
        {
            "access_token": "old_token",
            "refresh_token": "test_refresh",
            "expires_at": past_time,
            "scopes": ["test_scope"],
        },
        {
            "access_token": "new_token",
            "refresh_token": "test_refresh",
            "expires_at": future_time,
            "scopes": ["test_scope"],
        },
    ]

    # Mock the refresh token call
    mock_refresh.return_value = {
        "access_token": "new_token",
        "refresh_token": "test_refresh",
        "expires_in": 3600,
    }

    result = await get_user_credentials("test_user")
    assert isinstance(result, Credentials)
    assert result.token == "new_token"
    assert mock_get.call_count == 2
    mock_refresh.assert_called_once_with("test_user", "test_refresh")


def test_get_auth_url():
    url = get_auth_url("test_user", "test_channel", "test_thread")
    assert "accounts.google.com" in url
    assert "client_id=" in url
    assert "redirect_uri=" in url
    assert "test_user,test_channel,test_thread" in url


@pytest.mark.asyncio
@patch("example_agents_project.credentials.httpx.AsyncClient")
async def test_get_access_token_success(mock_client):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "access_token": "new_token",
        "refresh_token": "refresh_token",
        "expires_in": 3600,
    }
    mock_client.return_value.__aenter__.return_value.post.return_value = mock_response

    result = await get_access_token("test_code")
    assert result == {
        "access_token": "new_token",
        "refresh_token": "refresh_token",
        "expires_in": 3600,
    }


@pytest.mark.asyncio
@patch("example_agents_project.credentials.httpx.AsyncClient")
async def test_get_access_token_failure(mock_client):
    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_response.json.return_value = {"error": "invalid_grant"}
    mock_client.return_value.__aenter__.return_value.post.return_value = mock_response

    with pytest.raises(HTTPException):
        await get_access_token("invalid_code")


@pytest.mark.asyncio
@patch(
    "example_agents_project.credentials.cache.set_user_token", new_callable=AsyncMock
)
@patch("example_agents_project.credentials.update_user_token", new_callable=AsyncMock)
@patch("example_agents_project.credentials.httpx.AsyncClient")
async def test_refresh_access_token_success(mock_client, mock_update, mock_cache):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "access_token": "new_token",
        "refresh_token": "refresh_token",
        "expires_in": 3600,
    }
    mock_client.return_value.__aenter__.return_value.post.return_value = mock_response

    result = await refresh_access_token("test_user", "test_refresh_token")
    assert result == {
        "access_token": "new_token",
        "refresh_token": "refresh_token",
        "expires_in": 3600,
    }
    mock_update.assert_called_once()
    mock_cache.assert_called_once()


@pytest.mark.asyncio
@patch("example_agents_project.credentials.httpx.AsyncClient")
async def test_refresh_access_token_failure(mock_client):
    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_response.json.return_value = {"error": "invalid_grant"}
    mock_client.return_value.__aenter__.return_value.post.return_value = mock_response

    with pytest.raises(HTTPException):
        await refresh_access_token("test_user", "invalid_refresh_token")


@pytest.mark.asyncio
@patch("example_agents_project.credentials.delete_user_token", new_callable=AsyncMock)
@patch("example_agents_project.credentials.get_user_token", new_callable=AsyncMock)
@patch("example_agents_project.credentials.httpx.AsyncClient")
async def test_revoke_credentials_success(mock_client, mock_get, mock_delete):
    future_time = datetime.now() + timedelta(hours=1)
    mock_get.return_value = {
        "access_token": "test_token",
        "refresh_token": "test_refresh",
        "expires_at": future_time,
    }

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_client.return_value.__aenter__.return_value.post.return_value = mock_response

    await revoke_credentials("test_user")
    mock_delete.assert_called_once_with("test_user")


@pytest.mark.asyncio
@patch("example_agents_project.credentials.get_user_token", new_callable=AsyncMock)
@patch("example_agents_project.credentials.httpx.AsyncClient")
async def test_revoke_credentials_failure(mock_client, mock_get):
    future_time = datetime.now() + timedelta(hours=1)
    mock_get.return_value = {
        "access_token": "test_token",
        "refresh_token": "test_refresh",
        "expires_at": future_time,
    }

    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_client.return_value.__aenter__.return_value.post.return_value = mock_response

    with pytest.raises(HTTPException):
        await revoke_credentials("test_user")
