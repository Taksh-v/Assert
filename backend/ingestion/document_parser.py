import logging
import os
import tempfile
import io
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup
import pypdf
from backend.core.llm_client import LLMClient

logger = logging.getLogger(__name__)


class HybridParser:
    """
    Blueprint Layer 3: Structural & Multimodal Extraction.
    Handles PDFs, Images (OCR), and HTML-based documents without external heavy dependencies.
    Uses LLM Structural Repair for high-fidelity table extraction.
    """

    def __init__(self):
        self.ocr_reader = None # Lazy load
        self.whisper_model = None # Lazy load
        self.llm = LLMClient()

    async def _repair_table(self, scrambled_text: str) -> str:
        """Use LLM to reconstruct a clean Markdown table from scrambled text."""
        system_prompt = (
            "You are a document structural expert. Convert the following scrambled text "
            "into a clean, valid Markdown table. If it's not a table, return the text as is. "
            "Do NOT add any chat or preamble. ONLY return the table."
        )
        repaired = await self.llm.chat_completion(system_prompt, scrambled_text)
        return repaired if repaired else scrambled_text

    def _get_ocr(self):
        if not self.ocr_reader:
            import easyocr
            self.ocr_reader = easyocr.Reader(['en'])
        return self.ocr_reader

    def _parse_image(self, file_path: str) -> List[Dict[str, Any]]:
        """High-quality OCR using EasyOCR."""
        results = self._get_ocr().readtext(file_path, detail=1)
        content = "\n".join([res[1] for res in results])
        return [{"type": "ocr_text", "content": content, "metadata": {"source": "easyocr"}}]

    async def _summarize_table(self, table_markdown: str) -> str:
        """Generate a semantic summary of a table so it can be found via vector search."""
        prompt = (
            "Summarize the content and purpose of this table in one concise sentence. "
            "Example: 'This table lists monthly revenue targets for the sales team in 2024.'\n\n"
            f"Table:\n{table_markdown}"
        )
        summary = await self.llm.chat_completion(prompt, "")
        return summary if summary else "Data table."

    def _get_whisper(self):
        if not self.whisper_model:
            try:
                import whisper
                self.whisper_model = whisper.load_model("base")
            except ImportError:
                logger.warning("openai-whisper not installed. Audio extraction disabled.")
                return None
        return self.whisper_model

    async def parse(self, file_path: str) -> List[Dict[str, Any]]:
        """Parse a local file and return list of elements with metadata."""
        logger.info(f"Hybrid parsing: {file_path}")
        ext = file_path.lower().split('.')[-1]
        
        elements = []
        
        try:
            if ext in ['png', 'jpg', 'jpeg', 'tiff']:
                elements = self._parse_image(file_path)
            elif ext == "pdf":
                elements = await self._parse_pdf(file_path)
            elif ext in ["html", "htm"]:
                elements = self._parse_html(file_path)
            elif ext in ["mp3", "mp4", "wav", "m4a"]:
                elements = await self._parse_audio(file_path)
            else:
                # Basic text fallback
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    elements.append({"type": "text", "content": content, "metadata": {}})
            
            # Post-processing: Table Summarization
            for el in elements:
                if el["type"] == "table" and "summary" not in el["metadata"]:
                    el["metadata"]["summary"] = await self._summarize_table(el["content"])
                    # Combine summary with content for better embedding
                    el["content"] = f"Table Summary: {el['metadata']['summary']}\n\n{el['content']}"
            
            return elements
            
        except Exception as e:
            logger.error(f"Hybrid parsing failed for {file_path}: {e}")
            return []

    async def _parse_audio(self, file_path: str) -> List[Dict[str, Any]]:
        """Transcribe audio/video using Whisper."""
        model = self._get_whisper()
        if not model:
            return [{"type": "error", "content": "Whisper not available", "metadata": {}}]
        
        logger.info(f"Transcribing audio: {file_path}")
        result = model.transcribe(file_path)
        return [{"type": "transcript", "content": result["text"], "metadata": {"language": result.get("language")}}]

    async def _parse_pdf(self, file_path: str) -> List[Dict[str, Any]]:
        """Structured PDF parsing with automatic OCR for scanned pages."""
        elements = []
        with open(file_path, "rb") as f:
            reader = pypdf.PdfReader(f)
            for page_num, page in enumerate(reader.pages):
                text = page.extract_text()
                
                # If page has text, handle it (including tables)
                if text and text.strip():
                    if text.count('|') > 5 or "\t" in text:
                        repaired = await self._repair_table(text)
                        elements.append({
                            "type": "table",
                            "content": repaired,
                            "metadata": {"page": page_num + 1, "repaired": True}
                        })
                    else:
                        elements.append({
                            "type": "text",
                            "content": text,
                            "metadata": {"page": page_num + 1}
                        })
                
                # If page is empty, it's likely a scan. Trigger OCR.
                else:
                    logger.info(f"Page {page_num+1} is empty/scanned. Triggering OCR...")
                    # We would ideally extract the image of the page here
                    # For now, we fallback to OCR on the whole file if it's single page or log warning
                    if len(reader.pages) == 1:
                        ocr_elements = self._parse_image(file_path)
                        elements.extend(ocr_elements)
                    else:
                        elements.append({
                            "type": "text",
                            "content": "[Scanned Page - OCR Required]",
                            "metadata": {"page": page_num + 1, "needs_ocr": True}
                        })
                        
        return elements

    def _parse_html(self, file_path: str) -> List[Dict[str, Any]]:
        """Structural HTML parsing using BeautifulSoup."""
        elements = []
        with open(file_path, "r", encoding="utf-8") as f:
            soup = BeautifulSoup(f, "html.parser")
            
            # Extract headers, paragraphs, and tables as separate elements
            for tag in soup.find_all(['h1', 'h2', 'h3', 'p', 'table']):
                if tag.name == 'table':
                    elements.append({
                        "type": "table",
                        "content": str(tag), # Store HTML for now
                        "metadata": {"is_html": True}
                    })
                elif tag.name.startswith('h'):
                    elements.append({
                        "type": "header",
                        "content": tag.get_text(),
                        "metadata": {"level": tag.name[1]}
                    })
                else:
                    elements.append({
                        "type": "text",
                        "content": tag.get_text(),
                        "metadata": {}
                    })
        return elements

    def _parse_html_string(self, html_content: str) -> List[Dict[str, Any]]:
        """Structural HTML parsing from a string."""
        elements = []
        soup = BeautifulSoup(html_content, "html.parser")
        
        for tag in soup.find_all(['h1', 'h2', 'h3', 'p', 'table', 'li', 'code']):
            el_type = "text"
            if tag.name == 'table':
                el_type = "table"
            elif tag.name.startswith('h'):
                el_type = "header"
            elif tag.name == 'code':
                el_type = "code"
            
            elements.append({
                "type": el_type,
                "content": str(tag) if el_type == "table" else tag.get_text(),
                "metadata": {"tag": tag.name}
            })
        return elements

    async def parse_bytes(self, content: bytes, file_name: str) -> List[Dict[str, Any]]:
        """Parse content from bytes by saving to a temporary file."""
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{file_name.split('.')[-1]}") as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        
        try:
            return await self.parse(tmp_path)
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
