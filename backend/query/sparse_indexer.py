import logging
import math
import re
import threading
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

STOPWORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and", "any", "are", "arent", "as", "at",
    "be", "because", "been", "before", "being", "below", "between", "both", "but", "by", "cant", "cannot", "could",
    "couldnt", "did", "didnt", "do", "does", "doesnt", "doing", "dont", "down", "during", "each", "few", "for", "from",
    "further", "had", "hadnt", "has", "hasnt", "have", "havent", "having", "he", "hed", "hell", "hes", "her", "here",
    "heres", "hers", "herself", "him", "himself", "his", "how", "hows", "i", "id", "im", "ive", "if", "in", "into",
    "is", "isnt", "it", "its", "itself", "lets", "me", "more", "most", "mustnt", "my", "myself", "no", "nor", "not",
    "of", "off", "on", "once", "only", "or", "other", "ought", "our", "ours", "ourselves", "out", "over", "own",
    "same", "shant", "she", "shed", "shell", "shes", "should", "shouldnt", "so", "some", "such", "than", "that",
    "thats", "the", "their", "theirs", "them", "themselves", "then", "there", "theres", "these", "they", "theyd",
    "theyll", "theyre", "theyve", "this", "those", "through", "to", "too", "under", "until", "up", "very", "was",
    "wasnt", "we", "wed", "well", "were", "weve", "werent", "what", "whats", "when", "whens", "where", "wheres",
    "which", "while", "who", "whos", "whom", "why", "whys", "with", "wont", "would", "wouldnt", "you", "youd",
    "youll", "youre", "youve", "your", "yours", "yourself", "yourselves"
}

class SparseIndexer:
    """
    SOTA Query: In-Memory BM25 keyword indexer.
    Thread-safe and fast retrieval on low-end hardware.
    """

    def __init__(self):
        self.lock = threading.RLock()
        self.doc_ids: List[str] = []
        self.doc_texts: Dict[str, str] = {}
        self.doc_lens: Dict[str, int] = {}
        self.tf: Dict[str, Dict[str, int]] = {}  # term -> doc_id -> count
        self.df: Dict[str, int] = {}  # term -> doc_count
        self.N: int = 0
        self.avg_doc_len: float = 0.0

    def tokenize(self, text: str) -> List[str]:
        if not text:
            return []
        # Lowercase, remove punctuation, split by words
        words = re.findall(r"\w+", text.lower())
        return [w for w in words if w not in STOPWORDS]

    def add_document(self, doc_id: str, text: str):
        """Add or update a document in the index in a thread-safe manner."""
        with self.lock:
            self._add_document_unlocked(doc_id, text)
            self._recalculate_stats_unlocked()

    def remove_document(self, doc_id: str):
        """Remove a document from the index in a thread-safe manner."""
        with self.lock:
            self._remove_document_unlocked(doc_id)
            self._recalculate_stats_unlocked()

    def _add_document_unlocked(self, doc_id: str, text: str):
        if doc_id in self.doc_texts:
            self._remove_document_unlocked(doc_id)

        tokens = self.tokenize(text)
        if not tokens:
            return

        self.doc_ids.append(doc_id)
        self.doc_texts[doc_id] = text
        self.doc_lens[doc_id] = len(tokens)
        self.N += 1

        # Count frequencies
        doc_tf: Dict[str, int] = {}
        for token in tokens:
            doc_tf[token] = doc_tf.get(token, 0) + 1

        # Update global structures
        for term, count in doc_tf.items():
            if term not in self.tf:
                self.tf[term] = {}
            self.tf[term][doc_id] = count
            self.df[term] = self.df.get(term, 0) + 1

    def _remove_document_unlocked(self, doc_id: str):
        if doc_id not in self.doc_texts:
            return

        self.doc_ids.remove(doc_id)
        del self.doc_texts[doc_id]
        del self.doc_lens[doc_id]
        self.N -= 1

        for term in list(self.tf.keys()):
            if doc_id in self.tf[term]:
                del self.tf[term][doc_id]
                self.df[term] -= 1
                if self.df[term] == 0:
                    del self.df[term]
                    del self.tf[term]

    def _recalculate_stats_unlocked(self):
        if self.N > 0:
            self.avg_doc_len = sum(self.doc_lens.values()) / self.N
        else:
            self.avg_doc_len = 0.0

    async def load_from_sqlite(self):
        """Initialize the in-memory index from SQL database chunks."""
        from backend.core.database import async_session
        from backend.models.chunk import Chunk as DBChunk
        from sqlalchemy import select

        logger.info("Syncing BM25 index with SQLite database chunks...")
        try:
            async with async_session() as session:
                # Load all active chunks (only id and content projected for memory optimization)
                stmt = select(DBChunk.id, DBChunk.content).where(DBChunk.is_active == True)
                res = await session.execute(stmt)
                chunks = res.all()

                with self.lock:
                    self.doc_ids = []
                    self.doc_texts = {}
                    self.doc_lens = {}
                    self.tf = {}
                    self.df = {}
                    self.N = 0
                    self.avg_doc_len = 0.0

                    for row in chunks:
                        if hasattr(row, "_mapping"):
                            chunk_id = row._mapping["id"]
                            chunk_content = row._mapping["content"]
                        elif isinstance(row, tuple):
                            chunk_id, chunk_content = row
                        elif hasattr(row, "id") and hasattr(row, "content"):
                            chunk_id = row.id
                            chunk_content = row.content
                        else:
                            chunk_id, chunk_content = row
                        self._add_document_unlocked(chunk_id, chunk_content)
                    self._recalculate_stats_unlocked()

            logger.info(f"Loaded {self.N} active chunks into BM25 index.")
        except Exception as e:
            logger.error(f"Failed to load BM25 index from SQLite: {e}")

    def search(self, query: str, top_k: int = 10, filter_ids: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Search the in-memory BM25 index."""
        tokens = self.tokenize(query)
        if not tokens or self.N == 0:
            return []

        scores: Dict[str, float] = {}
        k1 = 1.5
        b = 0.75
        filter_set = set(filter_ids) if filter_ids is not None else None

        with self.lock:
            for term in tokens:
                if term not in self.tf:
                    continue

                df = self.df[term]
                # IDF calculation with smoothing
                idf = math.log(1.0 + (self.N - df + 0.5) / (df + 0.5))

                for doc_id, tf in self.tf[term].items():
                    if filter_set is not None and doc_id not in filter_set:
                        continue
                    doc_len = self.doc_lens[doc_id]
                    denom = tf + k1 * (1.0 - b + b * (doc_len / self.avg_doc_len))
                    score_term = idf * (tf * (k1 + 1)) / denom
                    scores[doc_id] = scores.get(doc_id, 0.0) + score_term

        # Sort by score descending
        sorted_hits = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]

        results = []
        with self.lock:
            for doc_id, score in sorted_hits:
                results.append({
                    "chunk_id": doc_id,
                    "text": self.doc_texts[doc_id],
                    "score": score
                })
        return results

# Global sparse indexer instance
_SPARSE_INDEXER = None
_SPARSE_INDEXER_LOCK = threading.Lock()

def get_sparse_indexer() -> SparseIndexer:
    global _SPARSE_INDEXER
    with _SPARSE_INDEXER_LOCK:
        if _SPARSE_INDEXER is None:
            _SPARSE_INDEXER = SparseIndexer()
        return _SPARSE_INDEXER
