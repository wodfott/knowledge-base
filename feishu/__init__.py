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

    def download_file(self, message_id: str, file_key: str, file_name: str = "") -> dict:
        """Download a file from Feishu message and extract text.

        Uses Feishu REST API directly. Supports: txt, md, docx, pdf, code files.
        """
        import os, io, requests as req_lib
        try:
            # 1. Get tenant access token
            token_url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
            token_resp = req_lib.post(token_url, json={
                "app_id": self.app_id,
                "app_secret": self.app_secret,
            }, timeout=10)
            if token_resp.status_code != 200:
                return {"status": "error", "message": f"获取token失败: {token_resp.status_code}"}
            token_data = token_resp.json()
            token = token_data.get("tenant_access_token", "")
            if not token:
                return {"status": "error", "message": f"token为空: {token_data}"}

            # 2. Download file
            download_url = f"https://open.feishu.cn/open-apis/im/v1/messages/{message_id}/resources/{file_key}?type=file"
            headers = {"Authorization": f"Bearer {token}"}
            resp = req_lib.get(download_url, headers=headers, timeout=30)
            if resp.status_code != 200:
                return {"status": "error", "message": f"下载失败: HTTP {resp.status_code}"}

            raw = resp.content
            ext = os.path.splitext(file_name)[1].lower() if file_name else ".txt"

            text = ""
            if ext in (".txt", ".md", ".markdown", ".json", ".py", ".js", ".ts", ".yaml", ".yml", ".csv"):
                try:
                    text = raw.decode("utf-8")
                except:
                    text = raw.decode("utf-8", errors="replace")

            elif ext == ".docx":
                try:
                    from docx import Document
                    import io
                    doc = Document(io.BytesIO(raw))
                    text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
                except ImportError:
                    return {"status": "error", "message": "docx support: pip install python-docx"}

            elif ext == ".pdf":
                try:
                    import PyPDF2, io
                    reader = PyPDF2.PdfReader(io.BytesIO(raw))
                    text = "\n".join(p.extract_text() or "" for p in reader.pages)
                except ImportError:
                    return {"status": "error", "message": "pdf support: pip install PyPDF2"}

            else:
                return {"status": "error", "message": f"Unsupported format: {ext}"}

            if not text.strip():
                return {"status": "error", "message": "No text extracted"}

            logger.info(f"File downloaded: {file_name} ({len(text)} chars)")
            return {"status": "ok", "file_name": file_name, "content": text, "size": len(text)}

        except Exception as e:
            logger.error(f"File download error: {e}")
            return {"status": "error", "message": str(e)}


# Singleton
bot = FeishuBot()
