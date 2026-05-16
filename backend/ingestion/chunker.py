import logging
import re
from typing import List, Dict, Any
from backend.models.chunk import Chunk

logger = logging.getLogger(__name__)


class DocumentChunker:
    """
    Blueprint Layer 6: Adaptive Chunking.
    Specialized splitting for Code, Tables, and Structured Text.
    """

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
        Group elements into chunks while preserving structural integrity (Layer 4).
        Tracks hierarchical heading paths and PREPENDS them to content for maximum context.
        """
        chunks = []
        current_chunk_text = []
        # Path stack: [H1, H2, H3...]
        heading_stack = []
        
        def finalize_chunk(text_list, stack):
            if not text_list:
                return
            
            clean_text = "\n\n".join(text_list)
            # Layer 4: Explicit Context Prepending
            path_str = " > ".join(stack) if stack else "Root"
            contextual_text = f"[{path_str}]\n\n{clean_text}"
            
            chunks.append({
                "content": contextual_text,
                "raw_content": clean_text,
                "type": "text",
                "heading": stack[-1] if stack else None,
                "heading_path": list(stack)
            })

        for el in elements:
            el_type = el["type"]
            content = el["content"]
            tag = el.get("metadata", {}).get("tag", "")
            
            if el_type == "header":
                # Determine heading level from tag (e.g. 'h1' -> 1, 'header' metadata -> el['metadata']['level'])
                level = el.get("metadata", {}).get("level", 1)
                if isinstance(level, str) and level.isdigit():
                    level = int(level)
                elif tag.startswith('h') and tag[1:].isdigit():
                    level = int(tag[1:])
                
                # Save current chunk before shifting hierarchy
                finalize_chunk(current_chunk_text, heading_stack)
                current_chunk_text = []
                
                # Update heading stack
                while len(heading_stack) >= level:
                    heading_stack.pop()
                heading_stack.append(content)
                
                # Header is included in text for retrieval
                current_chunk_text.append(content)
            
            elif el_type == "table":
                finalize_chunk(current_chunk_text, heading_stack)
                current_chunk_text = []
                
                # Tables get the same context prepending
                path_str = " > ".join(heading_stack) if heading_stack else "Root"
                chunks.append({
                    "content": f"[{path_str} (Table)]\n\n{content}",
                    "type": "table",
                    "heading": heading_stack[-1] if heading_stack else None,
                    "heading_path": list(heading_stack)
                })
            
            else:
                current_chunk_text.append(content)
                # Elite Chunk Size: ~1000-1200 chars
                if sum(len(c) for c in current_chunk_text) > 1200:
                    finalize_chunk(current_chunk_text, heading_stack)
                    current_chunk_text = []
        
        # Save last chunk
        finalize_chunk(current_chunk_text, heading_stack)
        return chunks

    def _chunk_code(self, code: str) -> List[Dict[str, Any]]:
        """
        Syntactic code chunking (Layer 6).
        Splits by logical units (classes, functions) to maintain semantic continuity.
        """
        # Patterns for common languages (Python, JS, Java, etc.)
        pattern = r"(?m)^(?:def|class|async def|export|interface|struct|function)\s+\w+.*"
        
        # Split but keep the delimiter (the definition line)
        parts = re.split(f"({pattern})", code)
        
        chunks = []
        # If there's text before the first definition
        if parts[0].strip():
            chunks.append({
                "content": f"[Code Overview]\n\n{parts[0].strip()}",
                "type": "code_overview"
            })
            
        for i in range(1, len(parts), 2):
            definition = parts[i]
            body = parts[i+1] if i + 1 < len(parts) else ""
            
            # Combine into a logical unit
            chunk_content = (definition + body).strip()
            if chunk_content:
                chunks.append({
                    "content": chunk_content,
                    "type": "code_block",
                    "metadata": {"is_definition": True}
                })
        return chunks

    def _chunk_table(self, table_text: str, heading_path: List[str] = None) -> List[Dict[str, Any]]:
        """
        Row-aware table chunking (Layer 6).
        Ensures the header is repeated in every chunk so the AI knows the schema.
        """
        lines = [l for l in table_text.split("\n") if l.strip()]
        if len(lines) < 2:
            return [{"content": table_text, "type": "table"}]
        
        # Identify the header and the separator line (usually |---|)
        header = lines[0]
        separator = lines[1] if len(lines) > 1 and "|" in lines[1] else ""
        
        start_idx = 2 if separator else 1
        data_rows = lines[start_idx:]
        
        chunks = []
        path_str = " > ".join(heading_path) if heading_path else "Table"
        
        # Group rows into batches of 8 for optimal context
        for i in range(0, len(data_rows), 8):
            batch = data_rows[i:i+8]
            chunk_content = f"[{path_str} (Part {i//8 + 1})]\n{header}\n{separator}\n" + "\n".join(batch)
            chunks.append({
                "content": chunk_content,
                "type": "table_part",
                "metadata": {"is_table_part": True, "row_start": i}
            })
        return chunks

    def _chunk_transcript(self, transcript: str, heading_path: List[str] = None) -> List[Dict[str, Any]]:
        """
        Topic-aware transcript chunking (Layer 6).
        Splits by topic transitions or large speaker gaps.
        """
        # Split by potential topic markers or speaker changes (e.g. "Speaker 1:", "John:")
        speaker_pattern = r"(?m)^([A-Z][a-z]+(?:\s[A-Z][a-z]+)?):"
        parts = re.split(f"({speaker_pattern})", transcript)
        
        chunks = []
        current_discussion = []
        path_str = " > ".join(heading_path) if heading_path else "Meeting"
        
        # Group by ~1500 characters to keep meaningful conversations together
        for i in range(0, len(parts), 2):
            content = parts[i]
            if i + 1 < len(parts):
                speaker = parts[i+1]
                msg = parts[i+2] if i+2 < len(parts) else ""
                current_discussion.append(f"{speaker}{msg}")
                
                if sum(len(d) for d in current_discussion) > 1500:
                    chunks.append({
                        "content": f"[{path_str} Discussion]\n\n" + "\n".join(current_discussion),
                        "type": "transcript_segment"
                    })
                    current_discussion = []
                    
        if current_discussion:
            chunks.append({
                "content": f"[{path_str} Final Discussion]\n\n" + "\n".join(current_discussion),
                "type": "transcript_segment"
            })
            
        return chunks

