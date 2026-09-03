"""
Exact and near-duplicate detection engine.
"""

from typing import List, Dict, Set, Tuple, Optional
from ..models.schema import NormalizedRecord


def tokenize_for_similarity(text: str) -> Set[str]:
    """Tokenize and create word shingles for Jaccard similarity."""
    words = [w.strip(".,!?:;\"'()[]{}").lower() for w in text.split()]
    return {w for w in words if len(w) > 2}


def compute_jaccard_similarity(set_a: Set[str], set_b: Set[str]) -> float:
    """Calculate Jaccard index between two token sets."""
    if not set_a or not set_b:
        return 0.0
    intersection = len(set_a.intersection(set_b))
    union = len(set_a.union(set_b))
    return intersection / union if union > 0 else 0.0


class Deduplicator:
    """Detects exact and fuzzy duplicate feedback records."""

    def __init__(self, fuzzy_threshold: float = 0.85):
        self.fuzzy_threshold = fuzzy_threshold
        self.seen_hashes: Dict[str, str] = {}  # text_hash -> canonical_record_id
        self.seen_tokens: Dict[str, Set[str]] = {}  # canonical_record_id -> token_set
        self.token_to_canon_ids: Dict[str, Set[str]] = {}  # token -> set of canonical_record_ids

    def process_record(self, record: NormalizedRecord) -> NormalizedRecord:
        """Evaluate a single record against indexed records for deduplication."""
        # 1. Exact match check (O(1))
        if record.text_hash in self.seen_hashes:
            record.is_duplicate = True
            record.canonical_record_id = self.seen_hashes[record.text_hash]
            return record

        # 2. Fuzzy match check with inverted index candidate filtering
        record_tokens = tokenize_for_similarity(record.cleaned_text)
        len_rec = len(record_tokens)

        if len_rec > 0 and self.token_to_canon_ids:
            min_hits_needed = max(1, int(len_rec * self.fuzzy_threshold))
            candidate_hits: Dict[str, int] = {}
            for token in record_tokens:
                if token in self.token_to_canon_ids:
                    for cid in self.token_to_canon_ids[token]:
                        candidate_hits[cid] = candidate_hits.get(cid, 0) + 1

            for canon_id, hits in candidate_hits.items():
                if hits < min_hits_needed:
                    continue
                existing_tokens = self.seen_tokens[canon_id]
                len_exist = len(existing_tokens)
                if min(len_rec, len_exist) / max(len_rec, len_exist) < self.fuzzy_threshold:
                    continue

                sim = compute_jaccard_similarity(record_tokens, existing_tokens)
                if sim >= self.fuzzy_threshold:
                    record.is_duplicate = True
                    record.canonical_record_id = canon_id
                    return record

        # New canonical record
        self.seen_hashes[record.text_hash] = record.record_id
        self.seen_tokens[record.record_id] = record_tokens
        for token in record_tokens:
            if token not in self.token_to_canon_ids:
                self.token_to_canon_ids[token] = set()
            self.token_to_canon_ids[token].add(record.record_id)

        record.is_duplicate = False
        record.canonical_record_id = record.record_id
        return record

    def process_batch(self, records: List[NormalizedRecord]) -> List[NormalizedRecord]:
        """Process a list of records in sequence."""
        return [self.process_record(r) for r in records]
