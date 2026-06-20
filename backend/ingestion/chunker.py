import logging
import re
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


class DocumentChunker:
    """
    Blueprint Layer 6: Adaptive Hierarchical Chunking.
    Splits elements into Parent Chunks (1000-1200 characters) and creates nested
    Child Chunks (200-300 characters) for high-precision retrieval.
    """

    def __init__(self, chunk_size: int = 1200, chunk_overlap: int = 200, child_size: int = 250, child_overlap: int = 50):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.child_size = child_size
        self.child_overlap = child_overlap

    def _create_child_chunks(self, parent_text: str) -> List[str]:
        """
        Split a parent text chunk into smaller child chunks for precise vector matches.
        """
        # Split by sentence boundaries to avoid mid-word truncation
        sentences = re.split(r'(?<=[.!?])\s+', parent_text)
        children = []
        current_child = ""

        for sentence in sentences:
            if not sentence.strip():
                continue
            if len(current_child) + len(sentence) > self.child_size and current_child:
                children.append(current_child.strip())
                overlap = current_child[-self.child_overlap:] if self.child_overlap > 0 else ""
                current_child = overlap + " " + sentence if overlap else sentence
            else:
                current_child += " " + sentence if current_child else sentence

        if current_child:
            children.append(current_child.strip())

        return children

    def chunk(self, text: str, doc_type: str = "general") -> List[Dict[str, Any]]:
        """Choose the best strategy based on document type."""
        if doc_type == "code":
            return self._chunk_code(text)
        elif doc_type == "table":
            return self._chunk_table(text)
        else:
            return self._chunk_structured_text(text)

    def chunk_elements(self, elements: List[Dict[str, Any]], doc_type: str = "auto") -> List[Dict[str, Any]]:
        """
        Group elements into chunks while preserving structural integrity.
        Generates hierarchical child chunks under each parent chunk.
        """
        chunks = []
        current_chunk_text = []
        heading_stack = []

        def finalize_chunk(text_list, stack):
            if not text_list:
                return

            clean_text = "\n\n".join(text_list)
            path_str = " > ".join(stack) if stack else "Root"
            contextual_text = f"[{path_str}]\n\n{clean_text}"

            # Create hierarchical child chunks from parent text
            children = self._create_child_chunks(clean_text)

            chunks.append({
                "content": contextual_text,
                "raw_content": clean_text,
                "type": "text",
                "heading": stack[-1] if stack else None,
                "heading_path": list(stack),
                "children": children
            })

        for el in elements:
            el_type = el["type"]
            content = el["content"]
            tag = el.get("metadata", {}).get("tag", "")

            if el_type == "header":
                level = el.get("metadata", {}).get("level", 1)
                if isinstance(level, str) and level.isdigit():
                    level = int(level)
                elif tag.startswith('h') and tag[1:].isdigit():
                    level = int(tag[1:])

                finalize_chunk(current_chunk_text, heading_stack)
                current_chunk_text = []

                while len(heading_stack) >= level:
                    heading_stack.pop()
                heading_stack.append(content)

                current_chunk_text.append(content)

            elif el_type == "table":
                finalize_chunk(current_chunk_text, heading_stack)
                current_chunk_text = []

                path_str = " > ".join(heading_stack) if heading_stack else "Root"
                table_content = f"[{path_str} (Table)]\n\n{content}"
                chunks.append({
                    "content": table_content,
                    "raw_content": content,
                    "type": "table",
                    "heading": heading_stack[-1] if heading_stack else None,
                    "heading_path": list(heading_stack),
                    "children": [content]  # Tables are atomic, do not split
                })

            else:
                current_chunk_text.append(content)
                if sum(len(c) for c in current_chunk_text) > self.chunk_size:
                    finalize_chunk(current_chunk_text, heading_stack)
                    current_chunk_text = []

        finalize_chunk(current_chunk_text, heading_stack)
        return chunks

    def _chunk_code(self, code: str) -> List[Dict[str, Any]]:
        """Syntactic code chunking."""
        pattern = r"(?m)^(?:def|class|async def|export|interface|struct|function)\s+\w+.*"
        parts = re.split(f"({pattern})", code)

        chunks = []
        if parts[0].strip():
            chunk_content = parts[0].strip()
            chunks.append({
                "content": f"[Code Overview]\n\n{chunk_content}",
                "raw_content": chunk_content,
                "type": "code_overview",
                "children": [chunk_content]  # Code overview is atomic
            })

        for i in range(1, len(parts), 2):
            definition = parts[i]
            body = parts[i + 1] if i + 1 < len(parts) else ""
            chunk_content = (definition + body).strip()
            if chunk_content:
                chunks.append({
                    "content": chunk_content,
                    "raw_content": chunk_content,
                    "type": "code_block",
                    "metadata": {"is_definition": True},
                    "children": [chunk_content]  # Code blocks are atomic
                })
        return chunks

    def _chunk_table(self, table_text: str, heading_path: List[str] = None) -> List[Dict[str, Any]]:
        """Row-aware table chunking."""
        lines = [l for l in table_text.split("\n") if l.strip()]
        if len(lines) < 2:
            return [{
                "content": table_text,
                "raw_content": table_text,
                "type": "table",
                "children": [table_text]
            }]

        header = lines[0]
        separator = lines[1] if len(lines) > 1 and "|" in lines[1] else ""

        start_idx = 2 if separator else 1
        data_rows = lines[start_idx:]

        chunks = []
        path_str = " > ".join(heading_path) if heading_path else "Table"

        for i in range(0, len(data_rows), 8):
            batch = data_rows[i:i + 8]
            chunk_content = f"[{path_str} (Part {i // 8 + 1})]\n{header}\n{separator}\n" + "\n".join(batch)
            chunks.append({
                "content": chunk_content,
                "raw_content": chunk_content,
                "type": "table_part",
                "metadata": {"is_table_part": True, "row_start": i},
                "children": [chunk_content]
            })
        return chunks

    def _chunk_transcript(self, transcript: str, heading_path: List[str] = None) -> List[Dict[str, Any]]:
        """Topic-aware transcript chunking."""
        speaker_pattern = r"(?m)^([A-Z][a-z]+(?:\s[A-Z][a-z]+)?):"
        parts = re.split(f"({speaker_pattern})", transcript)

        chunks = []
        current_discussion = []
        path_str = " > ".join(heading_path) if heading_path else "Meeting"

        def add_segment(disc, suffix):
            segment_content = f"[{path_str} {suffix}]\n\n" + "\n".join(disc)
            chunks.append({
                "content": segment_content,
                "raw_content": "\n".join(disc),
                "type": "transcript_segment",
                "children": self._create_child_chunks("\n".join(disc))
            })

        for i in range(0, len(parts), 2):
            content = parts[i]
            if i + 1 < len(parts):
                speaker = parts[i + 1]
                msg = parts[i + 2] if i + 2 < len(parts) else ""
                current_discussion.append(f"{speaker}{msg}")

                if sum(len(d) for d in current_discussion) > 1500:
                    add_segment(current_discussion, "Discussion")
                    current_discussion = []

        if current_discussion:
            add_segment(current_discussion, "Final Discussion")

        return chunks

    def _chunk_structured_text(self, text: str) -> List[Dict[str, Any]]:
        """Sliding window chunking for unstructured text."""
        sentences = re.split(r'(?<=[.!?])\s+', text)
        chunks = []
        current_chunk = ""

        for sentence in sentences:
            if not sentence.strip():
                continue

            if len(current_chunk) + len(sentence) > self.chunk_size and current_chunk:
                clean_chunk = current_chunk.strip()
                chunks.append({
                    "content": clean_chunk,
                    "raw_content": clean_chunk,
                    "type": "text",
                    "children": self._create_child_chunks(clean_chunk)
                })
                overlap_text = current_chunk[-self.chunk_overlap:] if self.chunk_overlap > 0 else ""
                current_chunk = overlap_text + " " + sentence if overlap_text else sentence
            else:
                current_chunk += " " + sentence if current_chunk else sentence

        if current_chunk:
            clean_chunk = current_chunk.strip()
            chunks.append({
                "content": clean_chunk,
                "raw_content": clean_chunk,
                "type": "text",
                "children": self._create_child_chunks(clean_chunk)
            })

        return chunks
