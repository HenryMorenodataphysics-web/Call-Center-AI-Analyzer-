"""Business-scoped lexical retriever for checked-in and uploaded policies."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from src.knowledge.repository import KnowledgeStore


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_KNOWLEDGE_DIR = PROJECT_ROOT / "knowledge_base"
DEFAULT_BUSINESS_ID = "demo_customer_service"
TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)


def tokens(text: str) -> set[str]:
    stop = {
        "the",
        "and",
        "for",
        "with",
        "that",
        "this",
        "para",
        "con",
        "que",
        "una",
        "los",
        "las",
        "del",
    }
    return {token.casefold() for token in TOKEN_RE.findall(text) if token.casefold() not in stop}


@dataclass(frozen=True)
class KnowledgeChunk:
    document: str
    heading: str
    text: str
    locator: str
    business_id: str = DEFAULT_BUSINESS_ID
    document_id: str = "portfolio_demo"
    version: str = "demo"
    page: int | None = None
    source_type: str = "portfolio_demo_policy"
    chunk_id: str = ""


class PolicyRetriever:
    def __init__(
        self,
        knowledge_dir: Path = DEFAULT_KNOWLEDGE_DIR,
        business_id: str = DEFAULT_BUSINESS_ID,
        runtime_root: Path | None = None,
    ):
        self.knowledge_dir = knowledge_dir
        self.store = KnowledgeStore(storage_root=runtime_root)
        self.business_id = self.store.validate_business_id(business_id)
        self.chunks = self._load_chunks()

    def _load_portfolio_chunks(self) -> list[KnowledgeChunk]:
        if self.business_id != DEFAULT_BUSINESS_ID:
            return []
        chunks: list[KnowledgeChunk] = []
        policy_paths = (
            path
            for path in sorted(self.knowledge_dir.glob("*.md"))
            if path.name.casefold() != "readme.md"
        )
        for path in policy_paths:
            current_heading = path.stem.replace("_", " ").title()
            body: list[str] = []
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.startswith("## "):
                    if body:
                        chunks.append(
                            KnowledgeChunk(
                                path.name,
                                current_heading,
                                " ".join(body).strip(),
                                f"{path.relative_to(PROJECT_ROOT).as_posix()}#{current_heading.casefold().replace(' ', '-')}",
                            )
                        )
                    current_heading = line[3:].strip()
                    body = []
                elif line and not line.startswith("# "):
                    body.append(line.strip())
            if body:
                chunks.append(
                    KnowledgeChunk(
                        path.name,
                        current_heading,
                        " ".join(body).strip(),
                        f"{path.relative_to(PROJECT_ROOT).as_posix()}#{current_heading.casefold().replace(' ', '-')}",
                    )
                )
        return chunks

    def _load_uploaded_chunks(self) -> list[KnowledgeChunk]:
        chunks: list[KnowledgeChunk] = []
        for row in self.store.list_chunks(self.business_id, approved_only=True):
            page = row.get("page")
            page_label = f"page-{page}" if page is not None else "section"
            chunks.append(
                KnowledgeChunk(
                    document=row["source_filename"],
                    heading=row["title"],
                    text=row["text"],
                    locator=(
                        f"kb://{self.business_id}/{row['document_id']}/"
                        f"{page_label}#{row['chunk_id']}"
                    ),
                    business_id=self.business_id,
                    document_id=row["document_id"],
                    version=row["version"],
                    page=page,
                    source_type="approved_uploaded_policy",
                    chunk_id=row["chunk_id"],
                )
            )
        return chunks

    def _load_chunks(self) -> list[KnowledgeChunk]:
        return self._load_portfolio_chunks() + self._load_uploaded_chunks()

    def search(self, query: str, limit: int = 3) -> list[KnowledgeChunk]:
        query_tokens = tokens(query)
        scored: list[tuple[float, KnowledgeChunk]] = []
        for chunk in self.chunks:
            heading_tokens = tokens(chunk.heading)
            body_tokens = tokens(chunk.text)
            metadata_tokens = tokens(
                f"{chunk.document} {chunk.business_id} {chunk.version}"
            )
            score = (
                3 * len(query_tokens & heading_tokens)
                + len(query_tokens & body_tokens)
                + len(query_tokens & metadata_tokens)
            )
            if score:
                scored.append((score, chunk))
        if not scored:
            scored = [
                (1, chunk)
                for chunk in self.chunks
                if chunk.heading in {"Unsupported requests", "Safe efficiency"}
            ]
        scored.sort(key=lambda item: (-item[0], item[1].document, item[1].heading))
        return [chunk for _, chunk in scored[:limit]]
