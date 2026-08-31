"""
BM25 Search Indexer and Hybrid Retrieval Engine for Feedback Records.
"""

import math
import re
from typing import List, Dict, Any, Optional
from ..storage.db import FeedbackDatabase


def tokenize_text(text: str) -> List[str]:
    """Tokenize, lowercase, and sanitize text into word tokens."""
    if not text:
        return []
    cleaned = re.sub(r"[^\w\s]", " ", text.lower())
    return [w for w in cleaned.split() if len(w) > 1]


class ResearchSearchIndex:
    """In-memory BM25 index built from DuckDB raw & behavioral feedback records."""

    def __init__(self, db: Optional[FeedbackDatabase] = None):
        self.db = db or FeedbackDatabase()
        self.documents: List[Dict[str, Any]] = []
        self.doc_lengths: List[int] = []
        self.avg_doc_length: float = 0.0
        self.doc_token_counts: List[Dict[str, int]] = []
        self.idf_cache: Dict[str, float] = {}
        self.total_docs: int = 0
        self.build_index()

    def build_index(self):
        """Construct the inverted index and BM25 statistics from DuckDB."""
        conn = self.db.get_connection()
        try:
            query = """
                SELECT r.record_id, r.source, r.source_url, r.date, r.raw_text, r.cleaned_text,
                       r.product_category, b.theme, b.verbatim_evidence, b.purchase_blocker,
                       b.information_gap, b.confidence_score, b.wishlist_intent
                FROM raw_feedback r
                LEFT JOIN behavioral_records b ON r.record_id = b.record_id
                WHERE r.is_duplicate = FALSE;
            """
            df = conn.execute(query).fetchdf()

            self.documents = df.to_dict(orient="records")
            self.total_docs = len(self.documents)
            self.doc_lengths = []
            self.doc_token_counts = []
            doc_freq: Dict[str, int] = {}

            total_tokens = 0
            for doc in self.documents:
                searchable_content = f"{doc.get('raw_text', '')} {doc.get('verbatim_evidence', '')} {doc.get('product_category', '')} {doc.get('theme', '')}"
                tokens = tokenize_text(searchable_content)
                doc_len = len(tokens)
                self.doc_lengths.append(doc_len)
                total_tokens += doc_len

                counts: Dict[str, int] = {}
                for t in tokens:
                    counts[t] = counts.get(t, 0) + 1
                self.doc_token_counts.append(counts)

                for unique_token in set(tokens):
                    doc_freq[unique_token] = doc_freq.get(unique_token, 0) + 1

            self.idf_cache = {}
            for token, freq in doc_freq.items():
                self.idf_cache[token] = math.log(1 + (self.total_docs - freq + 0.5) / (freq + 0.5))

            self.avg_doc_length = total_tokens / self.total_docs if self.total_docs > 0 else 1.0
        finally:
            conn.close()

    def search(
        self,
        query: str,
        category: Optional[str] = None,
        theme: Optional[str] = None,
        top_k: int = 5,
        k1: float = 1.5,
        b: float = 0.75
    ) -> List[Dict[str, Any]]:
        """
        Hybrid BM25 search with metadata filtering.
        """
        if self.total_docs == 0:
            self.build_index()

        if self.total_docs == 0:
            return []

        query_tokens = tokenize_text(query)
        if not query_tokens:
            return []

        scores: List[float] = [0.0] * self.total_docs

        for idx, doc in enumerate(self.documents):
            # Metadata filter: Category
            if category and category != "ALL" and doc.get("product_category", "").upper() != category.upper():
                continue

            # Metadata filter: Theme
            if theme and theme != "ALL" and doc.get("theme", "").upper() != theme.upper():
                continue

            doc_counts = self.doc_token_counts[idx]
            doc_len = self.doc_lengths[idx]

            doc_score = 0.0
            for token in query_tokens:
                if token not in doc_counts:
                    continue
                tf = doc_counts[token]
                idf = self.idf_cache.get(token, 0.0)
                numerator = tf * (k1 + 1)
                denominator = tf + k1 * (1 - b + b * (doc_len / self.avg_doc_length))
                doc_score += idf * (numerator / denominator)

            scores[idx] = doc_score

        # Rank documents by score
        ranked_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)

        results = []
        for idx in ranked_indices:
            if scores[idx] <= 0.0:
                break
            doc_copy = dict(self.documents[idx])
            doc_copy["bm25_score"] = round(scores[idx], 4)
            doc_copy["text"] = doc_copy.get("raw_text", "")
            results.append(doc_copy)
            if len(results) >= top_k:
                break

        return results
