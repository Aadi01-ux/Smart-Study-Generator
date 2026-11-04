"""
services/document_service.py — text extraction and chunking for uploaded documents.
"""

import hashlib
import re
from io import BytesIO

import pypdf

import config


class DocumentService:
    """Handles PDF/TXT extraction and line-preserving chunking."""

    # ── Text extraction ───────────────────────────────────────────────────────

    def extract_text(self, file_bytes: bytes, filename: str) -> str:
        """Extract plain text from *file_bytes*.

        Supports .pdf (via pypdf) and .txt (UTF-8 with latin-1 fallback).
        Preserves line breaks so that heading structure is intact for chunking.
        Raises ValueError if no text could be extracted.
        """
        lower = filename.lower()

        if lower.endswith(".pdf"):
            reader = pypdf.PdfReader(BytesIO(file_bytes))
            parts = []
            for page in reader.pages:
                page_text = page.extract_text() or ""
                parts.append(page_text)
            # Join pages with a blank line so page boundaries don't merge words
            raw = "\n\n".join(parts)
        elif lower.endswith(".txt"):
            try:
                raw = file_bytes.decode("utf-8")
            except UnicodeDecodeError:
                raw = file_bytes.decode("latin-1")
        else:
            raise ValueError(
                f"Unsupported file type: '{filename}'. Only .pdf and .txt are supported."
            )

        # Normalise: collapse runs of spaces/tabs on each line, but keep newlines
        # so that heading lines are preserved as distinct lines.
        lines = raw.splitlines()
        cleaned = []
        for line in lines:
            line = re.sub(r"[ \t]+", " ", line).strip()
            cleaned.append(line)
        # Collapse 3+ consecutive blank lines into two (paragraph break)
        text = re.sub(r"\n{3,}", "\n\n", "\n".join(cleaned)).strip()

        if not text:
            raise ValueError("No text could be extracted from the document.")

        return text

    # ── Heading extraction ────────────────────────────────────────────────────

    # Pattern for likely headings: numbered lines, ALL-CAPS lines, or Title Case.
    _HEADING_RE = re.compile(
        r"^(?:"
        r"\d[\d\.]*\s+.{1,100}"           # "1. Introduction" / "1.1 Overview"
        r"|[A-Z][A-Z0-9\s\-\(\)\/]{2,80}" # ALL-CAPS lines
        r"|(?:[A-Z][a-z]+(?:\s+[A-Za-z]+){0,7})"  # Title Case (1-8 words)
        r")$"
    )

    def extract_headings(self, text: str) -> list[str]:
        """Return a list of likely heading strings found in *text*.

        Scans every line; a line is treated as a heading when it is short
        (<=120 chars), non-empty, and matches the heading pattern.
        Duplicates are removed while preserving order.
        """
        seen: set[str] = set()
        headings: list[str] = []
        for line in text.splitlines():
            line = line.strip()
            if not line or len(line) > 120:
                continue
            if self._HEADING_RE.match(line) and line not in seen:
                seen.add(line)
                headings.append(line)
        return headings

    # ── Chunking ──────────────────────────────────────────────────────────────

    def chunk_text(
        self,
        text: str,
        chunk_size: int = None,
        overlap: int = None,
    ) -> list[str]:
        """Split *text* into overlapping paragraph-aware chunks.

        Splits on paragraph boundaries (blank lines) first to keep heading
        lines with their content.  Each chunk is roughly *chunk_size* words;
        when a single paragraph exceeds that, it is included as its own chunk.
        Consecutive paragraphs are merged until adding the next one would
        exceed the word limit.  The last *overlap* words of each chunk are
        repeated at the start of the next chunk so context is not lost at
        boundaries.

        Newlines within each chunk are preserved so ChromaDB stores
        structured text rather than a flat word stream.

        Defaults to config.CHUNK_SIZE / config.CHUNK_OVERLAP when not provided.
        Returns an empty list for empty input.
        """
        if not text:
            return []

        chunk_size = chunk_size if chunk_size is not None else config.CHUNK_SIZE
        overlap = overlap if overlap is not None else config.CHUNK_OVERLAP

        # Split into paragraphs (one or more blank lines as separator)
        paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]

        chunks: list[str] = []
        current_paras: list[str] = []
        current_words = 0

        for para in paragraphs:
            para_words = len(para.split())
            if current_words + para_words > chunk_size and current_paras:
                # Emit the current chunk
                chunk = "\n\n".join(current_paras)
                chunks.append(chunk)
                # Start next chunk with overlap: keep enough trailing words
                # by retaining the last paragraph(s) that together cover
                # at least *overlap* words.
                overlap_paras: list[str] = []
                overlap_count = 0
                for p in reversed(current_paras):
                    overlap_paras.insert(0, p)
                    overlap_count += len(p.split())
                    if overlap_count >= overlap:
                        break
                current_paras = overlap_paras
                current_words = overlap_count

            current_paras.append(para)
            current_words += para_words

        # Emit any remaining content
        if current_paras:
            chunks.append("\n\n".join(current_paras))

        return chunks if chunks else [text]

    # ── Document ID ───────────────────────────────────────────────────────────

    def generate_doc_id(self, filename: str) -> str:
        """Return a deterministic MD5 hex digest of *filename*."""
        return hashlib.md5(filename.encode()).hexdigest()
