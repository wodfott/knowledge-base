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

    # Log every incoming message
    logger.info(f"[MSG IN] type={msg_type} keys={list(content.keys())} "
                f"has_text={'text' in content} has_file={'file_key' in content} "
                f"text_preview={str(content.get('text',''))[:60]}")

    # --- Handle file/image/media messages ---
    if msg_type in ("file", "image", "media") or "file_key" in content:
        logger.info(f">>> File handler triggered: type={msg_type}, file_key={content.get('file_key','')[:30]}")
        return await _handle_file_message(content, message_id, msg_type)

    text = content.get("text", "").strip()

    if not text:
        return {"status": "ok", "message": "empty content"}

    # --- Command routing ---
    if text.startswith("/"):
        return await _handle_command(text, sender_id, message_id)

    # --- Natural language routing ---
    logger.info(f"Message routing: text='{text[:60]}' msg_type={msg_type}")

    # If it looks like a question → QA
    question_markers = ("?", "？", "吗", "呢", "什么", "怎么", "如何", "为什么", "哪个", "多少",
                        "what", "how", "why", "which", "who", "when", "where")
    if any(m in text for m in question_markers):
        logger.info(f"→ QA (question marker detected)")
        return await _handle_qa(text, sender_id, message_id)

    # If it contains a URL → collect
    if "http" in text:
        return await _handle_collect_url(text, sender_id, message_id)

    # If short and looks like a single entity name → try entity query first
    # Otherwise → go straight to QA
    entity_result = generate_entity_card(text)
    if entity_result["found"]:
        return await _handle_entity_query(text, sender_id, message_id)

    # Entity not found → QA
    logger.info(f"→ Entity not found, fallback to QA")
    return await _handle_qa(text, sender_id, message_id)


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

    elif cmd == "/flashcard" or cmd == "/闪卡":
        return await _handle_flashcard_create(arg, sender_id, message_id)

    elif cmd == "/stale" or cmd == "/过期":
        return await _handle_stale(sender_id, message_id)

    elif cmd == "/rec" or cmd == "/推荐":
        return await _handle_recommend(arg, sender_id, message_id)

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
            "• `/flashcard 实体名` - 创建闪卡\n"
            "• `/stale` - 查看过期知识\n"
            "• `/rec 实体名` - 相似推荐\n"
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

    # Follow-up: recommend similar entities
    _send_recommendations(entity_name, [], message_id)

    return {"status": "ok", "entity": result["entity"]["name"]}


async def _handle_qa(question: str, sender_id: str, message_id: str) -> dict:
    """Answer a question via RAG, with follow-up recommendations."""
    if not question:
        bot.reply_text(message_id, "请输入问题，例如: /ask OpenClaw是什么？")
        return {"status": "error", "message": "empty question"}

    logger.info(f"QA query: {question[:60]}")
    result = answer(question)
    logger.info(f"QA result: sources={len(result.get('sources',[]))}, cached={result.get('cached')}, answer_len={len(result.get('answer',''))}")

    card = qa_card(
        question=question,
        answer=result["answer"],
        sources=result["sources"],
    )
    bot.reply_card(message_id, card)

    # Follow-up: recommend related entities from sources
    _send_recommendations(question, result.get("sources", []), message_id)

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
    """Get today's review list with Anki-style cards."""
    reviews = db.get_due_reviews()
    if not reviews:
        bot.reply_text(message_id, "🎉 今日无待复习内容！")
        return {"status": "ok", "count": 0}

    # Send review cards one by one
    for review in reviews[:5]:
        entity = db.get_entity(review["entity_id"])
        if entity:
            card = review_card(
                entity_name=entity["name"],
                question=review.get("question", ""),
                answer=review.get("answer", ""),
                hint=review.get("hint", ""),
                entity_type=entity.get("type", ""),
                interval_days=review.get("interval_days", 1),
                repetitions=review.get("repetitions", 0),
            )
            bot.send_card(sender_id, card)

    return {"status": "ok", "count": len(reviews)}


async def _handle_flashcard_create(entity_name: str, sender_id: str, message_id: str) -> dict:
    """Create a flashcard for an entity, with fuzzy search fallback."""
    if not entity_name:
        bot.reply_text(message_id, "请输入实体名称，例如: /flashcard Python")
        return {"status": "error", "message": "empty name"}

    from agents.personal import create_flashcard

    result = create_flashcard(entity_name)

    if result["status"] == "error":
        # Try fuzzy search for suggestions
        candidates = graph_db.search_entities(entity_name, max_results=5)
        if candidates:
            names = "、".join(c["name"] for c in candidates[:5])
            bot.reply_text(message_id,
                f"❌ 未找到实体「{entity_name}」\n\n"
                f"💡 相似实体: {names}\n\n"
                f"请用完整名称重试: /flashcard 实体名")
        else:
            bot.reply_text(message_id, f"❌ 知识库中没有「{entity_name}」相关实体")
        return result

    if result["status"] == "duplicate":
        bot.reply_text(message_id, f"⚠️ {result['message']}")
        return result

    # Success
    entity = graph_db.find_entity_by_name(entity_name)
    type_info = f"[{entity['type']}]" if entity and entity.get('type') else ""
    bot.reply_text(message_id,
        f"✅ 已创建闪卡!\n\n"
        f"📚 实体: {entity_name} {type_info}\n"
        f"📅 下次复习: 明天\n"
        f"🔄 重复次数: 0\n\n"
        f"发送 /review 查看今日复习列表")
    return result


async def _handle_stale(sender_id: str, message_id: str) -> dict:
    """Show stale entities (not accessed for 90+ days)."""
    from agents.lifecycle import check_stale_entities
    stale = check_stale_entities(days_threshold=90)

    if not stale:
        bot.reply_text(message_id, "🌱 所有知识都很新鲜！暂无过期实体。")
        return {"status": "ok", "count": 0}

    lines = [f"🕰️ **知识保鲜预警** (90天未访问)\n"]
    for s in stale[:10]:
        emoji = "🔴" if s["days_stale"] > 180 else ("🟠" if s["days_stale"] > 120 else "🟡")
        lines.append(f"{emoji} **{s['name']}** [{s['type']}] — {s['days_stale']}天")
    lines.append(f"\n共 {len(stale)} 个过期实体，发送 /query 实体名 来重新回顾")

    bot.reply_text(message_id, "\n".join(lines))
    return {"status": "ok", "count": len(stale)}


async def _handle_recommend(entity_name: str, sender_id: str, message_id: str) -> dict:
    """Recommend similar entities."""
    if not entity_name:
        bot.reply_text(message_id, "请输入实体名称，例如: /rec Python")
        return {"status": "error"}

    from agents.recommend import recommend_similar, recommend_learning_path
    similar = recommend_similar(entity_name, top_k=5)
    path = recommend_learning_path(entity_name, max_depth=2)

    if not similar and not path:
        bot.reply_text(message_id, f"未找到与「{entity_name}」相似的实体")
        return {"status": "ok"}

    lines = [f"💡 **「{entity_name}」探索推荐**\n"]
    if similar:
        lines.append("**相似实体:**")
        for s in similar:
            lines.append(f"• {s['name']} [{s['type']}] — 相似度 {s['similarity']:.0%}")
    if path:
        lines.append(f"\n**学习路径:**")
        for p in path[:5]:
            arrow = "→" if p.get("direction") == "outgoing" else "←"
            lines.append(f"{arrow} {p['name']} [{p['type']}] — {p.get('relation', '')}")

    bot.reply_text(message_id, "\n".join(lines))
    return {"status": "ok"}


def _send_recommendations(query: str, sources: list[dict], message_id: str):
    """Send follow-up recommendations based on query and sources."""
    # Extract entity names from source titles
    source_titles = [s.get("title", "") for s in sources[:3] if s.get("title")]
    # Also try to find entities mentioned in source content
    candidates = set()
    for s in sources[:3]:
        content_text = s.get("content", "")[:300]
        # Quick entity extraction: find named entities from graph via search
        from storage.graph_db import graph_db
        # Search for keywords in the query
        words = query.replace("？", "").replace("?", "").replace("的", " ").replace("是", " ").split()
        for w in words[:5]:
            if len(w) >= 2:
                entities = graph_db.search_entities(w, max_results=3)
                for e in entities:
                    if e.get("name") and e["name"] not in candidates:
                        candidates.add(e["name"])

    if not candidates:
        return

    rec_list = list(candidates)[:5]
    from agents.recommend import recommend_similar as rec_similar
    expanded = []
    for name in rec_list[:2]:
        try:
            similar = rec_similar(name, top_k=3)
            for s in similar:
                expanded.append(f"• {s['name']} [{s.get('type', '')}] — 相似度 {s['similarity']:.0%}")
        except Exception:
            pass

    lines = ["💡 **相关推荐**"]
    if expanded:
        lines.extend(expanded[:5])
    else:
        lines.extend([f"• {n}" for n in rec_list[:5]])
    lines.append("\n发送 /query 实体名 深入了解")

    bot.reply_text(message_id, "\n".join(lines))


async def _handle_file_message(content: dict, message_id: str, msg_type: str = "file") -> dict:
    """Handle file/image message: download, extract text, store, reply with RAW content — no LLM."""
    file_key = content.get("file_key", "")
    # file_name might be in content or we derive it later
    file_name = content.get("file_name", "")

    if not file_key:
        bot.reply_text(message_id, "❌ 未找到文件，请确认已正确上传")
        return {"status": "error", "message": "no file_key"}

    if not file_name:
        file_name = f"feishu_file_{file_key[:8]}"

    bot.reply_text(message_id, f"📥 正在读取: {file_name} ...")

    result = bot.download_file(message_id, file_key, file_name)
    logger.info(f"File download result: status={result.get('status')}, name={file_name}, size={result.get('size',0)}")

    if result["status"] != "ok":
        bot.reply_text(message_id, f"❌ 读取失败: {result.get('message', '未知错误')}\n支持格式: txt, md, docx, pdf, py, js, json, csv")
        return result

    text_content = result["content"]
    title = file_name.rsplit(".", 1)[0] if "." in file_name else file_name

    # Store as document (no LLM processing in reply)
    from agents.collector import collect_text
    collect_result = collect_text(
        title=title,
        text=text_content,
        source_type="feishu_file",
        source_url=f"feishu://file/{file_key}",
    )

    if collect_result["status"] == "created":
        # Auto-process in background (entity extraction, indexing)
        from agents.knowledge import process_and_index_document
        process_and_index_document(collect_result["id"])

    # ALWAYS reply with raw content — never LLM
    reply = f"📄 **{title}**\n\n{text_content}"
    if len(reply) > 5000:
        reply = reply[:4900] + "\n\n... (内容过长已截断，全文已存入知识库)"
    bot.reply_text(message_id, reply)

    return {"status": "ok", "doc_id": collect_result.get("id", ""),
            "title": title, "size": result.get("size", 0)}


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
