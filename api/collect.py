"""Collection API endpoints."""

import logging
from fastapi import APIRouter, HTTPException

from models.api import CollectRequest, CollectResponse
from agents.collector import collect_url, collect_text, poll_rss
from agents.collector.feishu_doc import feishu_doc_collector
from agents.collector.obsidian import import_markdown_file, import_folder
from agents.knowledge import process_and_index_document

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/collect", tags=["Collection"])


@router.post("/url", response_model=CollectResponse)
async def api_collect_url(req: CollectRequest):
    """Collect content from a URL."""
    if not req.url:
        raise HTTPException(status_code=400, detail="url is required")

    result = await collect_url(req.url)

    if result["status"] == "created":
        process_and_index_document(result["id"])
        return CollectResponse(
            status="ok",
            doc_id=result["id"],
            message=f"Collected and indexed: {result.get('title', '')}",
        )
    elif result["status"] == "duplicate":
        return CollectResponse(status="duplicate", message="Document already exists")
    else:
        raise HTTPException(status_code=500, detail=result.get("message", "Collection failed"))


@router.post("/text", response_model=CollectResponse)
async def api_collect_text(req: CollectRequest):
    """Collect plain text content."""
    if not req.text:
        raise HTTPException(status_code=400, detail="text is required")

    result = collect_text(
        title=req.title or "Untitled",
        text=req.text,
        source_type=req.source_type,
    )

    if result["status"] == "created":
        process_and_index_document(result["id"])
        return CollectResponse(
            status="ok",
            doc_id=result["id"],
            message="Text collected and indexed",
        )
    elif result["status"] == "duplicate":
        return CollectResponse(status="duplicate", message="Content already exists")
    else:
        raise HTTPException(status_code=500, detail=result.get("message", ""))


@router.post("/rss", response_model=CollectResponse)
async def api_poll_rss(req: CollectRequest):
    """Poll an RSS feed."""
    if not req.rss_feed_url:
        raise HTTPException(status_code=400, detail="rss_feed_url is required")

    results = await poll_rss(req.rss_feed_url)
    created = [r for r in results if r.get("status") == "created"]
    errors = [r for r in results if r.get("status") == "error"]

    # Index new documents
    for doc in created:
        process_and_index_document(doc["id"])

    return CollectResponse(
        status="ok",
        message=f"Processed {len(results)} entries: {len(created)} new, {len(errors)} errors",
    )


@router.post("/feishu-doc")
async def api_collect_feishu_doc(doc_token: str = "", folder_token: str = "", limit: int = 50):
    """Collect Feishu cloud documents."""
    if doc_token:
        result = feishu_doc_collector.collect_doc(doc_token)
        if result["status"] == "created":
            process_and_index_document(result["id"])
        return result
    elif folder_token:
        result = feishu_doc_collector.collect_folder(folder_token, limit=limit)
        return {"status": "ok", **result}
    else:
        raise HTTPException(status_code=400, detail="doc_token or folder_token required")


@router.post("/note")
async def api_collect_note(title: str = "", content: str = ""):
    """Quick note from Feishu — auto-detect title from first line if empty."""
    if not content.strip():
        raise HTTPException(status_code=400, detail="content is required")

    # Auto-title from first line
    if not title:
        first_line = content.strip().split("\n")[0][:80]
        title = first_line if first_line else "未命名笔记"

    result = collect_text(title=title, text=content, source_type="feishu_note")
    if result["status"] == "created":
        process_and_index_document(result["id"])
        return {
            "status": "ok",
            "doc_id": result["id"],
            "title": title,
            "message": f"笔记已保存 📝 {title}",
            "entities": 0,  # Will be populated after async processing
        }
    elif result["status"] == "duplicate":
        return {"status": "duplicate", "message": "笔记内容重复，已存在相似笔记"}
    else:
        raise HTTPException(status_code=500, detail=result.get("message", ""))


@router.post("/feishu-file")
async def api_collect_feishu_file(message_id: str = "", file_key: str = "", file_name: str = ""):
    """Download + import a file sent via Feishu message."""
    if not file_key:
        raise HTTPException(status_code=400, detail="file_key required")

    from feishu import bot as feishu_bot
    result = feishu_bot.download_file(message_id, file_key, file_name)

    if result["status"] != "ok":
        raise HTTPException(status_code=400, detail=result.get("message", "File download failed"))

    # Save to knowledge base
    collect_result = collect_text(
        title=result["file_name"].rsplit(".", 1)[0],
        text=result["content"],
        source_type="feishu_file",
        source_url=f"feishu://file/{file_key}",
    )

    if collect_result["status"] == "created":
        process_and_index_document(collect_result["id"])
        return {
            "status": "ok",
            "doc_id": collect_result["id"],
            "file_name": result["file_name"],
            "size": result["size"],
            "message": f"文件已导入 📎 {result['file_name']}",
        }
    elif collect_result["status"] == "duplicate":
        return {"status": "duplicate", "message": "文件内容重复"}
    else:
        raise HTTPException(status_code=500, detail=collect_result.get("message", ""))


@router.post("/markdown-file")
async def api_import_markdown_file(filepath: str):
    """Import a single Markdown file (Obsidian/Notion export)."""
    result = import_markdown_file(filepath)
    if result["status"] == "created":
        process_and_index_document(result["id"])
    return result


@router.post("/markdown-folder")
async def api_import_markdown_folder(folder_path: str, recursive: bool = True):
    """Import all Markdown files from a folder (Obsidian vault)."""
    result = import_folder(folder_path, recursive=recursive)
    # Index all newly created docs
    for f in result.get("files", []):
        if f.get("doc_id"):
            process_and_index_document(f["doc_id"])
    return {"status": "ok", **result}
