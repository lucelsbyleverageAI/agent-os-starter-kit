"""Fast PDF text extraction using PyMuPDF (fitz).

This service provides quick PDF text extraction for chat uploads,
bypassing the slower Dockling pipeline used for knowledge base ingestion.
"""

import logging
import re
from dataclasses import dataclass
from typing import Optional

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)


@dataclass
class ExtractionResult:
    """Result from PDF text extraction."""

    success: bool
    content: str
    page_count: int
    error_message: Optional[str] = None


class PyMuPDFExtractor:
    """Fast PDF text extraction using PyMuPDF.

    This extractor is optimized for speed over accuracy, suitable for
    chat uploads where we need a quick text preview rather than
    detailed table/structure extraction.
    """

    def extract_text_from_bytes(self, pdf_bytes: bytes) -> ExtractionResult:
        """Extract text from PDF bytes with markdown-like formatting.

        Args:
            pdf_bytes: Raw PDF file bytes

        Returns:
            ExtractionResult with extracted text or error
        """
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            pages_text = []
            page_count = len(doc)

            for page_num in range(page_count):
                page = doc[page_num]
                text = page.get_text("text")

                # Clean and format the text
                cleaned = self._clean_text(text)
                if cleaned:
                    pages_text.append(f"## Page {page_num + 1}\n\n{cleaned}")

            doc.close()

            full_text = "\n\n".join(pages_text)

            return ExtractionResult(
                success=True,
                content=full_text,
                page_count=page_count,
            )

        except Exception as e:
            logger.exception("PyMuPDF extraction failed")
            return ExtractionResult(
                success=False,
                content="",
                page_count=0,
                error_message=str(e),
            )

    def _clean_text(self, text: str) -> str:
        """Clean extracted text - normalize whitespace, preserve structure.

        Args:
            text: Raw text from PDF page

        Returns:
            Cleaned text with normalized whitespace
        """
        if not text:
            return ""

        # Normalize line endings
        text = text.replace("\r\n", "\n").replace("\r", "\n")

        # Collapse excessive blank lines (more than 2 consecutive)
        text = re.sub(r"\n{3,}", "\n\n", text)

        # Collapse multiple spaces within lines
        text = re.sub(r"[ \t]+", " ", text)

        # Strip whitespace from each line
        lines = [line.strip() for line in text.split("\n")]
        text = "\n".join(lines)

        # Remove leading/trailing whitespace
        return text.strip()


# Singleton instance for reuse
pymupdf_extractor = PyMuPDFExtractor()
