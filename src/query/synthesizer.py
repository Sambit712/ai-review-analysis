"""
Evidence-Grounded RAG Response Synthesizer.
"""

from typing import List, Dict, Any, Optional
from ..ai.groq_client import GroqClient


RAG_SYSTEM_PROMPT = """You are a senior qualitative researcher analyzing consumer feedback for an e-commerce beauty platform.
Your task is to answer the researcher's query based STRICTLY on the provided user evidence quotes and behavioral data.

### MANDATORY CITATION AND ACCURACY RULES:
1. Every conclusion or behavioral insight you state MUST be directly supported by the provided evidence records.
2. Cite the exact record ID and quote when making a claim (e.g., `[Record #SYN002: "I'm not sure which shade matches my undertone"]`).
3. NEVER invent, extrapolate, or hallucinate user quotes or statistics that are not present in the provided evidence.
4. Structure your response into:
   - **Executive Summary**: Direct 1-2 sentence answer to the query.
   - **Key Behavioral Drivers & Blockers**: Bullet points detailing specific patterns observed in the evidence.
   - **Supporting User Evidence Quotes**: Exact quotes with record citations and category tags.
   - **Actionable Opportunity**: High-impact recommendation for product/UX teams to resolve this blocker.
5. If the evidence does not contain relevant information, respond: "No supporting evidence found in the current research corpus for this query."
"""


def format_rag_user_prompt(query: str, evidence_docs: List[Dict[str, Any]]) -> str:
    """Format the retrieved evidence into a structured prompt."""
    evidence_text_blocks = []
    for doc in evidence_docs:
        rec_id = doc.get("record_id")
        category = doc.get("product_category")
        intent = doc.get("wishlist_intent")
        
        blockers_arr = doc.get("purchase_blocker")
        blockers = ", ".join([str(b) for b in blockers_arr]) if blockers_arr is not None else ""
        
        gaps_arr = doc.get("information_gap")
        gaps = ", ".join([str(g) for g in gaps_arr]) if gaps_arr is not None else ""
        
        theme = doc.get("theme")
        raw_text = doc.get("raw_text")
        evidence = doc.get("verbatim_evidence") or raw_text

        block = f"""--- Record #{rec_id} (Category: {category} | Theme: {theme}) ---
Intent: {intent}
Blockers: {blockers}
Information Gaps: {gaps}
Customer Quote: "{evidence}"
Full Statement: "{raw_text}"
"""
        evidence_text_blocks.append(block)

    joined_evidence = "\n".join(evidence_text_blocks)

    return f"""Researcher Query: "{query}"

=== RETRIEVED CUSTOMER EVIDENCE ({len(evidence_docs)} Records) ===
{joined_evidence}
=====================================================

Please synthesize an evidence-grounded answer following the mandatory rules."""


class EvidenceSynthesizer:
    """Synthesizes qualitative answers grounded strictly in retrieved user statements."""

    def __init__(self, groq_client: Optional[GroqClient] = None):
        self.client = groq_client or GroqClient()

    def synthesize(self, query: str, evidence_docs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate evidence-backed answer."""
        if not evidence_docs:
            return {
                "query": query,
                "answer": "No supporting evidence found in the current research corpus for this query.",
                "evidence_count": 0,
                "cited_records": [],
                "engine": "none",
            }

        # Build citations list
        cited_records = []
        for doc in evidence_docs:
            blockers = doc.get("purchase_blocker")
            blockers_clean = [str(b) for b in blockers] if isinstance(blockers, list) else []
            cited_records.append({
                "record_id": doc.get("record_id"),
                "category": doc.get("product_category"),
                "product_category": doc.get("product_category"),
                "theme": doc.get("theme"),
                "intent": doc.get("wishlist_intent"),
                "blockers": blockers_clean,
                "quote": doc.get("verbatim_evidence") or doc.get("raw_text"),
                "verbatim_evidence": doc.get("verbatim_evidence") or doc.get("raw_text"),
                "raw_text": doc.get("raw_text") or doc.get("text", ""),
                "source": doc.get("source"),
            })

        # Check if Groq API is live
        if self.client.is_live and self.client.client:
            try:
                user_prompt = format_rag_user_prompt(query, evidence_docs)
                response = self.client.client.chat.completions.create(
                    model=self.client.model,
                    messages=[
                        {"role": "system", "content": RAG_SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.0,
                    max_tokens=1024,
                )
                answer_text = response.choices[0].message.content
                return {
                    "query": query,
                    "answer": answer_text,
                    "evidence_count": len(evidence_docs),
                    "cited_records": cited_records,
                    "engine": f"Groq ({self.client.model})",
                }
            except Exception as e:
                print(f"[!] Groq RAG call failed ({e}). Using deterministic synthesis.")

        # Deterministic / Mock Synthesis Fallback
        categories = list({str(d.get("product_category")) for d in evidence_docs if d.get("product_category")})
        themes = list({str(d.get("theme")) for d in evidence_docs if d.get("theme")})
        blockers_seen = set()
        for d in evidence_docs:
            b_arr = d.get("purchase_blocker")
            if b_arr is not None:
                for b in b_arr:
                    if b:
                        blockers_seen.add(str(b))

        quotes_list = "\n".join([f"  * [Record #{c['record_id']} - {c['category']}]: \"{c['quote']}\"" for c in cited_records[:4]])

        answer_text = f"""### Executive Summary
Analysis of {len(evidence_docs)} relevant feedback records indicates that shoppers in {', '.join(categories)} face primary decision hesitation around **{', '.join(themes)}**, specifically driven by blockers such as {', '.join(list(blockers_seen)[:3])}.

### Key Behavioral Drivers Observed
- **Uncertainty & Information Gaps**: Users save items to their wishlist but delay purchase because critical validation information is missing before checkout.
- **Comparison Behavior**: Shoppers frequently look for alternative products or cross-platform options while keeping items saved.

### Supporting Customer Evidence Quotes
{quotes_list}

### Actionable Opportunity
Provide clear contextual validation triggers (e.g., verified swatches, detailed compatibility filters, or price drop notifications) on the product detail and wishlist pages to unblock purchase hesitation."""

        return {
            "query": query,
            "answer": answer_text,
            "evidence_count": len(evidence_docs),
            "cited_records": cited_records,
            "engine": "Deterministic Synthesizer",
        }
