from datetime import datetime
import os
import logging
import httpx
from dotenv import load_dotenv
from fastapi import HTTPException
from google.oauth2.credentials import Credentials

from .db import (
    NoCredentialsFound,
    store_user_token,
    get_user_token,
    delete_user_token,
    has_user_token,
    update_user_token,
)
from . import cache

load_dotenv()

_logger = logging.getLogger(__name__)

CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI")


async def store_user_credentials(user_id: str, data: dict):
    """Stores the user's credentials."""
    await store_user_token(user_id, data)


async def has_user_credentials(user_id: str) -> bool:
    creds = await has_user_token(user_id)
    return True if creds else False


async def get_user_credentials(user_id: str) -> Credentials:
    """Retrieves the stored credentials for a given user."""
    try:
        creds = await get_user_token(user_id)
    except NoCredentialsFound:
        return None

    # check if needs a refresh (check expired); refresh; store
    if creds["expires_at"] < datetime.now():
        await refresh_access_token(user_id, creds["refresh_token"])
        creds = await get_user_token(user_id)

    credentials = Credentials(
        token=creds["access_token"],
        refresh_token=creds["refresh_token"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        scopes=creds["scopes"],
    )
    return credentials


def get_auth_url(user_id: str, channel: str, thread_ts: str) -> str:
    auth_url = (
        f"https://accounts.google.com/o/oauth2/v2/auth"
        f"?client_id={CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}"
        f"&response_type=code"
        f"&scope=email profile "
        f"https://www.googleapis.com/auth/gmail.readonly "
        f"https://www.googleapis.com/auth/gmail.compose "
        f"https://www.googleapis.com/auth/gmail.send"
        f"&access_type=offline"
        f"&prompt=consent"
        f"&state={user_id},{channel},{thread_ts}"
    )

    _logger.info(f"Auth url: {auth_url}")

    return auth_url


async def get_access_token(code: str) -> dict:
    token_url = "https://oauth2.googleapis.com/token"
    data = {
        "code": code,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(token_url, data=data)
        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code, detail=response.json()
            )
        data = response.json()
    return data


async def refresh_access_token(user_id: str, refresh_token: str) -> dict:
    """Helper function to refresh Google OAuth2 access token."""
    token_url = "https://oauth2.googleapis.com/token"
    data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(token_url, data=data)

        if response.status_code == 200:
            data = response.json()
            await update_user_token(user_id, data)  # update
            await cache.set_user_token(user_id, data)  # update cache

            _logger.info("Token successfully refreshed")
            return response.json()
        else:
            raise HTTPException(
                status_code=response.status_code, detail="Failed to refresh token"
            )


async def revoke_credentials(user_id: str):
    """Revokes the token on Google's side."""
    token = await get_user_token(user_id)

    if token["expires_at"] < datetime.now():
        await refresh_access_token(user_id, token["refresh_token"])
        token = await get_user_token(user_id)

    access_token = token["access_token"]

    revoke_url = "https://oauth2.googleapis.com/revoke"
    data = {"token": access_token}

    async with httpx.AsyncClient() as client:
        response = await client.post(
            revoke_url,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if response.status_code == 200:
            _logger.info("Token successfully revoked")
        else:
            raise HTTPException(
                status_code=response.status_code,
                detail="Failed to revoke token on Google side",
            )

    await delete_user_token(user_id)
