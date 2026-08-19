from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass, field

from models.document_model import ChunkModel, ChunkSourceModel, DocumentModel, PageModel

try:
    import tiktoken
except ImportError:  # pragma: no cover - repli pour environnement minimal
    tiktoken = None


@dataclass
class TextBlock:
    text: str
    sources: list[ChunkSourceModel] = field(default_factory=list)
    section_path: list[str] = field(default_factory=list)


class ChunkingService:
    def __init__(self, target_tokens: int = 600, max_tokens: int = 900, overlap_tokens: int = 80):
        self.target_tokens = target_tokens
        self.max_tokens = max_tokens
        self.overlap_tokens = overlap_tokens
        self.encoding = tiktoken.get_encoding("cl100k_base") if tiktoken else None

    def generate(self, document: DocumentModel) -> list[ChunkModel]:
        blocks = self._build_blocks(document.pages)
        groups = self._group_blocks(blocks)
        chunks = []
        for position, group in enumerate(groups):
            text = "\n\n".join(block.text for block in group).strip()
            sources = self._deduplicate_sources(group)
            section_path = next((block.section_path for block in reversed(group) if block.section_path), [])
            chunks.append(ChunkModel(
                id=str(uuid.uuid4()), document_id=document.id, position=position,
                text=text, section_path=section_path, sources=sources,
                token_count=self.estimate_tokens(text), content_hash=self.content_hash(text),
            ))
        return chunks

    def _build_blocks(self, pages: list[PageModel]) -> list[TextBlock]:
        blocks: list[TextBlock] = []
        current_section: list[str] = []
        for page in pages:
            text = page.corrected_text.strip()
            if not text:
                continue
            offset = 0
            for paragraph in re.split(r"\n\s*\n+", text):
                paragraph = paragraph.strip()
                if not paragraph:
                    continue
                start = text.find(paragraph, offset)
                end = start + len(paragraph)
                offset = end
                if self._looks_like_heading(paragraph):
                    current_section = [paragraph.replace("\n", " ")[:160]]
                for piece in self._split_large_text(paragraph):
                    piece_start = text.find(piece, start)
                    blocks.append(TextBlock(
                        text=piece,
                        sources=[ChunkSourceModel(
                            page_id=page.id, page_number=page.page,
                            start_offset=max(piece_start, start),
                            end_offset=max(piece_start, start) + len(piece),
                        )],
                        section_path=current_section.copy(),
                    ))
        return blocks

    def _group_blocks(self, blocks: list[TextBlock]) -> list[list[TextBlock]]:
        groups: list[list[TextBlock]] = []
        current: list[TextBlock] = []
        current_size = 0
        for block in blocks:
            block_size = self.estimate_tokens(block.text)
            separator_size = 1 if current else 0
            section_changed = bool(current and block.section_path and block.section_path != current[-1].section_path)
            if current and (current_size + separator_size + block_size > self.max_tokens or
                            section_changed and current_size >= self.target_tokens // 2):
                groups.append(current)
                current, current_size = [], 0
            current.append(block)
            current_size += separator_size + block_size
            if current_size >= self.target_tokens:
                groups.append(current)
                current, current_size = [], 0
        if current:
            groups.append(current)
        return groups

    def _split_large_text(self, text: str) -> list[str]:
        if self.estimate_tokens(text) <= self.max_tokens:
            return [text]
        sentences = re.split(r"(?<=[.!?])\s+", text)
        pieces, current = [], ""
        for sentence in sentences:
            if current and self.estimate_tokens(f"{current} {sentence}") > self.target_tokens:
                pieces.append(current)
                current = ""
            if self.estimate_tokens(sentence) > self.max_tokens:
                for piece in self._split_by_tokens(sentence):
                    if current:
                        pieces.append(current)
                        current = ""
                    pieces.append(piece)
            else:
                current = f"{current} {sentence}".strip()
        if current:
            pieces.append(current)
        return pieces

    @staticmethod
    def _looks_like_heading(text: str) -> bool:
        one_line = "\n" not in text and len(text) <= 160
        words = text.split()
        return one_line and 1 <= len(words) <= 14 and (
            text.isupper() or bool(re.match(r"^(\d+[.)]|[IVX]+[.)]|article\s+\d+)", text, re.I))
        )

    @staticmethod
    def _deduplicate_sources(group: list[TextBlock]) -> list[ChunkSourceModel]:
        sources = []
        for block in group:
            for source in block.sources:
                if sources and sources[-1].page_id == source.page_id:
                    sources[-1].end_offset = max(sources[-1].end_offset, source.end_offset)
                else:
                    sources.append(source.model_copy(deep=True))
        return sources

    def _split_by_tokens(self, text: str) -> list[str]:
        if not self.encoding:
            size = self.target_tokens * 4
            overlap = self.overlap_tokens * 4
            return [text[start:start + size] for start in range(0, len(text), max(1, size - overlap))]
        tokens = self.encoding.encode(text)
        step = max(1, self.target_tokens - self.overlap_tokens)
        return [self.encoding.decode(tokens[start:start + self.target_tokens]).strip()
                for start in range(0, len(tokens), step)]

    def estimate_tokens(self, text: str) -> int:
        if self.encoding:
            return max(1, len(self.encoding.encode(text)))
        return max(1, round(len(text) / 4))

    @staticmethod
    def content_hash(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()
