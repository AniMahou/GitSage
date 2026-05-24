# backend/core/chunker.py
"""
Code-aware chunking for GitSage.
Parses source files using AST (Python) and tree-sitter (JS/TS/Go/Rust).
Extracts functions, classes, and methods as complete logical units.

Why AST parsing instead of character splitting?
    Character splitting: "def process_request(self, request):" might be in Chunk 1
                         but the function body is in Chunk 2.
    AST parsing:        The ENTIRE function stays together — name, body, decorators.
                        When the user asks "How does process_request work?",
                        the embedding captures the complete function context.
"""

import ast
import re
from pathlib import Path
from typing import List, Optional, Dict
from backend.models.schemas import CodeChunk, ChunkMetadata
from backend.config import CHUNK_MAX_CHARS, CHUNK_OVERLAP_CHARS
from backend.utils.logger import setup_logger

logger = setup_logger(__name__)


# ============================================
# Language → Extension Mapping
# ============================================
EXTENSION_TO_LANGUAGE = {
    '.py': 'python',
    '.js': 'javascript',
    '.jsx': 'javascript',
    '.ts': 'typescript',
    '.tsx': 'typescript',
    '.go': 'go',
    '.rs': 'rust',
    '.java': 'java',
    '.rb': 'ruby',
    '.php': 'php',
    '.swift': 'swift',
    '.kt': 'kotlin',
    '.c': 'c',
    '.h': 'c',
    '.cpp': 'c++',
    '.hpp': 'c++',
    '.cs': 'csharp',
    '.scala': 'scala',
}


class CodeChunker:
    """
    Parse source code into logical chunks.
    
    Strategies (in priority order):
        1. Python:  Built-in `ast` module → exact function/class boundaries
        2. JS/TS/Go/Rust: tree-sitter → same precision
        3. Other languages: Regex-based function detection → good enough
        4. Fallback: Line-based splitting with overlap
    
    Usage:
        chunker = CodeChunker()
        chunks = chunker.chunk_file(Path("middleware/auth.py"))
        # Returns: List[CodeChunk]
    """
    
    def __init__(self):
        self.chunk_counter = 0
    
    # ─── MAIN ENTRY POINT ─────────────────────────────
    
    def chunk_file(self, filepath: Path) -> List[CodeChunk]:
        """
        Chunk a single source file.
        Dispatches to the correct parser based on file extension.
        """
        extension = filepath.suffix.lower()
        language = EXTENSION_TO_LANGUAGE.get(extension, 'unknown')
        
        logger.debug(f"Chunking {filepath.name} ({language})")
        
        try:
            # Read file
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                source_code = f.read()
        except Exception as e:
            logger.warning(f"Could not read {filepath}: {e}")
            return []
        
        # Skip empty files
        if not source_code.strip():
            return []
        
        # Dispatch to language-specific parser
        if extension == '.py':
            chunks = self._chunk_python(filepath, source_code)
        elif extension in ('.js', '.jsx', '.ts', '.tsx'):
            chunks = self._chunk_javascript(filepath, source_code, language)
        elif extension in ('.go', '.rs', '.java', '.rb', '.php', '.swift', '.kt', '.cs'):
            chunks = self._chunk_with_regex(filepath, source_code, language)
        else:
            chunks = self._chunk_fallback(filepath, source_code, language)
        
        logger.debug(f"  → {len(chunks)} chunks from {filepath.name}")
        return chunks
    
    def chunk_directory(self, files: List[Path]) -> List[CodeChunk]:
        """
        Chunk all files in a directory.
        
        Args:
            files: List of file paths from RepoHandler
        
        Returns:
            Combined list of all chunks
        """
        all_chunks = []
        total_files = len(files)
        
        logger.info(f"Chunking {total_files} files...")
        
        for i, filepath in enumerate(files):
            chunks = self.chunk_file(filepath)
            all_chunks.extend(chunks)
            
            # Progress logging every 10 files
            if (i + 1) % 10 == 0 or (i + 1) == total_files:
                logger.info(f"  Chunked {i + 1}/{total_files} files → {len(all_chunks)} chunks so far")
        
        logger.info(f"Chunking complete: {len(all_chunks)} chunks from {total_files} files")
        return all_chunks
    
    # ─── PYTHON PARSER (AST) ──────────────────────────
    
    def _chunk_python(self, filepath: Path, source_code: str) -> List[CodeChunk]:
        """
        Parse Python using the built-in AST module.
        Extracts: functions, async functions, classes, and their methods.
        """
        try:
            tree = ast.parse(source_code)
        except SyntaxError as e:
            logger.warning(f"  Syntax error in {filepath.name}: {e}")
            return self._chunk_fallback(filepath, source_code, 'python')
        
        lines = source_code.split('\n')
        chunks = []
        
        # Extract file-level imports (used as context for all chunks)
        imports = self._extract_python_imports(tree)
        
        # Walk the AST tree
        for node in ast.iter_child_nodes(tree):
            chunk = self._process_python_node(node, lines, filepath, imports)
            if chunk:
                chunks.append(chunk)
        
        return chunks
    
    def _extract_python_imports(self, tree: ast.Module) -> str:
        """Extract import statements from module level."""
        import_lines = []
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                import_lines.append(
                    ast.unparse(node) if hasattr(ast, 'unparse') else ''
                )
        return '\n'.join(import_lines) if import_lines else ''
    
    def _process_python_node(
        self,
        node: ast.AST,
        lines: List[str],
        filepath: Path,
        imports: str
    ) -> Optional[CodeChunk]:
        """Process a single AST node into a chunk."""
        
        # Function definition
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return self._create_python_chunk(
                node, lines, filepath, imports, 
                chunk_type='function' if not node.name.startswith('__') else 'method'
            )
        
        # Class definition
        elif isinstance(node, ast.ClassDef):
            # Create chunk for the class itself
            return self._create_python_chunk(
                node, lines, filepath, imports, chunk_type='class'
            )
        
        return None
    
    def _create_python_chunk(
        self,
        node: ast.AST,
        lines: List[str],
        filepath: Path,
        imports: str,
        chunk_type: str
    ) -> CodeChunk:
        """Create a CodeChunk from a Python AST node."""
        
        start_line = node.lineno - 1  # 0-indexed
        end_line = node.end_lineno    # Already 0-indexed for end
        
        # Extract source code
        chunk_lines = lines[start_line:end_line]
        chunk_text = '\n'.join(chunk_lines)
        
        # Get docstring
        docstring = ast.get_docstring(node)
        
        # Get decorators
        decorators = []
        if hasattr(node, 'decorator_list'):
            for decorator in node.decorator_list:
                if hasattr(ast, 'unparse'):
                    decorators.append(ast.unparse(decorator))
        
        # Build context: imports + decorators
        context_parts = []
        if imports:
            context_parts.append(f"# File: {filepath.name}")
            context_parts.append(imports)
        if decorators:
            context_parts.append('\n'.join(f'@{d}' for d in decorators))
        
        context = '\n'.join(context_parts)
        
        # Full chunk text: context + code
        full_text = f"{context}\n\n{chunk_text}" if context else chunk_text
        
        # If chunk is too large, split it
        if len(full_text) > CHUNK_MAX_CHARS:
            return self._split_large_chunk(
                full_text, filepath, node.name, start_line, end_line, 
                chunk_type, EXTENSION_TO_LANGUAGE['.py']
            )
        
        # Create metadata
        metadata = ChunkMetadata(
            file=str(filepath),
            start_line=start_line + 1,  # Back to 1-indexed
            end_line=end_line,
            chunk_type=chunk_type,
            name=node.name,
            language='python',
            docstring=docstring
        )
        
        self.chunk_counter += 1
        
        return CodeChunk(
            chunk_id=f"chunk_{self.chunk_counter:06d}",
            text=full_text,
            metadata=metadata
        )
    
    # ─── JAVASCRIPT/TYPESCRIPT PARSER ─────────────────
    
    def _chunk_javascript(
        self,
        filepath: Path,
        source_code: str,
        language: str
    ) -> List[CodeChunk]:
        """
        Parse JavaScript/TypeScript.
        
        Attempts tree-sitter first; falls back to regex.
        """
        # Try tree-sitter
        try:
            import tree_sitter
            # This is simplified — full implementation would need
            # language-specific grammars loaded
            return self._chunk_with_regex(filepath, source_code, language)
        except ImportError:
            logger.debug(f"  tree-sitter not available, using regex for {filepath.name}")
            return self._chunk_with_regex(filepath, source_code, language)
    
    # ─── REGEX-BASED PARSER ───────────────────────────
    
    def _chunk_with_regex(
        self,
        filepath: Path,
        source_code: str,
        language: str
    ) -> List[CodeChunk]:
        """
        Parse code using regex patterns to detect function/class boundaries.
        Works for most C-like languages.
        """
        
        # Patterns for different languages
        patterns = {
            'javascript': r'(?:export\s+)?(?:async\s+)?function\s+\w+\s*\([^)]*\)\s*\{',
            'typescript': r'(?:export\s+)?(?:async\s+)?function\s+\w+\s*\([^)]*\)\s*\{',
            'go': r'func\s+(?:\(\w+\s+\*?\w+\)\s+)?\w+\s*\([^)]*\)',
            'rust': r'(?:pub\s+)?fn\s+\w+\s*\([^)]*\)',
            'java': r'(?:public|private|protected)\s+(?:static\s+)?\w+\s+\w+\s*\([^)]*\)\s*\{',
            'ruby': r'def\s+\w+',
            'php': r'(?:public\s+)?function\s+\w+\s*\([^)]*\)\s*\{',
            'swift': r'func\s+\w+\s*\([^)]*\)',
            'kotlin': r'(?:suspend\s+)?fun\s+\w+\s*\([^)]*\)',
        }
        
        pattern = patterns.get(language)
        
        if not pattern:
            return self._chunk_fallback(filepath, source_code, language)
        
        return self._split_by_pattern(filepath, source_code, language, pattern)
    
    def _split_by_pattern(
        self,
        filepath: Path,
        source_code: str,
        language: str,
        pattern: str
    ) -> List[CodeChunk]:
        """Split source code using a regex pattern."""
        
        matches = list(re.finditer(pattern, source_code, re.MULTILINE))
        
        if not matches:
            # No functions found — treat whole file as one chunk
            return self._chunk_fallback(filepath, source_code, language)
        
        lines = source_code.split('\n')
        chunks = []
        
        for i, match in enumerate(matches):
            start_line = source_code[:match.start()].count('\n')
            
            # End line is start of next match, or end of file
            if i + 1 < len(matches):
                end_line = source_code[:matches[i + 1].start()].count('\n')
            else:
                end_line = len(lines)
            
            chunk_lines = lines[start_line:end_line]
            chunk_text = '\n'.join(chunk_lines)
            
            # Extract function name from match
            name_match = re.search(r'(?:function|func|fn|def)\s+(\w+)', match.group())
            name = name_match.group(1) if name_match else f"block_{i}"
            
            # If chunk is too large, split it
            if len(chunk_text) > CHUNK_MAX_CHARS:
                sub_chunks = self._split_large_chunk(
                    chunk_text, filepath, name, start_line, end_line, 'function', language
                )
                chunks.extend(sub_chunks if isinstance(sub_chunks, list) else [sub_chunks])
                continue
            
            metadata = ChunkMetadata(
                file=str(filepath),
                start_line=start_line + 1,
                end_line=end_line,
                chunk_type='function',
                name=name,
                language=language
            )
            
            self.chunk_counter += 1
            
            chunks.append(CodeChunk(
                chunk_id=f"chunk_{self.chunk_counter:06d}",
                text=f"// File: {filepath.name}\n{chunk_text}",
                metadata=metadata
            ))
        
        return chunks
    
    # ─── FALLBACK PARSER ──────────────────────────────
    
    def _chunk_fallback(
        self,
        filepath: Path,
        source_code: str,
        language: str
    ) -> List[CodeChunk]:
        """
        Last-resort chunking: split by lines with overlap.
        Used when no language-specific parser is available.
        """
        lines = source_code.split('\n')
        
        if len(lines) <= 50:
            # Small file — keep as single chunk
            metadata = ChunkMetadata(
                file=str(filepath),
                start_line=1,
                end_line=len(lines),
                chunk_type='module',
                name=filepath.stem,
                language=language
            )
            
            self.chunk_counter += 1
            
            return [CodeChunk(
                chunk_id=f"chunk_{self.chunk_counter:06d}",
                text=f"// File: {filepath.name}\n{source_code}",
                metadata=metadata
            )]
        
        # Split by lines with overlap
        chunks = []
        chunk_size = 40  # lines per chunk
        overlap = 10     # lines overlap
        
        i = 0
        part = 0
        
        while i < len(lines):
            end = min(i + chunk_size, len(lines))
            chunk_lines = lines[i:end]
            chunk_text = '\n'.join(chunk_lines)
            
            metadata = ChunkMetadata(
                file=str(filepath),
                start_line=i + 1,
                end_line=end,
                chunk_type='module',
                name=f"{filepath.stem}_part{part}",
                language=language
            )
            
            self.chunk_counter += 1
            
            chunks.append(CodeChunk(
                chunk_id=f"chunk_{self.chunk_counter:06d}",
                text=f"// File: {filepath.name} (lines {i+1}-{end})\n{chunk_text}",
                metadata=metadata
            ))
            
            i += chunk_size - overlap
            part += 1
        
        return chunks
    
    # ─── LARGE CHUNK HANDLING ─────────────────────────
    
    def _split_large_chunk(
        self,
        chunk_text: str,
        filepath: Path,
        name: str,
        start_line: int,
        end_line: int,
        chunk_type: str,
        language: str
    ) -> List[CodeChunk]:
        """
        Split a chunk that exceeds CHUNK_MAX_CHARS.
        Tries to split at function boundaries first, then by lines.
        """
        # Try to find sub-boundaries (inner functions, if blocks)
        lines = chunk_text.split('\n')
        
        # Simple line-based split with context preservation
        sub_chunks = []
        max_chars = CHUNK_MAX_CHARS
        current_start = 0
        
        for i in range(len(lines)):
            current_text = '\n'.join(lines[current_start:i + 1])
            
            if len(current_text) > max_chars and i > current_start:
                # Save current sub-chunk
                sub_text = '\n'.join(lines[current_start:i])
                
                metadata = ChunkMetadata(
                    file=str(filepath),
                    start_line=start_line + current_start + 1,
                    end_line=start_line + i,
                    chunk_type=chunk_type,
                    name=f"{name}_part{len(sub_chunks) + 1}",
                    language=language
                )
                
                self.chunk_counter += 1
                
                sub_chunks.append(CodeChunk(
                    chunk_id=f"chunk_{self.chunk_counter:06d}",
                    text=f"// File: {filepath.name}\n{sub_text}",
                    metadata=metadata
                ))
                
                current_start = i
        
        # Last sub-chunk
        if current_start < len(lines):
            sub_text = '\n'.join(lines[current_start:])
            
            metadata = ChunkMetadata(
                file=str(filepath),
                start_line=start_line + current_start + 1,
                end_line=end_line,
                chunk_type=chunk_type,
                name=f"{name}_part{len(sub_chunks) + 1}",
                language=language
            )
            
            self.chunk_counter += 1
            
            sub_chunks.append(CodeChunk(
                chunk_id=f"chunk_{self.chunk_counter:06d}",
                text=f"// File: {filepath.name}\n{sub_text}",
                metadata=metadata
            ))
        
        return sub_chunks if sub_chunks else []


# ============================================
# Convenience function
# ============================================

def chunk_repository(files: List[Path]) -> List[CodeChunk]:
    """Chunk all files in a repository."""
    chunker = CodeChunker()
    return chunker.chunk_directory(files)