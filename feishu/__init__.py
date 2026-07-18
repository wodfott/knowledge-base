"""Feishu bot: message sending, card templates, event handling."""

import logging
import hashlib
import time
import json
from typing import Optional

import lark_oapi as lark
from lark_oapi.api.im.v1 import (
    CreateMessageRequest, CreateMessageRequestBody,
    ReplyMessageRequest, ReplyMessageRequestBody,
    SendMessageRequest, SendMessageRequestBody,
)

from config import settings

logger = logging.getLogger(__name__)


class FeishuBot:
    """Feishu IM bot client."""

    def __init__(self):
        self.app_id = settings.feishu_app_id
        self.app_secret = settings.feishu_app_secret
        self._client = None
        self._processed_events: set[str] = set()  # Dedup

    @property
    def client(self):
        if not self._client:
            self._client = (
                lark.Client.builder()
                .app_id(self.app_id)
                .app_secret(self.app_secret)
                .build()
            )
        return self._client

    def is_duplicate(self, event_id: str) -> bool:
        """Check if event has already been processed."""
        if event_id in self._processed_events:
            return True
        self._processed_events.add(event_id)
        # Keep set bounded
        if len(self._processed_events) > 10000:
            self._processed_events.clear()
        return False

    def send_text(
        self,
        receive_id: str,
        content: str,
        receive_id_type: str = "open_id",
    ) -> dict:
        """Send a text message to a user or group."""
        try:
            request = CreateMessageRequest.builder().build()
            request.receive_id_type = receive_id_type

            body = CreateMessageRequestBody.builder()
            body.receive_id = receive_id
            body.msg_type = "text"
            body.content = json.dumps({"text": content})

            response = self.client.im.v1.message.create(
                CreateMessageRequest.builder()
                .receive_id_type(receive_id_type)
                .request_body(
                    CreateMessageRequestBody.builder()
                    .receive_id(receive_id)
                    .msg_type("text")
                    .content(json.dumps({"text": content}))
                    .build()
                )
                .build()
            )

            if response.success():
                return {"status": "ok", "message_id": response.data.message_id}
            else:
                logger.error(f"Feishu send failed: {response.code} {response.msg}")
                return {"status": "error", "message": response.msg}

        except Exception as e:
            logger.error(f"Feishu send exception: {e}")
            return {"status": "error", "message": str(e)}

    def send_card(
        self,
        receive_id: str,
        card: dict,
        receive_id_type: str = "open_id",
    ) -> dict:
        """Send an interactive card message."""
        try:
            response = self.client.im.v1.message.create(
                CreateMessageRequest.builder()
                .receive_id_type(receive_id_type)
                .request_body(
                    CreateMessageRequestBody.builder()
                    .receive_id(receive_id)
                    .msg_type("interactive")
                    .content(json.dumps(card))
                    .build()
                )
                .build()
            )

            if response.success():
                return {"status": "ok", "message_id": response.data.message_id}
            else:
                logger.error(f"Feishu card send failed: {response.code} {response.msg}")
                return {"status": "error", "message": response.msg}

        except Exception as e:
            logger.error(f"Feishu card send exception: {e}")
            return {"status": "error", "message": str(e)}

    def reply_text(
        self,
        message_id: str,
        content: str,
    ) -> dict:
        """Reply to a message with text."""
        try:
            response = self.client.im.v1.message.reply(
                ReplyMessageRequest.builder()
                .message_id(message_id)
                .request_body(
                    ReplyMessageRequestBody.builder()
                    .msg_type("text")
                    .content(json.dumps({"text": content}))
                    .build()
                )
                .build()
            )

            if response.success():
                return {"status": "ok", "message_id": response.data.message_id}
            else:
                logger.error(f"Feishu reply failed: {response.code} {response.msg}")
                return {"status": "error", "message": response.msg}

        except Exception as e:
            logger.error(f"Feishu reply exception: {e}")
            return {"status": "error", "message": str(e)}

    def reply_card(
        self,
        message_id: str,
        card: dict,
    ) -> dict:
        """Reply to a message with an interactive card."""
        try:
            response = self.client.im.v1.message.reply(
                ReplyMessageRequest.builder()
                .message_id(message_id)
                .request_body(
                    ReplyMessageRequestBody.builder()
                    .msg_type("interactive")
                    .content(json.dumps(card))
                    .build()
                )
                .build()
            )

            if response.success():
                return {"status": "ok", "message_id": response.data.message_id}
            else:
                logger.error(f"Feishu card reply failed: {response.code} {response.msg}")
                return {"status": "error", "message": response.msg}

        except Exception as e:
            logger.error(f"Feishu card reply exception: {e}")
            return {"status": "error", "message": str(e)}


# Singleton
bot = FeishuBot()
