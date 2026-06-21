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
    Thread-safe, partitioned by workspace, and fast retrieval.
    """

    def __init__(self):
        self.lock = threading.RLock()
        self.by_workspace: Dict[str, Dict[str, Any]] = {}
        self.doc_to_workspace: Dict[str, str] = {}

    def _get_workspace_state(self, workspace_id: Optional[str]) -> Dict[str, Any]:
        ws_id = workspace_id or "default"
        if ws_id not in self.by_workspace:
            self.by_workspace[ws_id] = {
                "doc_ids": [],
                "doc_texts": {},
                "doc_lens": {},
                "tf": {},
                "df": {},
                "N": 0,
                "avg_doc_len": 0.0
            }
        return self.by_workspace[ws_id]

    # Properties mapping flat access to 'default' workspace for test compatibility
    @property
    def doc_ids(self):
        return self._get_workspace_state("default")["doc_ids"]

    @doc_ids.setter
    def doc_ids(self, val):
        self._get_workspace_state("default")["doc_ids"] = val

    @property
    def doc_texts(self):
        return self._get_workspace_state("default")["doc_texts"]

    @doc_texts.setter
    def doc_texts(self, val):
        self._get_workspace_state("default")["doc_texts"] = val

    @property
    def doc_lens(self):
        return self._get_workspace_state("default")["doc_lens"]

    @doc_lens.setter
    def doc_lens(self, val):
        self._get_workspace_state("default")["doc_lens"] = val

    @property
    def tf(self):
        return self._get_workspace_state("default")["tf"]

    @tf.setter
    def tf(self, val):
        self._get_workspace_state("default")["tf"] = val

    @property
    def df(self):
        return self._get_workspace_state("default")["df"]

    @df.setter
    def df(self, val):
        self._get_workspace_state("default")["df"] = val

    @property
    def N(self):
        return self._get_workspace_state("default")["N"]

    @N.setter
    def N(self, val):
        self._get_workspace_state("default")["N"] = val

    @property
    def avg_doc_len(self):
        return self._get_workspace_state("default")["avg_doc_len"]

    @avg_doc_len.setter
    def avg_doc_len(self, val):
        self._get_workspace_state("default")["avg_doc_len"] = val

    def tokenize(self, text: str) -> List[str]:
        if not text:
            return []
        # Lowercase, remove punctuation, split by words
        words = re.findall(r"\w+", text.lower())
        return [w for w in words if w not in STOPWORDS]

    def add_document(self, doc_id: str, text: str, workspace_id: Optional[str] = None):
        """Add or update a document in the index in a thread-safe manner."""
        with self.lock:
            self._add_document_unlocked(doc_id, text, workspace_id)
            self._recalculate_stats_unlocked(workspace_id)

    def remove_document(self, doc_id: str):
        """Remove a document from the index in a thread-safe manner."""
        with self.lock:
            ws_id = self.doc_to_workspace.get(doc_id)
            self._remove_document_unlocked(doc_id)
            if ws_id:
                self._recalculate_stats_unlocked(ws_id)

    def _add_document_unlocked(self, doc_id: str, text: str, workspace_id: Optional[str] = None):
        ws_id = workspace_id or "default"
        state = self._get_workspace_state(ws_id)
        
        if doc_id in self.doc_to_workspace:
            self._remove_document_unlocked(doc_id)

        tokens = self.tokenize(text)
        if not tokens:
            return

        self.doc_to_workspace[doc_id] = ws_id
        state["doc_ids"].append(doc_id)
        state["doc_texts"][doc_id] = text
        state["doc_lens"][doc_id] = len(tokens)
        state["N"] += 1

        # Count frequencies
        doc_tf: Dict[str, int] = {}
        for token in tokens:
            doc_tf[token] = doc_tf.get(token, 0) + 1

        # Update global structures
        for term, count in doc_tf.items():
            if term not in state["tf"]:
                state["tf"][term] = {}
            state["tf"][term][doc_id] = count
            state["df"][term] = state["df"].get(term, 0) + 1

    def _remove_document_unlocked(self, doc_id: str):
        ws_id = self.doc_to_workspace.get(doc_id)
        if not ws_id:
            return

        state = self._get_workspace_state(ws_id)
        if doc_id not in state["doc_texts"]:
            return

        state["doc_ids"].remove(doc_id)
        del state["doc_texts"][doc_id]
        del state["doc_lens"][doc_id]
        state["N"] -= 1

        for term in list(state["tf"].keys()):
            if doc_id in state["tf"][term]:
                del state["tf"][term][doc_id]
                state["df"][term] -= 1
                if state["df"][term] == 0:
                    del state["df"][term]
                    del state["tf"][term]
                    
        if doc_id in self.doc_to_workspace:
            del self.doc_to_workspace[doc_id]

    def _recalculate_stats_unlocked(self, workspace_id: Optional[str] = None):
        ws_id = workspace_id or "default"
        state = self._get_workspace_state(ws_id)
        if state["N"] > 0:
            state["avg_doc_len"] = sum(state["doc_lens"].values()) / state["N"]
        else:
            state["avg_doc_len"] = 0.0

    async def load_from_sqlite(self):
        """Initialize the in-memory index from SQL database chunks."""
        from backend.core.database import async_session
        from backend.models.chunk import Chunk as DBChunk
        from sqlalchemy import select

        logger.info("Syncing BM25 index with SQLite database chunks...")
        try:
            async with async_session() as session:
                # Load all active chunks (id, content, and workspace_id projected)
                stmt = select(DBChunk.id, DBChunk.content, DBChunk.workspace_id).where(DBChunk.is_active == True)
                res = await session.execute(stmt)
                chunks = res.all()

                with self.lock:
                    self.by_workspace = {}
                    self.doc_to_workspace = {}

                    for row in chunks:
                        if hasattr(row, "_mapping"):
                            chunk_id = row._mapping["id"]
                            chunk_content = row._mapping["content"]
                            chunk_workspace_id = row._mapping["workspace_id"]
                        elif isinstance(row, tuple) and len(row) >= 3:
                            chunk_id, chunk_content, chunk_workspace_id = row[:3]
                        elif hasattr(row, "id") and hasattr(row, "content") and hasattr(row, "workspace_id"):
                            chunk_id = row.id
                            chunk_content = row.content
                            chunk_workspace_id = row.workspace_id
                        else:
                            chunk_id, chunk_content, chunk_workspace_id = row[:3]
                        self._add_document_unlocked(chunk_id, chunk_content, chunk_workspace_id)
                    
                    # Recalculate stats for all loaded workspaces
                    for ws_id in self.by_workspace:
                        self._recalculate_stats_unlocked(ws_id)

            logger.info(f"Loaded BM25 index from SQLite for {len(self.by_workspace)} active workspaces.")
        except Exception as e:
            logger.error(f"Failed to load BM25 index from SQLite: {e}")

    def search(
        self,
        query: str,
        top_k: int = 10,
        filter_ids: Optional[List[str]] = None,
        workspace_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Search the in-memory BM25 index."""
        tokens = self.tokenize(query)
        ws_id = workspace_id or "default"
        state = self._get_workspace_state(ws_id)
        
        if not tokens or state["N"] == 0:
            return []

        scores: Dict[str, float] = {}
        k1 = 1.5
        b = 0.75
        filter_set = set(filter_ids) if filter_ids is not None else None

        with self.lock:
            for term in tokens:
                if term not in state["tf"]:
                    continue

                df = state["df"][term]
                # IDF calculation with smoothing
                idf = math.log(1.0 + (state["N"] - df + 0.5) / (df + 0.5))

                for doc_id, tf in state["tf"][term].items():
                    if filter_set is not None and doc_id not in filter_set:
                        continue
                    doc_len = state["doc_lens"][doc_id]
                    denom = tf + k1 * (1.0 - b + b * (doc_len / state["avg_doc_len"]))
                    score_term = idf * (tf * (k1 + 1)) / denom
                    scores[doc_id] = scores.get(doc_id, 0.0) + score_term

        # Sort by score descending
        sorted_hits = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]

        results = []
        with self.lock:
            for doc_id, score in sorted_hits:
                results.append({
                    "chunk_id": doc_id,
                    "text": state["doc_texts"][doc_id],
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
