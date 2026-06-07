import logging
import re
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class LayoutAwareChunker:
    """
    Next-generation layout-aware chunking engine.
    Respects physical and structural boundaries in documents (PDFs, Markdown, Web Pages).
    Prepends parent structural hierarchy as a path to preserve local context.
    """

    def __init__(self, target_chunk_size: int = 1000, overlap_sentences: int = 1):
        self.target_chunk_size = target_chunk_size
        self.overlap_sentences = overlap_sentences

    def chunk_document_elements(self, elements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Groups visual document elements (headers, tables, lists, text) into semantic chunks.
        Recursively traces header hierarchies (H1 -> H2 -> H3) and includes these paths in child metadata.
        """
        chunks = []
        current_chunk_text = []
        heading_path = []

        def finalize_text_chunk(text_elements: List[str], path: List[str]) -> None:
            if not text_elements:
                return
            clean_text = "\n".join(text_elements)
            hierarchy_str = " > ".join(path) if path else "General Document Context"
            contextualized_content = f"[{hierarchy_str}]\n\n{clean_text}"
            
            chunks.append({
                "content": contextualized_content,
                "raw_content": clean_text,
                "type": "text",
                "hierarchy": list(path),
                "token_estimate": len(contextualized_content.split())
            })

        for el in elements:
            el_type = el.get("type", "text")
            content = el.get("content", "").strip()
            if not content:
                continue

            if el_type == "heading":
                # Finalize existing text chunks before updating heading hierarchy
                finalize_text_chunk(current_chunk_text, heading_path)
                current_chunk_text = []

                level = el.get("metadata", {}).get("level", 1)
                # Ensure hierarchy stays aligned
                while len(heading_path) >= level:
                    if heading_path:
                        heading_path.pop()
                heading_path.append(content)
                current_chunk_text.append(content)

            elif el_type == "table":
                finalize_text_chunk(current_chunk_text, heading_path)
                current_chunk_text = []
                
                # Tables are kept atomic and separate
                hierarchy_str = " > ".join(heading_path) if heading_path else "Table Context"
                chunks.append({
                    "content": f"[{hierarchy_str} (Table)]\n\n{content}",
                    "raw_content": content,
                    "type": "table",
                    "hierarchy": list(heading_path)
                })

            elif el_type == "list_item":
                # Lists are batched together to preserve complete instructions
                current_chunk_text.append(f"- {content}")
                if sum(len(x) for x in current_chunk_text) > self.target_chunk_size:
                    finalize_text_chunk(current_chunk_text, heading_path)
                    current_chunk_text = []

            else:  # Standard paragraph text
                current_chunk_text.append(content)
                if sum(len(x) for x in current_chunk_text) > self.target_chunk_size:
                    finalize_text_chunk(current_chunk_text, heading_path)
                    current_chunk_text = []

        # Finalize residual elements
        finalize_text_chunk(current_chunk_text, heading_path)
        logger.info("Successfully sliced document into %d layout-aware chunks", len(chunks))
        return chunks
