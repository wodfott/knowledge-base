"""Obsidian / local Markdown note importer."""

import logging
import re
from pathlib import Path
from datetime import datetime
from typing import Optional

from agents.collector import _process_and_save
from utils import clean_text, generate_doc_id, compute_simhash

logger = logging.getLogger(__name__)


def import_markdown_file(filepath: str | Path) -> dict:
    """Import a single Markdown file as a document.

    Handles Obsidian-style frontmatter (YAML between --- markers).
    """
    filepath = Path(filepath)
    if not filepath.exists():
        return {"status": "error", "message": f"File not found: {filepath}"}

    try:
        raw = filepath.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            raw = filepath.read_text(encoding="gbk")
        except Exception as e:
            return {"status": "error", "message": f"Encoding error: {e}"}

    # Parse title: prefer # Heading, then frontmatter title, then filename
    title = filepath.stem
    content_start = 0
    tags = []

    # Extract frontmatter
    frontmatter = {}
    if raw.startswith("---"):
        end = raw.find("---", 3)
        if end > 0:
            fm_text = raw[3:end].strip()
            content_start = end + 3
            for line in fm_text.split("\n"):
                if ":" in line:
                    k, v = line.split(":", 1)
                    frontmatter[k.strip()] = v.strip()
            if "title" in frontmatter:
                title = frontmatter["title"]
            if "tags" in frontmatter:
                tags_str = frontmatter["tags"]
                tags = [t.strip() for t in tags_str.strip("[]").split(",") if t.strip()]

    content = raw[content_start:].strip()

    # Extract first # heading as title if no frontmatter title
    heading_match = re.match(r"^#\s+(.+)$", content, re.MULTILINE)
    if heading_match and "title" not in frontmatter:
        title = heading_match.group(1).strip()

    # Clean markdown syntax for better text quality
    content = re.sub(r"^#+\s+", "", content, flags=re.MULTILINE)  # Strip headings
    content = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", content)   # Links → text
    content = re.sub(r"!\[.*?\]\([^)]+\)", "", content)            # Remove images
    content = re.sub(r"`{1,3}[^`]*`{1,3}", "", content)           # Remove inline code
    content = content.replace("*", "").replace("_", "")            # Strip emphasis
    content = content.replace("~~", "")                             # Strip strikethrough
    content = clean_text(content)

    if not content:
        return {"status": "error", "message": f"No content in {filepath}"}

    return _process_and_save(
        title=title,
        content=content,
        source_type="obsidian",
        source_url=str(filepath),
        tags=tags,
    )


def import_folder(folder_path: str, recursive: bool = True) -> dict:
    """Import all Markdown files from a folder (e.g. Obsidian vault)."""
    folder = Path(folder_path)
    if not folder.is_dir():
        return {"status": "error", "message": f"Not a directory: {folder_path}"}

    pattern = "**/*.md" if recursive else "*.md"
    md_files = list(folder.glob(pattern))

    # Skip certain Obsidian system folders
    skip_dirs = {".obsidian", ".trash", ".git", "node_modules", "__pycache__"}
    md_files = [f for f in md_files if not any(s in f.parts for s in skip_dirs)]

    results = {"total": len(md_files), "created": 0, "duplicate": 0, "error": 0, "files": []}

    for f in md_files:
        result = import_markdown_file(f)
        status = result.get("status", "error")
        results[status] = results.get(status, 0) + 1
        if status == "created":
            results["files"].append({
                "path": str(f),
                "title": result.get("title", f.stem),
                "doc_id": result.get("id", ""),
            })

    logger.info(f"Folder import: {results['total']} files, {results['created']} new, {results['duplicate']} dupes")
    return results
