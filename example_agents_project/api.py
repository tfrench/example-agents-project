import logging
import os
from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from . import cache
from .agent import process_message
from .credentials import (
    get_access_token,
    store_user_credentials,
    get_user_credentials,
    get_auth_url,
    has_user_credentials,
    revoke_credentials,
)
from .db import init_db
from .slack import send_slack_message

load_dotenv()


class HostnameFormatter(logging.Formatter):
    """Custom formatter to add Docker hostname to log messages."""

    def format(self, record):
        record.hostname = os.getpid()
        return super().format(record)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(hostname)s - %(message)s",
)
_logger = logging.getLogger(__name__)
logging.getLogger().handlers[0].setFormatter(
    HostnameFormatter("%(asctime)s - %(levelname)s - %(hostname)s - %(message)s")
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _logger.info("Starting lifespan")
    try:
        await init_db()
        _logger.info("Database initialized successfully")

        await cache.init_client()
        _logger.info("Redis client initialized successfully")

        yield

        await cache.close_client()
        _logger.info("Redis client closed successfully")
    except Exception as e:
        _logger.error(f"Error during lifespan startup: {e}")
        raise
    finally:
        _logger.info("Closing lifespan")


app = FastAPI(lifespan=lifespan)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    _logger.info("Health check endpoint called")
    return {"status": "ok"}


@app.get("/auth/callback")
async def auth_callback(request: Request, background_tasks: BackgroundTasks):
    """Handles the callback from Google's OAuth2 flow."""
    _logger.info("Auth callback endpoint called")

    code = request.query_params.get("code")
    user_id, channel, thread_ts = request.query_params.get("state").split(",")
    thread_ts = None if thread_ts == "None" else thread_ts

    _logger.info(f"User ID: {user_id}, Channel: {channel}, Thread TS: {thread_ts}")

    if not code or not user_id:
        _logger.error("Authorization code or state missing")
        raise HTTPException(
            status_code=400, detail="Authorization code or state missing"
        )

    data = await get_access_token(code)
    await store_user_credentials(user_id, data)
    await cache.set_user_token(user_id, data)  # update cache

    message = "Success! You have authenticated with Google. You can use the `chat` now."
    background_tasks.add_task(send_slack_message, message, channel, thread_ts)

    _logger.info("User %s successfully authenticated", user_id)

    return JSONResponse(
        content={
            "message": "Authentication successful. You can close this tab and return to Slack."
        }
    )


@app.post("/slack/events")
async def slack_events(slack_event: dict, background_tasks: BackgroundTasks):
    """Endpoint to handle Slack events."""
    event_type = slack_event.get("type")
    event_id = slack_event.get("event_id")

    if event_type == "url_verification":
        _logger.info("URL verification challenge received")
        return {"challenge": slack_event.get("challenge")}

    # Prevent duplicate events (Slack funkiness)
    if await cache.exists_event_id(event_id):
        _logger.info("Event %s already processed", event_id)
        return {"status": "ok"}
    else:
        await cache.add_event_id(event_id)  # add to cache

    _logger.info(f"Handling Slack event: {event_id}")

    event_data = slack_event.get("event")
    if (
        event_data
        and event_data.get("type") == "message"
        and "bot_id" not in event_data
    ):
        user_id = event_data.get("user")
        channel = event_data.get("channel")
        thread_ts = event_data.get("thread_ts")
        text = event_data.get("text")

        # No thread (Slack funkiness)
        thread_ts = None if thread_ts == "None|here" else thread_ts

        _logger.info(f"Received message event from user {user_id}: {text}")

        if text and text.lower().startswith("hello"):
            response_text = (
                "Hello! I'm here to help!\n"
                "First you need to authenticate (message: `auth`).\n"
                "You can check your authentication status (message: `status`).\n"
                "Then I can help manage your emails (read; send; draft) (message: `chat`).\n"
                "Finally, you can revoke credentials (message: `revoke`).\n"
            )
            background_tasks.add_task(
                send_slack_message, response_text, channel, thread_ts
            )
        elif text and text.lower().startswith("auth"):
            # Check if user has existing credentials - prioritise cache over db
            if await cache.exists_user_token(user_id) or await has_user_credentials(
                user_id
            ):
                message = """You have existing credentials.\nYou can use `chat`; or else `revoke` first."""
            else:
                auth_url = get_auth_url(user_id, channel, thread_ts)
                message = f"Please click <{auth_url}|here> to authenticate with Google."

            background_tasks.add_task(send_slack_message, message, channel, thread_ts)

        elif text and text.lower().startswith("status"):
            # Check if user has existing credentials - prioritise cache over db
            if await cache.exists_user_token(user_id) or await has_user_credentials(
                user_id
            ):
                message = """You have existing credentials.\nYou can use `chat` to send messages."""
            else:
                message = """You don't have existing credentials.\nUse `auth` to authenticate."""

            background_tasks.add_task(send_slack_message, message, channel, thread_ts)

        elif text and text.lower().startswith("revoke"):
            has_creds = await has_user_credentials(user_id)
            _logger.info(f"Has creds: {has_creds}")

            if has_creds:
                await revoke_credentials(user_id)
                await cache.remove_user_token(user_id)  # delete from cache
                message = "Credentials revoked successfully."
            else:
                message = (
                    "You don't have existing credentials. Use `auth` to authenticate."
                )

            background_tasks.add_task(send_slack_message, message, channel, thread_ts)

        elif text and text.lower().startswith("chat"):
            if not await get_user_credentials(user_id):
                response_text = (
                    "You are not authenticated with Google. Please use `auth` first."
                )
            else:
                chat_message = None
                if ":" in text:
                    _, chat_message = text.split(":", maxsplit=1)
                    chat_message = chat_message.lstrip()

                if not chat_message:
                    response_text = "Chat session started. Please provide instructions; use `chat: <message>` for chat messages."
                else:
                    response_text = await process_message(user_id, chat_message)

            background_tasks.add_task(
                send_slack_message, response_text, channel, thread_ts
            )

        else:
            background_tasks.add_task(
                send_slack_message,
                "Sorry, I didn't understand that. Try message: `hello`, `auth`, `chat`, `revoke`.",
                channel,
                thread_ts,
            )

    _logger.info(f"Event {event_id} processed successfully")

    return {"status": "ok"}
