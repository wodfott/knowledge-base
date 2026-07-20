"""LLM client using DeepSeek Chat API."""

import json
from typing import Optional
from openai import OpenAI

from config import settings


class LLMClient:
    """Wrapper around DeepSeek Chat API for extraction, QA, etc."""

    def __init__(self):
        self.client = OpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
        )
        self.model = settings.deepseek_chat_model

    def chat(
        self,
        messages: list[dict],
        temperature: float = 0.3,
        max_tokens: int = 2048,
        response_format: Optional[dict] = None,
    ) -> str:
        """Send a chat completion request."""
        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format:
            kwargs["response_format"] = response_format

        response = self.client.chat.completions.create(**kwargs)
        return response.choices[0].message.content

    def chat_json(
        self,
        messages: list[dict],
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> dict:
        """Send a chat completion request, parse JSON response."""
        text = self.chat(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
        return json.loads(text)

    def extract_entities(self, text: str) -> list[dict]:
        """Extract entities from text using LLM."""
        prompt = f"""Extract all meaningful entities from the following text.
For each entity, identify its name and type from these categories:
Person, Organization, Technology, Concept, Tool, Framework, Language, Platform, Event, Location, Product, Methodology, Other.

Output as JSON with 'entities' array:
{{"entities": [{{"name": "...", "type": "...", "description": "..."}}]}}

Text:
{text[:4000]}
"""
        result = self.chat_json([
            {"role": "system", "content": "You are a precise entity extraction system. Extract entities accurately and output valid JSON only."},
            {"role": "user", "content": prompt},
        ])
        return result.get("entities", [])

    def extract_relations(self, text: str, entities: list[dict]) -> list[dict]:
        """Extract relationships between entities from text."""
        entity_names = [e["name"] for e in entities]
        prompt = f"""Given the text and identified entities, extract relationships between them.
Relation types: uses, implements, depends_on, part_of, prerequisite_of, supports, related_to, derives_from, applied_to, builds_on, conflicts_with, supersedes.

Entities: {json.dumps(entity_names, ensure_ascii=False)}

Output as JSON with 'relations' array:
{{"relations": [{{"source": "entity_name", "target": "entity_name", "type": "relation_type", "evidence": "quote from text"}}]}}

Text:
{text[:3000]}
"""
        result = self.chat_json([
            {"role": "system", "content": "You are a precise relationship extraction system. Only output relationships explicitly mentioned in the text."},
            {"role": "user", "content": prompt},
        ])
        return result.get("relations", [])

    def answer_question(self, question: str, context_chunks: list[str]) -> str:
        """Answer a question based on retrieved context chunks."""
        context_text = "\n\n---\n\n".join(context_chunks)
        prompt = f"""Answer the question based on the following knowledge base excerpts. If the knowledge base doesn't contain enough information, say so.

Knowledge Base:
{context_text}

Question: {question}

Provide a concise, accurate answer. Cite specific sources when possible."""
        return self.chat([
            {"role": "system", "content": "You are a personal knowledge assistant. Answer based only on the knowledge base. Never say '上下文' — say '知识库' instead. Be concise and accurate."},
            {"role": "user", "content": prompt},
        ])

    def expand_query(self, question: str) -> list[str]:
        """Expand a query: fix typos, extract key terms, generate search variations."""
        prompt = f"""The user asked: "{question}"

Your task: generate 3-5 alternative search queries to find relevant documents in a knowledge base. Fix any typos. Extract key concepts. Use different phrasings.

Output as JSON:
{{"queries": ["corrected query", "alternative phrasing", "keyword list"]}}"""
        try:
            result = self.chat_json([
                {"role": "system", "content": "You are a query expansion engine. Fix typos and generate search variants. Output valid JSON only."},
                {"role": "user", "content": prompt},
            ])
            return result.get("queries", [question])
        except Exception:
            return [question]

    def generate_flashcard_qa(self, entity_name: str, entity_type: str, description: str, context: str) -> dict:
        """Generate a question-answer pair for spaced-repetition flashcard."""
        prompt = f"""Create a high-quality flashcard for spaced repetition learning.

Entity: {entity_name}
Type: {entity_type}
Description: {description}

Context (from knowledge base):
{context[:2000]}

Generate ONE flashcard with:
- "front": A challenging question that tests recall of this concept. Make it specific and concrete, not vague. The question should require deep understanding, not just recognition.
- "back": A concise, informative answer (2-4 sentences) that directly answers the question.
- "hint": A short clue (one phrase) to help if stuck.

Output as JSON:
{{"front": "...", "back": "...", "hint": "..."}}"""
        return self.chat_json([
            {"role": "system", "content": "You are a expert spaced-repetition flashcard creator. Create cards that promote active recall. Output valid JSON only."},
            {"role": "user", "content": prompt},
        ])

    def generate_answer_card(self, answer: str, sources: list[dict]) -> dict:
        """Generate structured card data for Feishu card response."""
        prompt = f"""Format this Q&A into a concise Feishu card-friendly summary.

Question: {sources[0].get('question', '') if sources else ''}
Answer: {answer}

Create a brief summary (within 200 chars) and key points (max 3 bullet points).

Output as JSON:
{{"summary": "...", "key_points": ["...", "...", "..."], "tags": ["..."]}}"""
        return self.chat_json([
            {"role": "system", "content": "You are a content formatter. Output valid JSON only."},
            {"role": "user", "content": prompt},
        ])


# Singleton
llm_client = LLMClient()
