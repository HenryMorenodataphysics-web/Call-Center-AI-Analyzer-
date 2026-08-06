"""Business-scoped document ingestion and local knowledge storage."""

from .ingestion import KnowledgeIngestionError, KnowledgeIngestionService
from .repository import KnowledgeStore

__all__ = ["KnowledgeIngestionError", "KnowledgeIngestionService", "KnowledgeStore"]
