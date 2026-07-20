"""
MiniLM Local NLP Scorer Module
Uses Sentence-Transformers 'all-MiniLM-L6-v2' to compute semantic similarity
between event titles/descriptions and target search goals/topics.
Includes a fast hybrid n-gram TF-IDF fallback if sentence-transformers is loading.
"""

import os
import re
import math
import numpy as np
from typing import List, Dict, Any, Optional

_MODEL = None
_MODEL_FAILED = False

def _load_model():
    global _MODEL, _MODEL_FAILED
    if _MODEL is not None:
        return _MODEL
    if _MODEL_FAILED:
        return None
    try:
        from sentence_transformers import SentenceTransformer
        print("[MiniLM Scorer] Loading all-MiniLM-L6-v2 model...")
        _MODEL = SentenceTransformer("all-MiniLM-L6-v2")
        print("[MiniLM Scorer] Model loaded successfully!")
    except Exception as e:
        print(f"[MiniLM Scorer] Notice: sentence-transformers model loading fallback: {e}")
        _MODEL_FAILED = False  # Retry on next call if pip finishes
    return _MODEL


def _ngram_tfidf_similarity(text1: str, text2: str) -> float:
    """Fast local fallback scoring based on token overlap & character n-grams."""
    def get_tokens(t):
        return set(re.findall(r'\w+', str(t).lower()))

    tokens1 = get_tokens(text1)
    tokens2 = get_tokens(text2)
    if not tokens1 or not tokens2:
        return 0.0

    intersection = tokens1.intersection(tokens2)
    union = tokens1.union(tokens2)
    jaccard = len(intersection) / len(union) if union else 0.0

    # Containment score
    containment = len(intersection) / min(len(tokens1), len(tokens2)) if min(len(tokens1), len(tokens2)) > 0 else 0.0
    
    score = (jaccard * 40.0) + (containment * 60.0)
    return float(score)


def compute_minilm_score(
    title: str,
    description: str = "",
    target_queries: Optional[List[str]] = None
) -> float:
    """
    Computes a 0 - 100 semantic similarity score between (title + description)
    and target queries using all-MiniLM-L6-v2 or hybrid NLP matching.
    """
    if not target_queries:
        return 0.0

    title_clean = str(title or "").strip()
    desc_clean = str(description or "").strip()[:300]
    event_text = f"{title_clean}. {desc_clean}".strip()

    if not event_text:
        return 0.0

    clean_queries = [str(q).strip() for q in target_queries if str(q).strip()]
    if not clean_queries:
        return 0.0

    model = _load_model()
    if model is not None:
        try:
            # Encode event text and target queries
            embeddings = model.encode([event_text] + clean_queries, normalize_embeddings=True)
            event_emb = embeddings[0]
            query_embs = embeddings[1:]

            # Cosine similarity
            sims = np.dot(query_embs, event_emb)
            max_sim = float(np.max(sims))

            # Map cosine similarity to 0-100 scale
            if max_sim <= 0.15:
                score = max_sim * 100
            elif max_sim <= 0.35:
                score = 15 + (max_sim - 0.15) * 175
            else:
                score = 50 + (max_sim - 0.35) * 80

            return round(max(0.0, min(100.0, score)), 1)
        except Exception as e:
            print(f"[MiniLM Scorer] Model run error: {e}")

    # Fallback NLP similarity matcher
    fallback_scores = [_ngram_tfidf_similarity(event_text, q) for q in clean_queries]
    return round(max(fallback_scores), 1) if fallback_scores else 0.0
