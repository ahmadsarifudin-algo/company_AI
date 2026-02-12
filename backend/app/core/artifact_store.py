"""
ArtifactStore — External storage for agent output artifacts.

Agents should NOT store large payloads inline in state. Instead, they
store results here and keep only an ArtifactRef in the state dict.

Default implementation: filesystem-backed (data/artifacts/{trace_id}/{name}).
Can be swapped for S3, GCS, or DB blob in production.
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger()

# Default storage root
_ARTIFACT_ROOT = os.environ.get("ARTIFACT_STORE_ROOT", "data/artifacts")


class ArtifactStore:
    """Filesystem-backed artifact store.

    Stores JSON artifacts to disk, returns a reference dict (ArtifactRef-style).
    """

    def __init__(self, root: str | None = None) -> None:
        self.root = Path(root or _ARTIFACT_ROOT)
        self.root.mkdir(parents=True, exist_ok=True)

    async def put_json(
        self,
        *,
        trace_id: str,
        task_id: str,
        name: str,
        content: dict[str, Any] | list[Any],
        sensitivity: str = "internal",
    ) -> dict[str, Any]:
        """Store a JSON artifact and return its reference.

        Args:
            trace_id: Trace ID for directory scoping.
            task_id: Task ID for metadata.
            name: Artifact filename (e.g. "accounting_result.json").
            content: JSON-serializable content to store.
            sensitivity: Data classification (public/internal/confidential/pii).

        Returns:
            ArtifactRef-like dict with id, path, type, sensitivity.
        """
        artifact_id = f"art-{uuid.uuid4().hex[:12]}"
        artifact_dir = self.root / trace_id
        artifact_dir.mkdir(parents=True, exist_ok=True)

        file_path = artifact_dir / name
        data = json.dumps(content, indent=2, default=str)
        file_path.write_text(data, encoding="utf-8")

        ref = {
            "id": artifact_id,
            "type": "json",
            "name": name,
            "path": str(file_path),
            "task_id": task_id,
            "trace_id": trace_id,
            "sensitivity": sensitivity,
            "size_bytes": len(data),
        }

        logger.debug("artifact_stored", artifact_id=artifact_id, path=str(file_path))
        return ref

    async def get_json(self, path: str) -> dict[str, Any] | list[Any]:
        """Read a JSON artifact from disk."""
        return json.loads(Path(path).read_text(encoding="utf-8"))


# ── Singleton ──────────────────────────
_artifact_store: ArtifactStore | None = None


def get_artifact_store(root: str | None = None) -> ArtifactStore:
    """Get the singleton ArtifactStore instance."""
    global _artifact_store
    if _artifact_store is None:
        _artifact_store = ArtifactStore(root)
    return _artifact_store
