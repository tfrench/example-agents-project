import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch
from aipolabs_test.api import app
from fastapi import status


@pytest_asyncio.fixture
async def test_client():
    """Fixture for creating an async test client."""
    transport = ASGITransport(app=app)  # Create ASGI transport for FastAPI app
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_health_check(test_client):
    """Test /health endpoint."""
    response = await test_client.get("/health")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
@patch("aipolabs_test.api.send_slack_message", new_callable=AsyncMock)
@patch("aipolabs_test.api.BackgroundTasks")
async def test_slack_events_hello(
    mock_background_tasks, mock_send_slack_message, test_client
):
    """Test /slack/events endpoint with 'hello' message."""

    mock_background_tasks.return_value.add_task = lambda func, *args, **kwargs: func(
        *args, **kwargs
    )

    payload = {
        "type": "event_callback",
        "event": {
            "type": "message",
            "user": "user123",
            "channel": "channel456",
            "text": "hello",
            "thread_ts": "1234567890.123456",
        },
    }

    response = await test_client.post(
        "/slack/events", json=payload, headers={"Content-Type": "application/json"}
    )

    assert response.status_code == status.HTTP_200_OK
    mock_send_slack_message.assert_called_once_with(
        "Hello! I'm here to help!\n"
        "First you need to authenticate (message: `auth`).\n"
        "You can check your authentication status (message: `status`).\n"
        "Then I can help manage your emails (read; send; draft) (message: `chat`).\n"
        "Finally, you can revoke credentials (message: `revoke`).\n",
        "channel456",
        "1234567890.123456",
    )


@pytest.mark.asyncio
@patch("aipolabs_test.api.has_user_token", return_value=False)
@patch("aipolabs_test.api.get_auth_url", return_value="http://auth.url")
@patch("aipolabs_test.api.send_slack_message", new_callable=AsyncMock)
@patch("aipolabs_test.api.BackgroundTasks")
async def test_slack_events_auth(
    mock_background_tasks,
    mock_send_message,
    mock_get_auth_url,
    mock_has_token,
    test_client,
):
    """Test /slack/events endpoint with 'auth' message."""
    payload = {
        "type": "event_callback",
        "event": {
            "type": "message",
            "user": "user123",
            "channel": "channel456",
            "text": "auth",
            "thread_ts": "1234567890.123456",
        },
    }

    mock_background_tasks.return_value.add_task = lambda func, *args, **kwargs: func(
        *args, **kwargs
    )

    response = await test_client.post(
        "/slack/events", json=payload, headers={"Content-Type": "application/json"}
    )

    assert response.status_code == status.HTTP_200_OK
    mock_send_message.assert_called_once_with(
        "Please click <http://auth.url|here> to authenticate with Google.",
        "channel456",
        "1234567890.123456",
    )
    mock_get_auth_url.assert_called_once_with(
        "user123", "channel456", "1234567890.123456"
    )


@pytest.mark.asyncio
@patch("aipolabs_test.api.has_user_token", return_value=True)
@patch("aipolabs_test.api.send_slack_message", new_callable=AsyncMock)
@patch("aipolabs_test.api.BackgroundTasks")
async def test_slack_events_status(
    mock_background_tasks, mock_send_message, mock_has_token, test_client
):
    """Test /slack/events endpoint with 'status' message."""
    payload = {
        "type": "event_callback",
        "event": {
            "type": "message",
            "user": "user123",
            "channel": "channel456",
            "text": "status",
            "thread_ts": "1234567890.123456",
        },
    }

    response = await test_client.post(
        "/slack/events", json=payload, headers={"Content-Type": "application/json"}
    )

    assert response.status_code == status.HTTP_200_OK
    mock_send_message.assert_called_once_with(
        "You have existing credentials.\nYou can use `chat` to send messages.",
        "channel456",
        "1234567890.123456",
    )


@pytest.mark.asyncio
@patch("aipolabs_test.api.has_user_token", return_value=True)
@patch("aipolabs_test.api.revoke_user_token", new_callable=AsyncMock)
@patch("aipolabs_test.api.send_slack_message", new_callable=AsyncMock)
@patch("aipolabs_test.api.BackgroundTasks")
async def test_slack_events_revoke_with_credentials(
    mock_background_tasks,
    mock_send_message,
    mock_revoke_token,
    mock_has_token,
    test_client,
):
    """Test /slack/events endpoint with 'revoke' message when credentials exist."""
    payload = {
        "type": "event_callback",
        "event": {
            "type": "message",
            "user": "user123",
            "channel": "channel456",
            "text": "revoke",
            "thread_ts": "1234567890.123456",
        },
    }

    response = await test_client.post(
        "/slack/events", json=payload, headers={"Content-Type": "application/json"}
    )

    assert response.status_code == status.HTTP_200_OK
    mock_revoke_token.assert_called_once_with("user123")
    mock_send_message.assert_called_once_with(
        "Credentials revoked successfully.",
        "channel456",
        "1234567890.123456",
    )


@pytest.mark.asyncio
@patch("aipolabs_test.api.has_user_token", return_value=False)
@patch("aipolabs_test.api.send_slack_message", new_callable=AsyncMock)
@patch("aipolabs_test.api.BackgroundTasks")
async def test_slack_events_revoke_without_credentials(
    mock_background_tasks, mock_send_message, mock_has_token, test_client
):
    """Test /slack/events endpoint with 'revoke' message when no credentials exist."""
    payload = {
        "type": "event_callback",
        "event": {
            "type": "message",
            "user": "user123",
            "channel": "channel456",
            "text": "revoke",
            "thread_ts": "1234567890.123456",
        },
    }

    response = await test_client.post(
        "/slack/events", json=payload, headers={"Content-Type": "application/json"}
    )

    assert response.status_code == status.HTTP_200_OK
    mock_send_message.assert_called_once_with(
        "You don't have existing credentials. Use `auth` to authenticate.",
        "channel456",
        "1234567890.123456",
    )


@pytest.mark.asyncio
@patch(
    "aipolabs_test.api.get_user_token",
    return_value={"access_token": "fake_token"},
)
@patch("aipolabs_test.api.handle_message", new_callable=AsyncMock)
@patch("aipolabs_test.api.send_slack_message", new_callable=AsyncMock)
@patch("aipolabs_test.api.BackgroundTasks")
async def test_slack_events_chat_with_message(
    mock_background_tasks,
    mock_send_message,
    mock_handle_message,
    mock_get_token,
    test_client,
):
    """Test /slack/events endpoint with 'chat' message."""
    mock_handle_message.return_value = "This is a chat response."
    payload = {
        "type": "event_callback",
        "event": {
            "type": "message",
            "user": "user123",
            "channel": "channel456",
            "text": "chat: Hello there!",
            "thread_ts": "1234567890.123456",
        },
    }

    response = await test_client.post(
        "/slack/events", json=payload, headers={"Content-Type": "application/json"}
    )

    assert response.status_code == status.HTTP_200_OK
    mock_get_token.assert_called_once_with("user123")
    mock_handle_message.assert_called_once_with("user123", "Hello there!")
    mock_send_message.assert_called_once_with(
        "This is a chat response.", "channel456", "1234567890.123456"
    )


@pytest.mark.asyncio
@patch("aipolabs_test.api.get_user_token", return_value=None)
@patch("aipolabs_test.api.send_slack_message", new_callable=AsyncMock)
@patch("aipolabs_test.api.BackgroundTasks")
async def test_slack_events_chat_without_credentials(
    mock_background_tasks, mock_send_message, mock_get_token, test_client
):
    """Test /slack/events endpoint with 'chat' message when not authenticated."""
    payload = {
        "type": "event_callback",
        "event": {
            "type": "message",
            "user": "user123",
            "channel": "channel456",
            "text": "chat: Hello there!",
            "thread_ts": "1234567890.123456",
        },
    }

    response = await test_client.post(
        "/slack/events", json=payload, headers={"Content-Type": "application/json"}
    )

    assert response.status_code == status.HTTP_200_OK
    mock_get_token.assert_called_once_with("user123")
    mock_send_message.assert_called_once_with(
        "You are not authenticated with Google. Please use `auth` first.",
        "channel456",
        "1234567890.123456",
    )


@pytest.mark.asyncio
@patch(
    "aipolabs_test.api.get_user_token",
    return_value={"access_token": "fake_token"},
)
@patch("aipolabs_test.api.send_slack_message", new_callable=AsyncMock)
@patch("aipolabs_test.api.BackgroundTasks")
async def test_slack_events_chat_without_message(
    mock_background_tasks, mock_send_message, mock_get_token, test_client
):
    """Test /slack/events endpoint with empty 'chat' message."""
    payload = {
        "type": "event_callback",
        "event": {
            "type": "message",
            "user": "user123",
            "channel": "channel456",
            "text": "chat",
            "thread_ts": "1234567890.123456",
        },
    }

    response = await test_client.post(
        "/slack/events", json=payload, headers={"Content-Type": "application/json"}
    )

    assert response.status_code == status.HTTP_200_OK
    mock_get_token.assert_called_once_with("user123")
    mock_send_message.assert_called_once_with(
        "Chat session started. Please provide instructions; use `chat: <message>` for chat messages.",
        "channel456",
        "1234567890.123456",
    )


@pytest.mark.asyncio
@patch("aipolabs_test.api.cache.exists_event_id", return_value=True)
async def test_slack_events_duplicate_event(mock_exists_event_id, test_client):
    """Test /slack/events endpoint with duplicate event."""
    payload = {"type": "event_callback", "event_id": "duplicate_event"}
    response = await test_client.post("/slack/events", json=payload)
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"status": "ok"}
    mock_exists_event_id.assert_called_once_with("duplicate_event")


@pytest.mark.asyncio
@patch("aipolabs_test.api.cache.exists_event_id", return_value=False)
async def test_slack_events_url_verification(mock_exists_event_id, test_client):
    """Test /slack/events endpoint with url_verification event."""
    payload = {"type": "url_verification", "challenge": "test_challenge"}
    response = await test_client.post("/slack/events", json=payload)
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["challenge"] == "test_challenge"
    mock_exists_event_id.assert_called_once_with("url_verification")


@pytest.mark.asyncio
async def test_auth_callback_missing_code_or_state(test_client):
    """Test /auth/callback with missing code or state."""
    response = await test_client.get("/auth/callback?state=user123,channel456,None")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["detail"] == "Authorization code or state missing"
