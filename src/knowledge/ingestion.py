"""LangChain-backed document extraction, chunking, and governed registration."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import docx2txt
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader

from .repository import DEFAULT_CONTRACT_PATH, KnowledgeStore, read_json


class KnowledgeIngestionError(ValueError):
    """Raised when a document cannot safely enter the local knowledge store."""


class KnowledgeIngestionService:
    PROMPT_INJECTION_PATTERNS = (
        "ignore previous instructions",
        "ignore system instructions",
        "reveal the system prompt",
        "disable citations",
        "reveal secrets",
    )

    def __init__(
        self,
        storage_root: Path | None = None,
        contract_path: Path = DEFAULT_CONTRACT_PATH,
    ):
        self.contract = read_json(contract_path)
        self.store = KnowledgeStore(storage_root=storage_root, contract_path=contract_path)
        chunking = self.contract["chunking"]
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=int(chunking["chunk_size"]),
            chunk_overlap=int(chunking["chunk_overlap"]),
            length_function=len,
            is_separator_regex=False,
        )

    def validate_metadata(self, metadata: dict[str, Any]) -> dict[str, str]:
        missing = [
            field
            for field in self.contract["required_metadata"]
            if not str(metadata.get(field, "")).strip()
        ]
        if missing:
            raise KnowledgeIngestionError(
                "Missing required metadata: " + ", ".join(sorted(missing))
            )
        try:
            business_id = self.store.validate_business_id(str(metadata["business_id"]))
        except ValueError as exc:
            raise KnowledgeIngestionError(str(exc)) from exc
        policy_type = str(metadata["policy_type"]).strip().casefold()
        if policy_type not in self.contract["allowed_policy_types"]:
            raise KnowledgeIngestionError(f"Unsupported policy type: {policy_type}")
        approval_status = str(metadata["approval_status"]).strip().casefold()
        if approval_status not in self.contract["approval_statuses"]:
            raise KnowledgeIngestionError(
                f"Unsupported approval status: {approval_status}"
            )
        effective_date = str(metadata["effective_date"]).strip()
        try:
            date.fromisoformat(effective_date)
        except ValueError as exc:
            raise KnowledgeIngestionError(
                "Effective date must use YYYY-MM-DD format"
            ) from exc
        version = str(metadata["version"]).strip()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,31}", version):
            raise KnowledgeIngestionError(
                "Version must contain only letters, numbers, dots, underscores, or hyphens"
            )
        return {
            "business_id": business_id,
            "title": str(metadata["title"]).strip()[:200],
            "policy_type": policy_type,
            "version": version,
            "effective_date": effective_date,
            "language": str(metadata["language"]).strip().casefold()[:20],
            "market": str(metadata["market"]).strip().casefold()[:60],
            "approval_status": approval_status,
        }

    def validate_file(self, filename: str, content: bytes) -> tuple[str, str]:
        safe_name = Path(filename).name
        if safe_name != filename or not safe_name:
            raise KnowledgeIngestionError("Filename must not contain a directory path")
        suffix = Path(safe_name).suffix.casefold()
        if suffix not in self.contract["allowed_extensions"]:
            raise KnowledgeIngestionError(
                "Unsupported file type. Allowed: "
                + ", ".join(self.contract["allowed_extensions"])
            )
        if not content:
            raise KnowledgeIngestionError("Uploaded document is empty")
        if len(content) > int(self.contract["max_file_bytes"]):
            raise KnowledgeIngestionError(
                f"Document exceeds the {int(self.contract['max_file_bytes']) // 1048576} MB limit"
            )
        return safe_name, suffix

    @staticmethod
    def _text_document(path: Path) -> list[Document]:
        try:
            text = path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError as exc:
            raise KnowledgeIngestionError("TXT and Markdown files must use UTF-8") from exc
        return [Document(page_content=text, metadata={"page": None})]

    @staticmethod
    def _pdf_documents(path: Path) -> list[Document]:
        try:
            reader = PdfReader(str(path))
            return [
                Document(
                    page_content=page.extract_text() or "",
                    metadata={"page": page_number},
                )
                for page_number, page in enumerate(reader.pages, start=1)
            ]
        except Exception as exc:
            raise KnowledgeIngestionError(f"PDF extraction failed: {exc}") from exc

    @staticmethod
    def _docx_document(path: Path) -> list[Document]:
        try:
            text = docx2txt.process(str(path)) or ""
        except Exception as exc:
            raise KnowledgeIngestionError(f"DOCX extraction failed: {exc}") from exc
        return [Document(page_content=text, metadata={"page": None})]

    def _extract(self, path: Path, suffix: str) -> list[Document]:
        if suffix in {".txt", ".md"}:
            documents = self._text_document(path)
        elif suffix == ".pdf":
            documents = self._pdf_documents(path)
        else:
            documents = self._docx_document(path)
        documents = [
            Document(page_content=document.page_content.strip(), metadata=document.metadata)
            for document in documents
            if document.page_content.strip()
        ]
        extracted = sum(len(document.page_content) for document in documents)
        if extracted < int(self.contract["minimum_extracted_characters"]):
            raise KnowledgeIngestionError(
                "Document contains too little extractable text. Scanned PDFs require OCR, "
                "which is not included in v1."
            )
        normalized_text = " ".join(
            document.page_content.casefold() for document in documents
        )
        if any(pattern in normalized_text for pattern in self.PROMPT_INJECTION_PATTERNS):
            raise KnowledgeIngestionError(
                "Document contains a possible prompt-injection instruction and cannot "
                "enter the approved local index. Review it outside the Copilot workflow."
            )
        return documents

    def ingest_bytes(
        self,
        filename: str,
        content: bytes,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        clean_metadata = self.validate_metadata(metadata)
        safe_name, suffix = self.validate_file(filename, content)
        fingerprint = hashlib.sha256(
            (
                clean_metadata["business_id"]
                + "|"
                + clean_metadata["version"]
                + "|"
                + safe_name.casefold()
            ).encode("utf-8")
            + content
        ).hexdigest()
        document_id = f"kb_{fingerprint[:20]}"
        source_path = self.store.source_path(
            clean_metadata["business_id"], document_id, suffix
        )
        source_path.parent.mkdir(parents=True, exist_ok=True)
        if source_path.exists():
            raise KnowledgeIngestionError(
                "This document version and content are already registered"
            )
        source_path.write_bytes(content)

        try:
            extracted = self._extract(source_path, suffix)
            chunks = self.splitter.split_documents(extracted)
            ingested_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
            chunk_rows: list[dict[str, Any]] = []
            for index, chunk in enumerate(chunks, start=1):
                page = chunk.metadata.get("page")
                chunk_rows.append(
                    {
                        **clean_metadata,
                        "document_id": document_id,
                        "chunk_id": f"{document_id}_chunk_{index:04d}",
                        "chunk_index": index,
                        "page": page,
                        "source_filename": safe_name,
                        "source_type": "uploaded_policy",
                        "ingested_at": ingested_at,
                        "text": chunk.page_content.strip(),
                    }
                )
            document_record = {
                **clean_metadata,
                "document_id": document_id,
                "source_filename": safe_name,
                "source_path": str(
                    source_path.relative_to(self.store.storage_root)
                ).replace("\\", "/"),
                "sha256": hashlib.sha256(content).hexdigest(),
                "bytes": len(content),
                "chunk_count": len(chunk_rows),
                "indexed_for_retrieval": clean_metadata["approval_status"]
                == "approved_demo",
                "ingested_at": ingested_at,
            }
            self.store.add_document(
                clean_metadata["business_id"], document_record, chunk_rows
            )
            return document_record
        except Exception:
            source_path.unlink(missing_ok=True)
            try:
                source_path.parent.rmdir()
            except OSError:
                pass
            raise

    def contract_summary(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract["contract_version"],
            "allowed_extensions": self.contract["allowed_extensions"],
            "max_file_bytes": self.contract["max_file_bytes"],
            "chunking": self.contract["chunking"],
            "guardrails": self.contract["guardrails"],
        }
