"""
Document chunking utilities for text and code with token-aware splitting.
"""

from typing import List, Dict, Any, Optional
import re
from dataclasses import dataclass

try:
    import tiktoken
except ImportError:
    tiktoken = None
    print("Warning: tiktoken not installed. Install with: pip install tiktoken")

from .config import ChunkingConfig


@dataclass
class Chunk:
    """Represents a document chunk."""
    text: str
    metadata: Dict[str, Any]
    start_char: int
    end_char: int
    token_count: int


class TokenAwareChunker:
    """Base class for token-aware document chunking."""
    
    def __init__(self, config: ChunkingConfig):
        """
        Initialize chunker with configuration.
        
        Args:
            config: ChunkingConfig instance
        """
        self.config = config
        
        # Initialize tiktoken encoder
        if tiktoken is not None:
            try:
                self.encoder = tiktoken.get_encoding(config.encoding_name)
            except Exception as e:
                print(f"Warning: Failed to load tiktoken encoding: {e}")
                self.encoder = None
        else:
            self.encoder = None
    
    def count_tokens(self, text: str) -> int:
        """Count tokens in text."""
        if self.encoder:
            return len(self.encoder.encode(text))
        else:
            # Fallback: rough estimate (1 token ≈ 4 characters)
            return len(text) // 4
    
    def encode(self, text: str) -> List[int]:
        """Encode text to tokens."""
        if self.encoder:
            return self.encoder.encode(text)
        else:
            raise ValueError("Tiktoken encoder not available")
    
    def decode(self, tokens: List[int]) -> str:
        """Decode tokens to text."""
        if self.encoder:
            return self.encoder.decode(tokens)
        else:
            raise ValueError("Tiktoken encoder not available")


class TextChunker(TokenAwareChunker):
    """
    Chunk text documents with token-aware splitting and overlap.
    
    Preserves paragraph boundaries and ensures semantic coherence.
    """
    
    def chunk_text(
        self,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
        chunk_size: Optional[int] = None,
        overlap: Optional[int] = None
    ) -> List[Chunk]:
        """
        Chunk text into overlapping segments.
        
        Args:
            text: Text to chunk
            metadata: Optional metadata to attach to each chunk
            chunk_size: Override default chunk size
            overlap: Override default overlap
            
        Returns:
            List of Chunk objects
        """
        if metadata is None:
            metadata = {}
        
        chunk_size = chunk_size or self.config.text_chunk_size
        overlap = overlap or self.config.overlap
        
        # Split into paragraphs first (preserve semantic boundaries)
        paragraphs = self._split_into_paragraphs(text)
        
        chunks = []
        current_chunk_tokens = []
        current_chunk_text = []
        current_start_char = 0
        
        for para in paragraphs:
            para_tokens = self.encode(para) if self.encoder else para.split()
            
            # If single paragraph exceeds chunk size, split it
            if len(para_tokens) > chunk_size:
                # First, add any accumulated content
                if current_chunk_tokens:
                    chunk_text = " ".join(current_chunk_text)
                    chunks.append(Chunk(
                        text=chunk_text,
                        metadata=metadata.copy(),
                        start_char=current_start_char,
                        end_char=current_start_char + len(chunk_text),
                        token_count=len(current_chunk_tokens)
                    ))
                    current_chunk_tokens = []
                    current_chunk_text = []
                
                # Split long paragraph
                for i in range(0, len(para_tokens), chunk_size - overlap):
                    chunk_tokens = para_tokens[i:i + chunk_size]
                    chunk_text = self.decode(chunk_tokens) if self.encoder else " ".join(chunk_tokens)
                    
                    chunks.append(Chunk(
                        text=chunk_text,
                        metadata=metadata.copy(),
                        start_char=current_start_char,
                        end_char=current_start_char + len(chunk_text),
                        token_count=len(chunk_tokens)
                    ))
                    current_start_char += len(chunk_text)
                
                continue
            
            # Check if adding paragraph would exceed chunk size
            if len(current_chunk_tokens) + len(para_tokens) > chunk_size:
                # Save current chunk
                if current_chunk_tokens:
                    chunk_text = " ".join(current_chunk_text)
                    chunks.append(Chunk(
                        text=chunk_text,
                        metadata=metadata.copy(),
                        start_char=current_start_char,
                        end_char=current_start_char + len(chunk_text),
                        token_count=len(current_chunk_tokens)
                    ))
                
                # Start new chunk with overlap
                if overlap > 0 and len(current_chunk_tokens) > overlap:
                    overlap_tokens = current_chunk_tokens[-overlap:]
                    current_chunk_tokens = overlap_tokens
                    current_chunk_text = [self.decode(overlap_tokens) if self.encoder else " ".join(overlap_tokens)]
                    current_start_char = chunks[-1].end_char - len(current_chunk_text[0])
                else:
                    current_chunk_tokens = []
                    current_chunk_text = []
                    current_start_char = chunks[-1].end_char if chunks else 0
            
            # Add paragraph to current chunk
            current_chunk_tokens.extend(para_tokens)
            current_chunk_text.append(para)
        
        # Add final chunk
        if current_chunk_tokens:
            chunk_text = " ".join(current_chunk_text)
            chunks.append(Chunk(
                text=chunk_text,
                metadata=metadata.copy(),
                start_char=current_start_char,
                end_char=current_start_char + len(chunk_text),
                token_count=len(current_chunk_tokens)
            ))
        
        return chunks
    
    def _split_into_paragraphs(self, text: str) -> List[str]:
        """Split text into paragraphs."""
        # Split on double newlines or multiple newlines
        paragraphs = re.split(r'\n\s*\n', text)
        # Filter out empty paragraphs
        return [p.strip() for p in paragraphs if p.strip()]


class CodeChunker(TokenAwareChunker):
    """
    Chunk code documents with awareness of function/class boundaries.
    
    Preserves code structure and indentation.
    """
    
    def chunk_code(
        self,
        code: str,
        language: str = "python",
        metadata: Optional[Dict[str, Any]] = None,
        chunk_size: Optional[int] = None,
        overlap: Optional[int] = None
    ) -> List[Chunk]:
        """
        Chunk code into function/class-level segments.
        
        Args:
            code: Code to chunk
            language: Programming language
            metadata: Optional metadata
            chunk_size: Override default chunk size
            overlap: Override default overlap
            
        Returns:
            List of Chunk objects
        """
        if metadata is None:
            metadata = {}
        
        metadata["type"] = "code"
        metadata["language"] = language
        
        chunk_size = chunk_size or self.config.code_chunk_size
        overlap = overlap or self.config.overlap
        
        # Language-specific splitting
        if language == "python":
            return self._chunk_python_code(code, metadata, chunk_size, overlap)
        else:
            # Generic code chunking (split on blank lines)
            return self._chunk_generic_code(code, metadata, chunk_size, overlap)
    
    def _chunk_python_code(
        self,
        code: str,
        metadata: Dict[str, Any],
        chunk_size: int,
        overlap: int
    ) -> List[Chunk]:
        """Chunk Python code at function/class boundaries."""
        lines = code.split('\n')
        chunks = []
        current_chunk_lines = []
        current_start_line = 0
        
        for i, line in enumerate(lines):
            # Detect function or class definitions
            if re.match(r'^(def |class )', line) and current_chunk_lines:
                # Check if current chunk exceeds size
                chunk_text = '\n'.join(current_chunk_lines)
                token_count = self.count_tokens(chunk_text)
                
                if token_count >= chunk_size:
                    # Save current chunk
                    chunks.append(Chunk(
                        text=chunk_text,
                        metadata=metadata.copy(),
                        start_char=current_start_line,
                        end_char=i,
                        token_count=token_count
                    ))
                    
                    # Start new chunk with overlap
                    if overlap > 0:
                        overlap_lines = current_chunk_lines[-overlap:]
                        current_chunk_lines = overlap_lines
                        current_start_line = i - len(overlap_lines)
                    else:
                        current_chunk_lines = []
                        current_start_line = i
            
            current_chunk_lines.append(line)
        
        # Add final chunk
        if current_chunk_lines:
            chunk_text = '\n'.join(current_chunk_lines)
            chunks.append(Chunk(
                text=chunk_text,
                metadata=metadata.copy(),
                start_char=current_start_line,
                end_char=len(lines),
                token_count=self.count_tokens(chunk_text)
            ))
        
        return chunks
    
    def _chunk_generic_code(
        self,
        code: str,
        metadata: Dict[str, Any],
        chunk_size: int,
        overlap: int
    ) -> List[Chunk]:
        """Generic code chunking (split on blank lines)."""
        # Split on blank lines
        blocks = re.split(r'\n\s*\n', code)
        
        chunks = []
        current_chunk_blocks = []
        current_token_count = 0
        current_start_char = 0
        
        for block in blocks:
            block_tokens = self.count_tokens(block)
            
            if current_token_count + block_tokens > chunk_size and current_chunk_blocks:
                # Save current chunk
                chunk_text = '\n\n'.join(current_chunk_blocks)
                chunks.append(Chunk(
                    text=chunk_text,
                    metadata=metadata.copy(),
                    start_char=current_start_char,
                    end_char=current_start_char + len(chunk_text),
                    token_count=current_token_count
                ))
                
                # Start new chunk
                current_chunk_blocks = []
                current_token_count = 0
                current_start_char += len(chunk_text) + 2  # +2 for \n\n
            
            current_chunk_blocks.append(block)
            current_token_count += block_tokens
        
        # Add final chunk
        if current_chunk_blocks:
            chunk_text = '\n\n'.join(current_chunk_blocks)
            chunks.append(Chunk(
                text=chunk_text,
                metadata=metadata.copy(),
                start_char=current_start_char,
                end_char=current_start_char + len(chunk_text),
                token_count=current_token_count
            ))
        
        return chunks


# Factory function
def create_chunker(
    config: Optional[ChunkingConfig] = None,
    chunker_type: str = "text"
) -> TokenAwareChunker:
    """
    Create a chunker instance.
    
    Args:
        config: ChunkingConfig instance (uses defaults if None)
        chunker_type: "text" or "code"
        
    Returns:
        TokenAwareChunker instance
    """
    if config is None:
        config = ChunkingConfig()
    
    if chunker_type == "text":
        return TextChunker(config)
    elif chunker_type == "code":
        return CodeChunker(config)
    else:
        raise ValueError(f"Unknown chunker type: {chunker_type}")
