"""
Unified Research Query Service coordinating search retrieval and RAG synthesis.
"""

from typing import Dict, Any, Optional, List
from ..storage.db import FeedbackDatabase
from ..ai.groq_client import GroqClient
from .indexer import ResearchSearchIndex
from .synthesizer import EvidenceSynthesizer


class ResearchQueryService:
    """Entry point for natural-language discovery research queries."""

    def __init__(self, db: Optional[FeedbackDatabase] = None, groq_client: Optional[GroqClient] = None):
        self.db = db or FeedbackDatabase()
        self.groq_client = groq_client or GroqClient()
        self.index = ResearchSearchIndex(self.db)
        self.synthesizer = EvidenceSynthesizer(self.groq_client)

    @property
    def search_index(self) -> ResearchSearchIndex:
        """Alias for self.index."""
        return self.index

    def refresh_index(self):
        """Reload and rebuild search index from latest DB state."""
        self.index.build_index()

    def ask(
        self,
        query: str,
        category: Optional[str] = None,
        theme: Optional[str] = None,
        top_k: int = 5
    ) -> Dict[str, Any]:
        """Execute hybrid search and synthesize evidence-backed answer."""
        retrieved_docs = self.index.search(
            query=query,
            category=category,
            theme=theme,
            top_k=top_k
        )
        return self.synthesizer.synthesize(query=query, evidence_docs=retrieved_docs)

    def search_records(
        self,
        query: str,
        category: Optional[str] = None,
        theme: Optional[str] = None,
        limit: int = 10,
        top_k: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Directly search and return evidence records."""
        actual_k = limit if limit is not None else (top_k or 10)
        return self.index.search(
            query=query,
            category=category,
            theme=theme,
            top_k=actual_k
        )

    def search_evidence(
        self,
        query: str,
        category: Optional[str] = None,
        theme: Optional[str] = None,
        limit: int = 10,
        category_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Alias for search_records."""
        cat = category or category_filter
        return self.search_records(query=query, category=cat, theme=theme, limit=limit)
