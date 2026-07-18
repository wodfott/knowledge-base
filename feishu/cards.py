"""Feishu card templates for graph queries, Q&A, and reviews."""

import json
from typing import Optional


def entity_card(
    entity_name: str,
    entity_type: str,
    description: str,
    relations: list[dict],
    related_docs: list[dict],
    text_tree: str = "",
) -> dict:
    """Build a Feishu card for entity display."""
    elements = []

    # Header
    elements.append({
        "tag": "div",
        "text": {
            "tag": "lark_md",
            "content": f"**📌 {entity_name}**  [{entity_type}]",
        },
    })

    # Description
    if description:
        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": description[:200],
            },
        })
        elements.append({"tag": "hr"})

    # Relations
    if relations:
        rel_lines = ["**🔗 关联关系:**"]
        for r in relations[:8]:
            arrow = "→" if r.get("direction") == "outgoing" else "←"
            rel_lines.append(
                f"{arrow} {r['relation_type']}: {r.get('target_name', '?')} "
                f"[{r.get('target_type', '?')}]"
            )
        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": "\n".join(rel_lines),
            },
        })
        elements.append({"tag": "hr"})

    # Related docs
    if related_docs:
        doc_lines = ["**📄 相关文档:**"]
        for d in related_docs[:5]:
            doc_lines.append(f"• {d.get('title', '?')[:80]}")
        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": "\n".join(doc_lines),
            },
        })

    # Actions
    elements.append({
        "tag": "action",
        "actions": [
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "⭐ 收藏复习"},
                "type": "primary",
                "value": json.dumps({"action": "star_review", "entity": entity_name}),
            },
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "📝 批注"},
                "type": "default",
                "value": json.dumps({"action": "annotate", "entity": entity_name}),
            },
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "🔗 展开关系"},
                "type": "default",
                "value": json.dumps({"action": "expand", "entity": entity_name}),
            },
        ],
    })

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": f"📌 {entity_name}"},
            "template": "blue",
        },
        "elements": elements,
    }


def qa_card(question: str, answer: str, sources: list[dict]) -> dict:
    """Build a Feishu card for Q&A display."""
    elements = []

    # Question
    elements.append({
        "tag": "div",
        "text": {
            "tag": "lark_md",
            "content": f"**❓ {question[:100]}**",
        },
    })
    elements.append({"tag": "hr"})

    # Answer
    elements.append({
        "tag": "div",
        "text": {
            "tag": "lark_md",
            "content": answer[:1500],
        },
    })

    # Sources
    if sources:
        elements.append({"tag": "hr"})
        src_lines = ["**📚 参考来源:**"]
        for i, s in enumerate(sources[:3], 1):
            src_lines.append(f"{i}. {s.get('title', '未知')[:80]}")
        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": "\n".join(src_lines),
            },
        })

    # Feedback buttons
    elements.append({
        "tag": "action",
        "actions": [
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "👍"},
                "type": "default",
                "value": json.dumps({"action": "feedback", "rating": "up"}),
            },
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "👎"},
                "type": "default",
                "value": json.dumps({"action": "feedback", "rating": "down"}),
            },
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "⭐ 收藏"},
                "type": "default",
                "value": json.dumps({"action": "star", "question": question}),
            },
        ],
    })

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": "💬 知识问答"},
            "template": "blue",
        },
        "elements": elements,
    }


def review_card(entity_name: str, relations: list[str], related_docs: list[str]) -> dict:
    """Build a Feishu card for daily review."""
    elements = []

    # Entity
    elements.append({
        "tag": "div",
        "text": {
            "tag": "lark_md",
            "content": f"**📌 {entity_name}**\n回忆一下这个知识点...",
        },
    })
    elements.append({"tag": "hr"})

    # Relations (hidden, like Anki back)
    if relations:
        rel_lines = ["**核心关系:**"]
        for r in relations[:3]:
            rel_lines.append(f"• {r}")
        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": "\n".join(rel_lines),
            },
        })

    if related_docs:
        elements.append({"tag": "hr"})
        doc_lines = ["**相关文档:**"]
        for d in related_docs[:3]:
            doc_lines.append(f"• {d}")
        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": "\n".join(doc_lines),
            },
        })

    # Review actions
    elements.append({
        "tag": "action",
        "actions": [
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "✅ 简单"},
                "type": "primary",
                "value": json.dumps({"action": "review_easy", "entity": entity_name}),
            },
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "🤔 困难"},
                "type": "default",
                "value": json.dumps({"action": "review_hard", "entity": entity_name}),
            },
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "⏭️ 跳过"},
                "type": "default",
                "value": json.dumps({"action": "review_skip", "entity": entity_name}),
            },
        ],
    })

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": "📖 今日复习"},
            "template": "orange",
        },
        "elements": elements,
    }


def text_entity_card(text_tree: str) -> str:
    """Fallback: render entity info as plain text for simple reply."""
    return text_tree
