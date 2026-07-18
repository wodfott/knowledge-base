"""Feishu event handlers: message routing, card actions, shortcuts."""

import json
import logging
from typing import Optional

from feishu import bot
from feishu.cards import entity_card, qa_card, review_card, text_entity_card
from agents.qa import answer, generate_entity_card
from agents.knowledge import process_and_index_document
from agents.collector import collect_url, collect_text, poll_rss
from storage import db
from storage.graph_db import graph_db

logger = logging.getLogger(__name__)


async def handle_message_event(event: dict) -> dict:
    """Handle incoming message event from Feishu."""
    event_id = event.get("header", {}).get("event_id", "")
    if bot.is_duplicate(event_id):
        return {"status": "ok", "message": "duplicate"}

    event_data = event.get("event", {})
    message = event_data.get("message", {})
    sender = event_data.get("sender", {})
    sender_id = sender.get("sender_id", {}).get("open_id", "")

    msg_type = message.get("message_type", "text")
    content_str = message.get("content", "{}")
    message_id = message.get("message_id", "")

    try:
        content = json.loads(content_str)
    except json.JSONDecodeError:
        content = {}

    text = content.get("text", "").strip()

    if not text:
        return {"status": "ok", "message": "empty content"}

    # --- Command routing ---
    if text.startswith("/"):
        return await _handle_command(text, sender_id, message_id)

    # Default: treat as entity query
    return await _handle_entity_query(text, sender_id, message_id)


async def _handle_command(text: str, sender_id: str, message_id: str) -> dict:
    """Route slash commands."""
    parts = text.split(maxsplit=1)
    cmd = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    if cmd == "/query" or cmd == "/搜索":
        return await _handle_entity_query(arg, sender_id, message_id)

    elif cmd == "/ask" or cmd == "/问答":
        return await _handle_qa(arg, sender_id, message_id)

    elif cmd == "/collect" or cmd == "/收藏":
        return await _handle_collect_url(arg, sender_id, message_id)

    elif cmd == "/rss" or cmd == "/订阅":
        return await _handle_rss(arg, sender_id, message_id)

    elif cmd == "/recap" or cmd == "/周报":
        return await _handle_recap(arg, sender_id, message_id)

    elif cmd == "/review" or cmd == "/复习":
        return await _handle_review(sender_id, message_id)

    elif cmd == "/help" or cmd == "/帮助":
        help_text = (
            "📚 **知识管理助手**\n\n"
            "**命令列表:**\n"
            "• `/query 实体名` - 查询知识图谱\n"
            "• `/ask 问题` - 知识问答\n"
            "• `/collect URL` - 收藏网页\n"
            "• `/rss URL` - 订阅RSS\n"
            "• `/recap [7d|30d|90d]` - 知识周报\n"
            "• `/review` - 今日复习\n"
            "• `/help` - 帮助\n\n"
            "**直接发消息:** 自动识别为实体查询或问答"
        )
        bot.reply_text(message_id, help_text)
        return {"status": "ok", "command": "help"}

    else:
        # Unknown command → try entity query
        return await _handle_entity_query(text, sender_id, message_id)


async def _handle_entity_query(entity_name: str, sender_id: str, message_id: str) -> dict:
    """Query entity and return card."""
    if not entity_name:
        bot.reply_text(message_id, "请输入要查询的实体名称，例如: /query OpenClaw")
        return {"status": "error", "message": "empty query"}

    result = generate_entity_card(entity_name)

    if not result["found"]:
        # Try Q&A instead
        return await _handle_qa(entity_name, sender_id, message_id)

    # Send card
    card = entity_card(
        entity_name=result["entity"]["name"],
        entity_type=result["entity"]["type"],
        description=result["entity"].get("description", ""),
        relations=result.get("relations", []),
        related_docs=result.get("related_docs", []),
        text_tree=result.get("text_tree", ""),
    )
    bot.reply_card(message_id, card)

    # Also send quick text summary
    summary = result.get("text_tree", "")
    if summary:
        bot.reply_text(message_id, summary[:500])

    return {"status": "ok", "entity": result["entity"]["name"]}


async def _handle_qa(question: str, sender_id: str, message_id: str) -> dict:
    """Answer a question via RAG."""
    if not question:
        bot.reply_text(message_id, "请输入问题，例如: /ask OpenClaw是什么？")
        return {"status": "error", "message": "empty question"}

    result = answer(question)
    card = qa_card(
        question=question,
        answer=result["answer"],
        sources=result["sources"],
    )
    bot.reply_card(message_id, card)
    return {"status": "ok"}


async def _handle_collect_url(url: str, sender_id: str, message_id: str) -> dict:
    """Collect a URL into knowledge base."""
    if not url:
        bot.reply_text(message_id, "请输入URL，例如: /collect https://example.com")
        return {"status": "error", "message": "empty url"}

    bot.reply_text(message_id, f"🔄 正在采集: {url}")

    result = await collect_url(url)
    if result["status"] == "created":
        # Auto-process: extract knowledge + index
        doc_id = result["id"]
        process_result = process_and_index_document(doc_id)
        bot.reply_text(
            message_id,
            f"✅ 已收藏!\n"
            f"• 实体: {process_result.get('knowledge', {}).get('entities', 0)} 个\n"
            f"• 关系: {process_result.get('knowledge', {}).get('relations', 0)} 个\n"
            f"• 索引块: {process_result.get('indexing', {}).get('chunks', 0)} 个",
        )
    elif result["status"] == "duplicate":
        bot.reply_text(message_id, f"⚠️ 内容重复，已存在相似文档")
    else:
        bot.reply_text(message_id, f"❌ 采集失败: {result.get('message', '')}")

    return result


async def _handle_rss(feed_url: str, sender_id: str, message_id: str) -> dict:
    """Subscribe to an RSS feed."""
    if not feed_url:
        bot.reply_text(message_id, "请输入RSS订阅地址，例如: /rss https://example.com/feed.xml")
        return {"status": "error", "message": "empty rss url"}

    bot.reply_text(message_id, f"🔄 正在订阅: {feed_url}")

    results = await poll_rss(feed_url)
    created = [r for r in results if r.get("status") == "created"]
    duplicates = [r for r in results if r.get("status") == "duplicate"]
    errors = [r for r in results if r.get("status") == "error"]

    # Process and index new documents
    for doc in created:
        process_and_index_document(doc["id"])

    bot.reply_text(
        message_id,
        f"📰 RSS订阅完成!\n"
        f"• 新增: {len(created)} 篇\n"
        f"• 重复: {len(duplicates)} 篇\n"
        f"• 失败: {len(errors)} 篇",
    )
    return {"status": "ok", "created": len(created)}


async def _handle_recap(period: str, sender_id: str, message_id: str) -> dict:
    """Generate a knowledge recap."""
    from datetime import datetime, timedelta

    now = datetime.now()
    if period == "30d":
        since = (now - timedelta(days=30)).isoformat()
        label = "30天"
    elif period == "90d":
        since = (now - timedelta(days=90)).isoformat()
        label = "90天"
    else:
        since = (now - timedelta(days=7)).isoformat()
        label = "7天"

    stats = db.get_stats(since=since)
    entities = db.list_entities(limit=10)
    top_names = [e["name"] for e in entities[:5]]

    text = (
        f"📊 **知识周报** ({label})\n\n"
        f"• 新增文档: {stats['documents']} 篇\n"
        f"• 新增实体: {stats['entities']} 个\n"
        f"• 新增关系: {stats['relations']} 条\n\n"
        f"**活跃实体:** {', '.join(top_names[:5]) if top_names else '无'}"
    )
    bot.reply_text(message_id, text)
    return {"status": "ok"}


async def _handle_review(sender_id: str, message_id: str) -> dict:
    """Get today's review list."""
    reviews = db.get_due_reviews()
    if not reviews:
        bot.reply_text(message_id, "🎉 今日无待复习内容！")
        return {"status": "ok", "count": 0}

    # Send review cards one by one
    for review in reviews[:5]:
        entity = db.get_entity(review["entity_id"])
        if entity:
            relations_data = db.get_relations_for_entity(entity["id"])
            relation_strs = [
                f"{r['relation_type']}: {_get_entity_name(r['source_entity_id'])} → {_get_entity_name(r['target_entity_id'])}"
                for r in relations_data[:3]
            ]
            card = review_card(
                entity_name=entity["name"],
                relations=relation_strs,
                related_docs=[did for did in entity.get("source_doc_ids", [])[:3]],
            )
            bot.send_card(sender_id, card)

    return {"status": "ok", "count": len(reviews)}


def _get_entity_name(entity_id: str) -> str:
    """Get entity name by ID."""
    entity = graph_db.get_entity(entity_id)
    if entity:
        return entity.get("name", entity_id)
    sql_entity = db.get_entity(entity_id)
    if sql_entity:
        return sql_entity["name"]
    return entity_id


async def handle_card_action(action_data: dict) -> dict:
    """Handle card button click events."""
    action = action_data.get("action", {})
    value_str = action.get("value", "{}")

    try:
        value = json.loads(value_str)
    except json.JSONDecodeError:
        value = {}

    action_type = value.get("action", "")
    entity_name = value.get("entity", "")
    rating = value.get("rating", "")

    if action_type == "feedback":
        if rating == "up":
            return {"status": "ok", "toast": "感谢反馈！👍"}
        else:
            return {"status": "ok", "toast": "感谢反馈，我们会改进！👎"}

    elif action_type == "star_review":
        # Add to review queue
        entity = graph_db.find_entity_by_name(entity_name)
        if entity:
            from datetime import datetime, timedelta
            review = {
                "id": f"review_{entity['id']}",
                "entity_id": entity["id"],
                "ease": 2.5,
                "interval_days": 1,
                "repetitions": 0,
                "next_review": (datetime.now() + timedelta(days=1)).isoformat(),
                "created_at": datetime.now().isoformat(),
            }
            db.insert_review(review)
            return {"status": "ok", "toast": f"已加入复习队列: {entity_name}"}
        return {"status": "error", "toast": "实体未找到"}

    elif action_type == "expand":
        return {"status": "ok", "action": "expand", "entity": entity_name}

    elif action_type in ("review_easy", "review_hard", "review_skip"):
        entity = graph_db.find_entity_by_name(entity_name)
        if entity:
            # Update review record
            reviews = db.get_due_reviews()
            for r in reviews:
                if r["entity_id"] == entity["id"]:
                    from datetime import datetime, timedelta
                    if action_type == "review_easy":
                        r["ease"] = min(3.5, r["ease"] + 0.2)
                        r["interval_days"] = int(r["interval_days"] * r["ease"])
                    elif action_type == "review_hard":
                        r["ease"] = max(1.3, r["ease"] - 0.2)
                        r["interval_days"] = max(1, int(r["interval_days"] * 0.5))
                    r["repetitions"] += 1
                    r["last_reviewed"] = datetime.now().isoformat()
                    r["next_review"] = (datetime.now() + timedelta(days=r["interval_days"])).isoformat()
                    db.insert_review(r)
                    break
            return {"status": "ok", "toast": f"复习记录已更新: {entity_name}"}
        return {"status": "error", "toast": "实体未找到"}

    return {"status": "ok", "toast": "操作已收到"}
