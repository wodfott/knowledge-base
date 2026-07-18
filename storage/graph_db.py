"""NetworkX-based graph database for knowledge graph storage."""

import json
import networkx as nx
from pathlib import Path
from datetime import datetime
from typing import Optional, Any

from config import settings


class GraphDB:
    """NetworkX + JSON-backed knowledge graph store."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or settings.graph_db_path
        self._graph = nx.MultiDiGraph()
        self._load()

    def _load(self):
        """Load graph from JSON file."""
        path = Path(self.db_path)
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            self._graph = nx.node_link_graph(data, edges="links")
        else:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            self._save()

    def _save(self):
        """Persist graph to JSON file."""
        data = nx.node_link_data(self._graph, edges="links")
        Path(self.db_path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    # --- Node operations ---
    def add_entity(
        self,
        entity_id: str,
        name: str,
        entity_type: str,
        description: Optional[str] = None,
        confidence: float = 1.0,
        source_doc_ids: Optional[list[str]] = None,
        metadata: Optional[dict] = None,
        **kwargs,
    ):
        """Add or update an entity node."""
        self._graph.add_node(
            entity_id,
            name=name,
            type=entity_type,
            description=description or "",
            confidence=confidence,
            source_doc_ids=json.dumps(source_doc_ids or []),
            metadata=json.dumps(metadata or {}, ensure_ascii=False),
            updated_at=datetime.now().isoformat(),
            **kwargs,
        )
        self._save()

    def get_entity(self, entity_id: str) -> Optional[dict]:
        """Get entity by ID."""
        if entity_id in self._graph.nodes:
            return dict(self._graph.nodes[entity_id])
        return None

    def find_entity_by_name(self, name: str) -> Optional[dict]:
        """Find entity by name (case-insensitive)."""
        name_lower = name.lower()
        for node_id, data in self._graph.nodes(data=True):
            if data.get("name", "").lower() == name_lower:
                result = dict(data)
                result["id"] = node_id
                return result
        return None

    def has_entity(self, entity_id: str) -> bool:
        return entity_id in self._graph.nodes

    # --- Edge operations ---
    def add_relation(
        self,
        source_id: str,
        target_id: str,
        relation_type: str,
        relation_id: Optional[str] = None,
        confidence: float = 1.0,
        source_doc_ids: Optional[list[str]] = None,
        evidence: Optional[str] = None,
        metadata: Optional[dict] = None,
    ):
        """Add a relation edge between two entities."""
        self._graph.add_edge(
            source_id,
            target_id,
            key=relation_id or f"{source_id}_{relation_type}_{target_id}",
            type=relation_type,
            confidence=confidence,
            source_doc_ids=json.dumps(source_doc_ids or []),
            evidence=evidence or "",
            metadata=json.dumps(metadata or {}, ensure_ascii=False),
            created_at=datetime.now().isoformat(),
        )
        self._save()

    # --- Query operations ---
    def get_neighbors(self, entity_id: str, max_depth: int = 1) -> dict:
        """Get entity and its neighbors up to max_depth hops."""
        if entity_id not in self._graph.nodes:
            return {"entity": None, "neighbors": []}

        entity_data = dict(self._graph.nodes[entity_id])
        entity_data["id"] = entity_id

        neighbors = []
        visited = {entity_id}

        for depth in range(1, max_depth + 1):
            new_neighbors = set()
            for node in list(visited):
                for _, neighbor, edge_data in self._graph.edges(node, data=True):
                    if neighbor not in visited:
                        neighbor_data = dict(self._graph.nodes[neighbor])
                        neighbor_data["id"] = neighbor
                        neighbor_data["relation"] = {
                            "type": edge_data.get("type", "related_to"),
                            "confidence": edge_data.get("confidence", 1.0),
                            "evidence": edge_data.get("evidence", ""),
                            "direction": "outgoing",
                        }
                        neighbors.append(neighbor_data)
                        new_neighbors.add(neighbor)
                for predecessor, _, edge_data in self._graph.in_edges(node, data=True):
                    if predecessor not in visited:
                        predecessor_data = dict(self._graph.nodes[predecessor])
                        predecessor_data["id"] = predecessor
                        predecessor_data["relation"] = {
                            "type": edge_data.get("type", "related_to"),
                            "confidence": edge_data.get("confidence", 1.0),
                            "evidence": edge_data.get("evidence", ""),
                            "direction": "incoming",
                        }
                        neighbors.append(predecessor_data)
                        new_neighbors.add(predecessor)
            visited.update(new_neighbors)

        return {"entity": entity_data, "neighbors": neighbors}

    def search_entities(self, query: str, max_results: int = 10) -> list[dict]:
        """Simple name-based entity search."""
        query_lower = query.lower()
        results = []
        for node_id, data in self._graph.nodes(data=True):
            name = data.get("name", "")
            if query_lower in name.lower():
                r = dict(data)
                r["id"] = node_id
                results.append(r)
        return results[:max_results]

    def get_all_entities(self) -> list[dict]:
        """Get all entities."""
        results = []
        for node_id, data in self._graph.nodes(data=True):
            r = dict(data)
            r["id"] = node_id
            results.append(r)
        return results

    def get_all_relations(self) -> list[dict]:
        """Get all relations."""
        results = []
        for source, target, edge_data in self._graph.edges(data=True):
            r = dict(edge_data)
            r["source"] = source
            r["source_name"] = self._graph.nodes[source].get("name", source)
            r["target"] = target
            r["target_name"] = self._graph.nodes[target].get("name", target)
            results.append(r)
        return results

    def build_text_tree(self, entity_id: str, max_depth: int = 1) -> str:
        """Build a text-based tree representation for card display."""
        result = self.get_neighbors(entity_id, max_depth)
        if not result["entity"]:
            return f"实体不存在: {entity_id}"

        entity = result["entity"]
        lines = [
            f"📌 {entity.get('name', entity_id)} [{entity.get('type', 'Unknown')}]",
            f"   {entity.get('description', '无描述')[:120]}",
            "",
        ]

        if result["neighbors"]:
            lines.append("🔗 关联实体:")
            by_type = {}
            for n in result["neighbors"]:
                rel_type = n.get("relation", {}).get("type", "related_to")
                if rel_type not in by_type:
                    by_type[rel_type] = []
                by_type[rel_type].append(n)

            for rel_type, items in by_type.items():
                lines.append(f"  ── {rel_type} ──")
                for item in items[:5]:
                    direction = "→" if item.get("relation", {}).get("direction") == "outgoing" else "←"
                    lines.append(f"    {direction} {item.get('name', '?')} [{item.get('type', '?')}]")

        return "\n".join(lines)

    @property
    def entity_count(self) -> int:
        return self._graph.number_of_nodes()

    @property
    def relation_count(self) -> int:
        return self._graph.number_of_edges()


# Singleton
graph_db = GraphDB()
