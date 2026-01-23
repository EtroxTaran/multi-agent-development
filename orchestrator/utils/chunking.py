"""Semantic chunking for context optimization.

Implements:
- Semantic chunking (breaks at meaning boundaries)
- Hierarchical chunking (preserves document structure)
- Selective context loading (only relevant chunks)
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ChunkStrategy(Enum):
    """Chunking strategies."""

    FIXED = "fixed"  # Fixed size chunks
    SENTENCE = "sentence"  # Sentence-based
    PARAGRAPH = "paragraph"  # Paragraph-based
    SEMANTIC = "semantic"  # Semantic boundaries
    HIERARCHICAL = "hierarchical"  # Structure-aware


@dataclass
class Chunk:
    """A chunk of content with metadata."""

    content: str
    index: int
    start_char: int
    end_char: int
    token_estimate: int
    metadata: dict = field(default_factory=dict)

    # Semantic metadata
    heading: Optional[str] = None
    section: Optional[str] = None
    importance: float = 1.0  # 0.0 to 1.0

    def to_dict(self) -> dict:
        return {
            "content": self.content,
            "index": self.index,
            "start_char": self.start_char,
            "end_char": self.end_char,
            "token_estimate": self.token_estimate,
            "metadata": self.metadata,
            "heading": self.heading,
            "section": self.section,
            "importance": self.importance,
        }


@dataclass
class ChunkingResult:
    """Result of chunking operation."""

    chunks: list[Chunk]
    total_tokens: int
    strategy_used: ChunkStrategy
    original_length: int

    def get_chunks_within_budget(self, token_budget: int) -> list[Chunk]:
        """Get chunks that fit within token budget, prioritized by importance."""
        sorted_chunks = sorted(self.chunks, key=lambda c: -c.importance)
        selected = []
        total = 0

        for chunk in sorted_chunks:
            if total + chunk.token_estimate <= token_budget:
                selected.append(chunk)
                total += chunk.token_estimate

        # Return in original order
        return sorted(selected, key=lambda c: c.index)


class SemanticChunker:
    """Semantic chunking that preserves meaning boundaries.

    Breaks text at natural semantic boundaries rather than
    arbitrary character positions, improving retrieval quality.
    """

    # Patterns for detecting semantic boundaries
    HEADING_PATTERN = re.compile(r"^#{1,6}\s+.+$", re.MULTILINE)
    PARAGRAPH_BREAK = re.compile(r"\n\n+")
    SENTENCE_END = re.compile(r"[.!?]\s+")
    CODE_BLOCK = re.compile(r"```[\s\S]*?```")
    LIST_ITEM = re.compile(r"^\s*[-*+]\s+", re.MULTILINE)

    def __init__(
        self,
        target_chunk_size: int = 500,  # Target tokens per chunk
        min_chunk_size: int = 100,
        max_chunk_size: int = 1000,
        overlap_tokens: int = 50,
    ):
        """Initialize chunker.

        Args:
            target_chunk_size: Target tokens per chunk
            min_chunk_size: Minimum chunk size
            max_chunk_size: Maximum chunk size
            overlap_tokens: Overlap between chunks for context
        """
        self.target_chunk_size = target_chunk_size
        self.min_chunk_size = min_chunk_size
        self.max_chunk_size = max_chunk_size
        self.overlap_tokens = overlap_tokens

    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count (~4 chars per token for English)."""
        return len(text) // 4

    def chunk(
        self,
        text: str,
        strategy: ChunkStrategy = ChunkStrategy.SEMANTIC,
    ) -> ChunkingResult:
        """Chunk text using specified strategy.

        Args:
            text: Text to chunk
            strategy: Chunking strategy

        Returns:
            ChunkingResult with chunks
        """
        if strategy == ChunkStrategy.FIXED:
            chunks = self._fixed_chunk(text)
        elif strategy == ChunkStrategy.SENTENCE:
            chunks = self._sentence_chunk(text)
        elif strategy == ChunkStrategy.PARAGRAPH:
            chunks = self._paragraph_chunk(text)
        elif strategy == ChunkStrategy.HIERARCHICAL:
            chunks = self._hierarchical_chunk(text)
        else:  # SEMANTIC (default)
            chunks = self._semantic_chunk(text)

        total_tokens = sum(c.token_estimate for c in chunks)

        return ChunkingResult(
            chunks=chunks,
            total_tokens=total_tokens,
            strategy_used=strategy,
            original_length=len(text),
        )

    def _fixed_chunk(self, text: str) -> list[Chunk]:
        """Simple fixed-size chunking."""
        chunks = []
        char_size = self.target_chunk_size * 4  # Convert tokens to chars
        pos = 0
        index = 0

        while pos < len(text):
            end = min(pos + char_size, len(text))
            content = text[pos:end]

            chunks.append(
                Chunk(
                    content=content,
                    index=index,
                    start_char=pos,
                    end_char=end,
                    token_estimate=self._estimate_tokens(content),
                )
            )

            pos = end - (self.overlap_tokens * 4)  # Overlap
            index += 1

        return chunks

    def _sentence_chunk(self, text: str) -> list[Chunk]:
        """Chunk by sentences, respecting token limits."""
        sentences = self.SENTENCE_END.split(text)
        chunks = []
        current_content = ""
        current_start = 0
        index = 0
        char_pos = 0

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            sentence_tokens = self._estimate_tokens(sentence)

            # If adding this sentence exceeds max, start new chunk
            if self._estimate_tokens(current_content + " " + sentence) > self.max_chunk_size:
                if current_content:
                    chunks.append(
                        Chunk(
                            content=current_content.strip(),
                            index=index,
                            start_char=current_start,
                            end_char=char_pos,
                            token_estimate=self._estimate_tokens(current_content),
                        )
                    )
                    index += 1

                current_content = sentence
                current_start = char_pos
            else:
                current_content += " " + sentence if current_content else sentence

            char_pos += len(sentence) + 1

        # Add final chunk
        if current_content:
            chunks.append(
                Chunk(
                    content=current_content.strip(),
                    index=index,
                    start_char=current_start,
                    end_char=len(text),
                    token_estimate=self._estimate_tokens(current_content),
                )
            )

        return chunks

    def _paragraph_chunk(self, text: str) -> list[Chunk]:
        """Chunk by paragraphs."""
        paragraphs = self.PARAGRAPH_BREAK.split(text)
        chunks = []
        current_content = ""
        current_start = 0
        index = 0
        char_pos = 0

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            para_tokens = self._estimate_tokens(para)

            # If paragraph alone exceeds max, split it
            if para_tokens > self.max_chunk_size:
                if current_content:
                    chunks.append(
                        Chunk(
                            content=current_content.strip(),
                            index=index,
                            start_char=current_start,
                            end_char=char_pos,
                            token_estimate=self._estimate_tokens(current_content),
                        )
                    )
                    index += 1
                    current_content = ""
                    current_start = char_pos

                # Split large paragraph by sentences
                sub_chunks = self._sentence_chunk(para)
                for sub in sub_chunks:
                    sub.index = index
                    sub.start_char += char_pos
                    sub.end_char += char_pos
                    chunks.append(sub)
                    index += 1

            elif self._estimate_tokens(current_content + "\n\n" + para) > self.max_chunk_size:
                if current_content:
                    chunks.append(
                        Chunk(
                            content=current_content.strip(),
                            index=index,
                            start_char=current_start,
                            end_char=char_pos,
                            token_estimate=self._estimate_tokens(current_content),
                        )
                    )
                    index += 1

                current_content = para
                current_start = char_pos
            else:
                current_content += "\n\n" + para if current_content else para

            char_pos += len(para) + 2

        if current_content:
            chunks.append(
                Chunk(
                    content=current_content.strip(),
                    index=index,
                    start_char=current_start,
                    end_char=len(text),
                    token_estimate=self._estimate_tokens(current_content),
                )
            )

        return chunks

    def _semantic_chunk(self, text: str) -> list[Chunk]:
        """Chunk at semantic boundaries (headings, code blocks, etc.)."""
        chunks = []
        index = 0

        # First, identify code blocks and protect them
        code_blocks = list(self.CODE_BLOCK.finditer(text))
        code_positions = [(m.start(), m.end()) for m in code_blocks]

        # Find all headings
        headings = list(self.HEADING_PATTERN.finditer(text))

        if not headings:
            # No headings, fall back to paragraph chunking
            return self._paragraph_chunk(text)

        # Create sections based on headings
        sections = []
        for i, heading in enumerate(headings):
            start = heading.start()
            end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
            heading_text = heading.group().strip("#").strip()

            sections.append(
                {
                    "heading": heading_text,
                    "start": start,
                    "end": end,
                    "content": text[start:end],
                }
            )

        # Process each section
        current_section = None
        for section in sections:
            current_section = section["heading"]
            content = section["content"]
            section_tokens = self._estimate_tokens(content)

            if section_tokens <= self.max_chunk_size:
                # Section fits in one chunk
                chunks.append(
                    Chunk(
                        content=content.strip(),
                        index=index,
                        start_char=section["start"],
                        end_char=section["end"],
                        token_estimate=section_tokens,
                        heading=current_section,
                        section=current_section,
                        importance=self._calculate_importance(content, current_section),
                    )
                )
                index += 1
            else:
                # Split section by paragraphs
                sub_chunks = self._paragraph_chunk(content)
                for sub in sub_chunks:
                    sub.index = index
                    sub.start_char += section["start"]
                    sub.end_char += section["start"]
                    sub.heading = current_section
                    sub.section = current_section
                    sub.importance = self._calculate_importance(sub.content, current_section)
                    chunks.append(sub)
                    index += 1

        return chunks

    def _hierarchical_chunk(self, text: str) -> list[Chunk]:
        """Structure-aware chunking preserving document hierarchy."""
        # Similar to semantic but maintains parent-child relationships
        chunks = self._semantic_chunk(text)

        # Add hierarchy metadata
        heading_stack = []
        for chunk in chunks:
            if chunk.heading:
                # Determine heading level
                heading_match = re.match(r"^(#+)", chunk.content)
                if heading_match:
                    level = len(heading_match.group(1))
                    # Pop stack to this level
                    heading_stack = heading_stack[: level - 1]
                    heading_stack.append(chunk.heading)

                chunk.metadata["hierarchy"] = list(heading_stack)
                chunk.metadata["depth"] = len(heading_stack)

        return chunks

    def _calculate_importance(self, content: str, heading: Optional[str]) -> float:
        """Calculate importance score for a chunk.

        Higher scores for:
        - Headings with keywords like "Important", "Warning", etc.
        - Code examples
        - Lists (often key points)
        - Shorter, focused content
        """
        score = 0.5  # Base score

        content_lower = content.lower()
        heading_lower = (heading or "").lower()

        # Important keywords in heading
        important_keywords = ["important", "warning", "note", "critical", "key", "summary"]
        if any(kw in heading_lower for kw in important_keywords):
            score += 0.2

        # Code blocks indicate examples
        if "```" in content:
            score += 0.1

        # Lists often contain key information
        if self.LIST_ITEM.search(content):
            score += 0.1

        # Shorter chunks are often more focused
        tokens = self._estimate_tokens(content)
        if tokens < self.target_chunk_size / 2:
            score += 0.1

        return min(1.0, score)


class SelectiveContextLoader:
    """Loads only relevant context chunks based on query.

    Instead of loading entire documents into context,
    selects and prioritizes relevant chunks.
    """

    def __init__(self, chunker: Optional[SemanticChunker] = None):
        """Initialize loader.

        Args:
            chunker: Chunker to use (creates default if not provided)
        """
        self.chunker = chunker or SemanticChunker()
        self._document_chunks: dict[str, ChunkingResult] = {}

    def index_document(self, doc_id: str, content: str) -> ChunkingResult:
        """Index a document for selective loading.

        Args:
            doc_id: Unique document identifier
            content: Document content

        Returns:
            ChunkingResult
        """
        result = self.chunker.chunk(content, ChunkStrategy.SEMANTIC)
        self._document_chunks[doc_id] = result
        return result

    def select_context(
        self,
        query: str,
        doc_ids: Optional[list[str]] = None,
        token_budget: int = 4000,
    ) -> str:
        """Select relevant context for a query.

        Args:
            query: The query/prompt needing context
            doc_ids: Documents to consider (all if None)
            token_budget: Maximum tokens to return

        Returns:
            Selected context string
        """
        doc_ids = doc_ids or list(self._document_chunks.keys())
        query_lower = query.lower()
        query_terms = set(query_lower.split())

        # Score all chunks
        scored_chunks = []
        for doc_id in doc_ids:
            if doc_id not in self._document_chunks:
                continue

            for chunk in self._document_chunks[doc_id].chunks:
                score = self._score_relevance(chunk, query_terms)
                if score > 0:
                    scored_chunks.append((chunk, score, doc_id))

        # Sort by score
        scored_chunks.sort(key=lambda x: -x[1])

        # Select chunks within budget
        selected = []
        total_tokens = 0

        for chunk, score, doc_id in scored_chunks:
            if total_tokens + chunk.token_estimate > token_budget:
                continue

            selected.append((chunk, doc_id))
            total_tokens += chunk.token_estimate

        # Build context string
        context_parts = []
        for chunk, doc_id in selected:
            header = f"[From {doc_id}"
            if chunk.section:
                header += f" - {chunk.section}"
            header += "]"

            context_parts.append(f"{header}\n{chunk.content}")

        return "\n\n---\n\n".join(context_parts)

    def _score_relevance(self, chunk: Chunk, query_terms: set[str]) -> float:
        """Score chunk relevance to query terms."""
        content_lower = chunk.content.lower()
        content_terms = set(content_lower.split())

        # Term overlap
        overlap = len(query_terms & content_terms)
        if overlap == 0:
            return 0.0

        # Base score from overlap
        score = overlap / len(query_terms)

        # Boost by chunk importance
        score *= chunk.importance

        # Boost if terms appear in heading
        if chunk.heading:
            heading_lower = chunk.heading.lower()
            if any(term in heading_lower for term in query_terms):
                score *= 1.5

        return score

    def get_document_summary(self, doc_id: str) -> Optional[dict]:
        """Get summary of indexed document.

        Returns:
            Summary dict or None if not indexed
        """
        if doc_id not in self._document_chunks:
            return None

        result = self._document_chunks[doc_id]
        return {
            "doc_id": doc_id,
            "chunk_count": len(result.chunks),
            "total_tokens": result.total_tokens,
            "strategy": result.strategy_used.value,
            "sections": list(set(c.section for c in result.chunks if c.section)),
        }
