"""Feishu cloud document collector."""

import logging
from datetime import datetime

import lark_oapi as lark
from lark_oapi.api.docx.v1 import (
    GetDocumentRequest, ListDocumentBlockRequest,
    RawContentDocumentRequest,
)
from lark_oapi.api.drive.v1 import ListFileRequest

from config import settings
from agents.collector import _process_and_save
from utils import clean_text

logger = logging.getLogger(__name__)


class FeishuDocCollector:
    """Collect documents from Feishu cloud docs."""

    def __init__(self):
        self._client = None

    @property
    def client(self):
        if not self._client:
            self._client = (
                lark.Client.builder()
                .app_id(settings.feishu_app_id)
                .app_secret(settings.feishu_app_secret)
                .build()
            )
        return self._client

    def list_files(self, folder_token: str = "", page_size: int = 20) -> list[dict]:
        """List files in a Feishu drive folder."""
        try:
            request = (
                ListFileRequest.builder()
                .page_size(page_size)
                .folder_token(folder_token)
                .build()
            )
            response = self.client.drive.v1.file.list(request)
            if not response.success():
                logger.error(f"List files failed: {response.code} {response.msg}")
                return []

            files = []
            for f in response.data.files:
                if f.type in ("doc", "docx"):
                    files.append({
                        "token": f.token,
                        "name": f.name,
                        "type": f.type,
                        "url": f.url,
                        "modified_time": str(f.modified_time) if f.modified_time else "",
                    })
            return files
        except Exception as e:
            logger.error(f"List files error: {e}")
            return []

    def get_doc_content(self, doc_token: str) -> tuple[str, str]:
        """Get document title and raw content."""
        try:
            # Get document metadata
            doc_req = GetDocumentRequest.builder().document_id(doc_token).build()
            doc_resp = self.client.docx.v1.document.get(doc_req)
            if not doc_resp.success():
                return "", ""

            title = doc_resp.data.document.title or "Untitled"

            # Get raw content
            raw_req = RawContentDocumentRequest.builder().document_id(doc_token).build()
            raw_resp = self.client.docx.v1.document.raw_content(raw_req)
            if not raw_resp.success():
                return title, ""

            content = raw_resp.data.content or ""
            content = clean_text(content)
            return title, content
        except Exception as e:
            logger.error(f"Get doc content error for {doc_token}: {e}")
            return "", ""

    def collect_doc(self, doc_token: str) -> dict:
        """Collect a single Feishu document."""
        title, content = self.get_doc_content(doc_token)
        if not content:
            return {"status": "error", "message": f"No content for doc {doc_token}"}

        return _process_and_save(
            title=title or "Feishu Document",
            content=content,
            source_type="feishu_doc",
            source_url=f"https://bytedance.feishu.cn/docx/{doc_token}",
        )

    def collect_folder(self, folder_token: str = "", limit: int = 50) -> dict:
        """Collect all documents in a Feishu folder."""
        files = self.list_files(folder_token, page_size=min(limit, 50))
        results = {"total": len(files), "created": 0, "duplicate": 0, "error": 0}

        for f in files[:limit]:
            result = self.collect_doc(f["token"])
            if result["status"] == "created":
                results["created"] += 1
            elif result["status"] == "duplicate":
                results["duplicate"] += 1
            else:
                results["error"] += 1

        return results


# Singleton
feishu_doc_collector = FeishuDocCollector()
