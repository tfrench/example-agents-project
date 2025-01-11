import httpx
import logging
import os
from dotenv import load_dotenv

load_dotenv()

_logger = logging.getLogger(__name__)

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")


async def send_slack_message(message: str, channel: str, thread_ts: str = None):
    """Helper function to send a message to a Slack user, optionally in a thread."""
    slack_url = "https://slack.com/api/chat.postMessage"
    headers = {
        "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
        "Content-Type": "application/json",
    }

    data = {
        "channel": channel,
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": message,
                },
            }
        ],
    }

    if thread_ts is not None:
        data["thread_ts"] = thread_ts

    async with httpx.AsyncClient() as client:
        response = await client.post(slack_url, headers=headers, json=data)
        if response.status_code != 200:
            _logger.error(f"Failed to send message: {response.json()}")
        else:
            _logger.info(f"Message sent to channel {channel} in thread {thread_ts}")
