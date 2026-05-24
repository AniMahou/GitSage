# backend/core/repo_handler.py
"""
Repository handler for GitSage.
Clones GitHub repos, extracts ZIPs, and walks file trees.
"""

import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse

import git
from git.exc import GitCommandError

from backend.config import REPO_STORAGE_PATH
from backend.utils.logger import setup_logger

logger = setup_logger(__name__)


# ============================================
# Supported file extensions
# ============================================
# Languages we have dedicated parsers for
SUPPORTED_EXTENSIONS = {
    '.py',    # Python (AST built-in)
    '.js',    # JavaScript
    '.jsx',   # React JSX
    '.ts',    # TypeScript
    '.tsx',   # React TSX
    '.go',    # Go
    '.rs',    # Rust
    '.java',  # Java
    '.rb',    # Ruby
    '.php',   # PHP
    '.swift', # Swift
    '.kt',    # Kotlin
    '.c',     # C
    '.h',     # C header
    '.cpp',   # C++
    '.hpp',   # C++ header
    '.cs',    # C#
    '.scala', # Scala
}

# Directories to skip during file walk
SKIP_DIRECTORIES = {
    '.git',
    'node_modules',
    '__pycache__',
    'venv',
    '.venv',
    'env',
    '.env',
    'dist',
    'build',
    '.tox',
    '.eggs',
    '.mypy_cache',
    '.pytest_cache',
    '.next',
    'vendor',
    'bower_components',
    '.sass-cache',
}

# Files to skip
SKIP_FILES = {
    '.DS_Store',
    'Thumbs.db',
    'package-lock.json',
    'yarn.lock',
    'pnpm-lock.yaml',
    'poetry.lock',
    'Pipfile.lock',
    '.gitignore',
    '.gitattributes',
}


class RepoHandler:
    """
    Handles repository operations: clone, validate, walk file tree.
    
    Usage:
        handler = RepoHandler()
        repo_path = handler.clone("https://github.com/user/repo", "session_123")
        files = handler.get_source_files(repo_path)
    """
    
    def __init__(self):
        # Ensure storage directory exists
        REPO_STORAGE_PATH.mkdir(parents=True, exist_ok=True)
    
    # ─── VALIDATION ────────────────────────────────────
    
    def validate_url(self, url: str) -> bool:
        """
        Check if a URL looks like a valid Git repository.
        
        Returns:
            True if URL is valid, False otherwise
        """
        if not url:
            return False
        
        # Must be a URL
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return False
        
        # Must be a known Git host
        valid_hosts = ['github.com', 'gitlab.com', 'bitbucket.org']
        host = parsed.netloc.lower()
        # Remove port if present
        host = host.split(':')[0]
        
        if host not in valid_hosts:
            logger.warning(f"Unknown Git host: {host}")
            # We'll still try — might be a self-hosted instance
        
        return True
    
    def check_repo_accessible(self, url: str) -> bool:
        """
        Check if a repository is accessible (exists and is public).
        Uses git ls-remote which is lightweight — no clone needed.
        
        Returns:
            True if accessible, False otherwise
        """
        try:
            git.cmd.Git().ls_remote(url, timeout=10)
            return True
        except GitCommandError as e:
            logger.error(f"Repository not accessible: {url}")
            logger.error(f"  Error: {e.stderr}")
            return False
        except Exception as e:
            logger.error(f"Failed to check repository: {e}")
            return False
    
    # ─── CLONE ─────────────────────────────────────────
    
    def clone(self, url: str, session_id: str) -> Path:
        """
        Clone a repository to local storage.
        
        Args:
            url: GitHub/GitLab URL
            session_id: Unique session identifier
        
        Returns:
            Path to the cloned repository
        
        Raises:
            ValueError: If URL is invalid
            RuntimeError: If clone fails
        """
        # Validate
        if not self.validate_url(url):
            raise ValueError(f"Invalid repository URL: {url}")
        
        # Create session directory
        repo_path = REPO_STORAGE_PATH / session_id
        
        # Clean up if exists
        if repo_path.exists():
            logger.info(f"Removing existing repo at {repo_path}")
            shutil.rmtree(repo_path)
        
        repo_path.mkdir(parents=True, exist_ok=True)
        
        # Clone
        logger.info(f"Cloning {url} → {repo_path}")
        
        try:
            git.Repo.clone_from(
                url,
                str(repo_path),
                depth=1,          # Only latest commit (faster)
                single_branch=True # Don't fetch all branches
            )
            
            logger.info(f"Clone complete: {repo_path}")
            return repo_path
            
        except GitCommandError as e:
            logger.error(f"Clone failed: {e.stderr}")
            # Clean up partial clone
            if repo_path.exists():
                shutil.rmtree(repo_path)
            raise RuntimeError(f"Failed to clone repository: {e.stderr}")
    
    # ─── ZIP EXTRACTION ────────────────────────────────
    
    def extract_zip(self, zip_file, session_id: str) -> Path:
        """
        Extract an uploaded ZIP file.
        
        Args:
            zip_file: File-like object (from Streamlit upload)
            session_id: Unique session identifier
        
        Returns:
            Path to extracted contents
        """
        repo_path = REPO_STORAGE_PATH / session_id
        
        if repo_path.exists():
            shutil.rmtree(repo_path)
        
        repo_path.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Extracting ZIP to {repo_path}")
        
        with zipfile.ZipFile(zip_file) as zf:
            zf.extractall(repo_path)
        
        logger.info(f"ZIP extracted: {repo_path}")
        return repo_path
    
    # ─── FILE WALK ─────────────────────────────────────
    
    def get_source_files(
        self,
        repo_path: Path,
        extensions: Optional[set] = None
    ) -> List[Path]:
        """
        Walk the repository and find all source files.
        
        Args:
            repo_path: Path to cloned repository
            extensions: File extensions to include (default: SUPPORTED_EXTENSIONS)
        
        Returns:
            List of file paths sorted alphabetically
        """
        if extensions is None:
            extensions = SUPPORTED_EXTENSIONS
        
        source_files = []
        total_files = 0
        skipped_dirs = 0
        skipped_files = 0
        
        logger.info(f"Walking {repo_path}...")
        
        for filepath in repo_path.rglob('*'):
            total_files += 1
            
            # Skip directories
            if filepath.is_dir():
                if filepath.name in SKIP_DIRECTORIES:
                    skipped_dirs += 1
                    # Don't recurse into skipped dirs
                    # (we can't easily skip recursion with rglob, but we filter)
                continue
            
            # Skip unwanted files
            if filepath.name in SKIP_FILES:
                skipped_files += 1
                continue
            
            # Skip hidden files (starting with .)
            if filepath.name.startswith('.') and filepath.name != '.env.example':
                skipped_files += 1
                continue
            
            # Skip files in skipped directories
            parts = set(filepath.parts)
            if parts & SKIP_DIRECTORIES:
                continue
            
            # Check extension
            if filepath.suffix.lower() in extensions:
                source_files.append(filepath)
            else:
                skipped_files += 1
        
        # Sort for consistent output
        source_files = sorted(source_files)
        
        # Log summary
        extensions_found = set(f.suffix for f in source_files)
        
        logger.info(f"File walk complete:")
        logger.info(f"  Total entries: {total_files}")
        logger.info(f"  Source files: {len(source_files)}")
        logger.info(f"  Skipped dirs: {skipped_dirs}")
        logger.info(f"  Skipped files: {skipped_files}")
        logger.info(f"  Extensions found: {extensions_found}")
        
        return source_files
    
    def get_file_stats(self, files: List[Path]) -> dict:
        """
        Get statistics about a list of source files.
        
        Returns:
            {
                "total_files": 127,
                "total_lines": 15420,
                "total_chars": 523000,
                "by_extension": {".py": 45, ".js": 32, ...},
                "by_language": {"python": 45, "javascript": 32, ...}
            }
        """
        stats = {
            "total_files": len(files),
            "total_lines": 0,
            "total_chars": 0,
            "by_extension": {},
            "by_language": {},
        }
        
        # Language mapping
        ext_to_lang = {
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
        
        for filepath in files:
            ext = filepath.suffix.lower()
            
            # Count by extension
            stats["by_extension"][ext] = stats["by_extension"].get(ext, 0) + 1
            
            # Count by language
            lang = ext_to_lang.get(ext, ext.lstrip('.'))
            stats["by_language"][lang] = stats["by_language"].get(lang, 0) + 1
            
            # Count lines and chars
            try:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    stats["total_chars"] += len(content)
                    stats["total_lines"] += content.count('\n') + 1
            except Exception:
                pass  # Skip unreadable files
        
        return stats
    
    # ─── CLEANUP ───────────────────────────────────────
    
    def cleanup(self, session_id: str):
        """
        Remove a cloned repository from disk.
        
        Args:
            session_id: Session to clean up
        """
        repo_path = REPO_STORAGE_PATH / session_id
        
        if repo_path.exists():
            shutil.rmtree(repo_path)
            logger.info(f"Cleaned up {repo_path}")
        else:
            logger.debug(f"Nothing to clean up: {repo_path}")
    
    def cleanup_all(self):
        """Remove ALL cloned repositories."""
        if REPO_STORAGE_PATH.exists():
            shutil.rmtree(REPO_STORAGE_PATH)
            REPO_STORAGE_PATH.mkdir(parents=True, exist_ok=True)
            logger.info("Cleaned up all repositories")


# ============================================
# Convenience function
# ============================================

def process_repository(url: str, session_id: str) -> tuple:
    """
    Clone a repo and return all source files.
    One function call does it all.
    
    Returns:
        (repo_path, source_files, stats)
    """
    handler = RepoHandler()
    
    # Clone
    repo_path = handler.clone(url, session_id)
    
    # Find source files
    source_files = handler.get_source_files(repo_path)
    
    # Get stats
    stats = handler.get_file_stats(source_files)
    
    return repo_path, source_files, stats