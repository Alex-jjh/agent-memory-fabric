"""Markdown file storage — source of truth for memory nodes."""

from __future__ import annotations

import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml

from agent_memory_fabric.core.node import LifecycleState, MemoryNode, MemoryType

_UNSAFE_PATH_CHARS = re.compile(r"[^\w\s\-]", re.UNICODE)


def _sanitize_path_component(name: str) -> str:
    """Sanitize a string for safe use as a filesystem path component."""
    name = name.replace("/", "-").replace("\\", "-").replace("\x00", "")
    name = name.replace("..", "")
    name = _UNSAFE_PATH_CHARS.sub("", name)
    return name.strip(". ")[:100] or "unnamed"


class MarkdownStore:
    """Reads/writes MemoryNodes as Markdown files with YAML frontmatter.

    File layout:
        vault_path/
        ├── _global/          (Global scope memories)
        ├── projects/
        │   └── {project}/    (Project scope memories)
        └── _sessions/        (Session scratch, auto-cleanup)
    """

    def __init__(self, vault_path: Path):
        self.vault_path = vault_path
        self._id_to_path: dict[str, Path] = {}

    def _ensure_dirs(self) -> None:
        (self.vault_path / "_global").mkdir(parents=True, exist_ok=True)
        (self.vault_path / "projects").mkdir(parents=True, exist_ok=True)
        (self.vault_path / "_sessions").mkdir(parents=True, exist_ok=True)

    def resolve_path(self, node: MemoryNode) -> Path:
        safe_name = _sanitize_path_component(node.name)
        if node.project:
            safe_project = _sanitize_path_component(node.project)
            path = self.vault_path / "projects" / safe_project / f"{safe_name}.md"
        else:
            path = self.vault_path / "_global" / f"{safe_name}.md"
        if not path.resolve().is_relative_to(self.vault_path.resolve()):
            raise ValueError(f"Path traversal detected: {node.name}")
        return path

    def _serialize(self, node: MemoryNode) -> str:
        frontmatter = {
            "id": node.id,
            "name": node.name,
            "state": node.state.value,
            "type": node.type.value,
            "created": node.created.isoformat(),
            "modified": node.modified.isoformat(),
            "last_accessed": node.last_accessed.isoformat(),
            "access_count": node.access_count,
            "decay_score": node.decay_score,
            "strength": node.strength,
            "confidence_alpha": node.confidence_alpha,
            "confidence_beta": node.confidence_beta,
            "tags": node.tags,
            "links": node.links,
        }
        if node.project:
            frontmatter["project"] = node.project
        if node.ttl:
            frontmatter["ttl"] = node.ttl.isoformat()

        fm_str = yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True, sort_keys=False)
        return f"---\n{fm_str}---\n{node.content}\n"

    def _deserialize(self, text: str, file_path: Path) -> MemoryNode:
        parts = text.split("---", 2)
        if len(parts) < 3:
            raise ValueError(f"Invalid frontmatter in {file_path}")

        fm_raw = parts[1].strip()
        content = parts[2].strip()
        data = yaml.safe_load(fm_raw)

        return MemoryNode(
            id=data["id"],
            name=data["name"],
            content=content,
            state=LifecycleState(data.get("state", "active")),
            type=MemoryType(data.get("type", "project")),
            project=data.get("project"),
            created=datetime.fromisoformat(data["created"]),
            modified=datetime.fromisoformat(data["modified"]),
            last_accessed=datetime.fromisoformat(data["last_accessed"]),
            access_count=data.get("access_count", 0),
            decay_score=data.get("decay_score", 1.0),
            strength=data.get("strength", 1.0),
            confidence_alpha=data.get("confidence_alpha", 1.0),
            confidence_beta=data.get("confidence_beta", 1.0),
            ttl=datetime.fromisoformat(data["ttl"]) if data.get("ttl") else None,
            tags=data.get("tags", []),
            links=data.get("links", []),
        )

    def write(self, node: MemoryNode) -> Path:
        self._ensure_dirs()
        file_path = self.resolve_path(node)
        file_path.parent.mkdir(parents=True, exist_ok=True)

        content = self._serialize(node)

        fd, tmp_path = tempfile.mkstemp(dir=file_path.parent, suffix=".tmp")
        closed = False
        try:
            os.write(fd, content.encode("utf-8"))
            os.close(fd)
            closed = True
            os.replace(tmp_path, file_path)
        except Exception:
            if not closed:
                os.close(fd)
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

        self._id_to_path[node.id] = file_path
        return file_path

    def read(self, node_id: str) -> Optional[MemoryNode]:
        if node_id in self._id_to_path:
            path = self._id_to_path[node_id]
            if path.exists():
                return self.read_by_path(path)
            else:
                del self._id_to_path[node_id]

        for md_file in self.vault_path.rglob("*.md"):
            try:
                node = self.read_by_path(md_file)
                self._id_to_path[node.id] = md_file
                if node.id == node_id:
                    return node
            except (ValueError, KeyError, TypeError, yaml.YAMLError):
                continue
        return None

    def read_by_path(self, path: Path) -> MemoryNode:
        text = path.read_text(encoding="utf-8")
        return self._deserialize(text, path)

    def delete(self, node_id: str) -> bool:
        node = self.read(node_id)
        if node is None:
            return False
        path = self._id_to_path.get(node_id)
        if path and path.exists():
            path.unlink()
            del self._id_to_path[node_id]
            return True
        return False

    def list_all(self, scope: str | None = None) -> list[MemoryNode]:
        self._ensure_dirs()
        nodes: list[MemoryNode] = []

        if scope:
            search_dir = self.vault_path / "projects" / scope
        else:
            search_dir = self.vault_path

        for md_file in search_dir.rglob("*.md"):
            if md_file.name.startswith("."):
                continue
            try:
                node = self.read_by_path(md_file)
                self._id_to_path[node.id] = md_file
                nodes.append(node)
            except (ValueError, KeyError, TypeError, yaml.YAMLError):
                continue

        return nodes
