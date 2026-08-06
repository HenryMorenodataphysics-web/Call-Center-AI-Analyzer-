"""Safe local persistence for uploaded knowledge documents and chunks."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONTRACT_PATH = PROJECT_ROOT / "config" / "knowledge_ingestion_contract_v1.json"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


class KnowledgeStore:
    """Persist registries and chunk indexes beneath one validated local root."""

    def __init__(
        self,
        storage_root: Path | None = None,
        contract_path: Path = DEFAULT_CONTRACT_PATH,
    ):
        self.contract = read_json(contract_path)
        configured = PROJECT_ROOT / self.contract["storage_root"]
        self.storage_root = (storage_root or configured).resolve()
        self.business_pattern = re.compile(self.contract["business_id_pattern"])

    def validate_business_id(self, business_id: str) -> str:
        normalized = business_id.strip().casefold()
        if not self.business_pattern.fullmatch(normalized):
            raise ValueError(
                "Business ID must start with a letter and contain only lowercase "
                "letters, numbers, underscores, or hyphens."
            )
        return normalized

    def business_root(self, business_id: str) -> Path:
        normalized = self.validate_business_id(business_id)
        target = (self.storage_root / normalized).resolve()
        if self.storage_root != target and self.storage_root not in target.parents:
            raise ValueError("Resolved business storage escaped the approved root")
        return target

    def registry_path(self, business_id: str) -> Path:
        return self.business_root(business_id) / "registry.json"

    def chunks_path(self, business_id: str) -> Path:
        return self.business_root(business_id) / "chunks.jsonl"

    def source_path(self, business_id: str, document_id: str, suffix: str) -> Path:
        return self.business_root(business_id) / "documents" / document_id / f"source{suffix}"

    def read_registry(self, business_id: str) -> dict[str, Any]:
        normalized = self.validate_business_id(business_id)
        path = self.registry_path(normalized)
        if not path.exists():
            return {
                "schema_version": "knowledge_registry_v1",
                "business_id": normalized,
                "documents": [],
            }
        payload = read_json(path)
        if payload.get("business_id") != normalized:
            raise ValueError("Knowledge registry business ID does not match its directory")
        return payload

    def list_documents(self, business_id: str) -> list[dict[str, Any]]:
        return list(self.read_registry(business_id)["documents"])

    def list_chunks(
        self, business_id: str, approved_only: bool = True
    ) -> list[dict[str, Any]]:
        path = self.chunks_path(business_id)
        if not path.exists():
            return []
        rows = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if approved_only:
            rows = [row for row in rows if row["approval_status"] == "approved_demo"]
        return rows

    @staticmethod
    def _atomic_text_write(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(path)

    def add_document(
        self,
        business_id: str,
        document: dict[str, Any],
        chunks: list[dict[str, Any]],
    ) -> None:
        registry = self.read_registry(business_id)
        if any(
            item["document_id"] == document["document_id"]
            for item in registry["documents"]
        ):
            raise ValueError("This document version and content are already registered")

        registry["documents"].append(document)
        registry["documents"].sort(key=lambda item: (item["title"], item["version"]))
        self._atomic_text_write(
            self.registry_path(business_id),
            json.dumps(registry, indent=2, ensure_ascii=False) + "\n",
        )

        existing = self.list_chunks(business_id, approved_only=False)
        combined = existing + chunks
        content = "".join(
            json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
            for row in combined
        )
        self._atomic_text_write(self.chunks_path(business_id), content)
