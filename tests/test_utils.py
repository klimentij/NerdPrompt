"""Tests for the utility functions."""

import pytest
from pathlib import Path
import os

from np.utils import estimate_tokens, get_relative_path, sanitize_filename


def test_estimate_tokens():
    """Test token estimation logic."""
    # Empty string
    assert estimate_tokens("") == 0
    
    # Short text
    assert estimate_tokens("Hello, world!") > 0
    
    # Check char-to-token ratio (approximate)
    text = "This is a test text with approximately 4 characters per token."
    tokens = estimate_tokens(text)
    assert tokens >= len(text) / 5  # Lower bound (more characters per token)
    assert tokens <= len(text) / 3  # Upper bound (fewer characters per token)
    
    # Check large text
    large_text = "word " * 1000
    tokens = estimate_tokens(large_text)
    assert tokens > 500  # Should have at least 500 tokens


def test_get_relative_path():
    """Test relative path calculation."""
    base_path = Path("/home/user/project")
    
    # Test file directly in base path
    file_path = Path("/home/user/project/file.txt")
    rel_path = get_relative_path(file_path, base_path)
    assert str(rel_path) == "file.txt"
    
    # Test file in subdirectory
    file_path = Path("/home/user/project/src/module/file.py")
    rel_path = get_relative_path(file_path, base_path)
    assert str(rel_path) == os.path.join("src", "module", "file.py")
    
    # Test file outside base path
    file_path = Path("/home/user/other/file.txt")
    rel_path = get_relative_path(file_path, base_path)
    assert str(rel_path) == os.path.join("..", "other", "file.txt")
    
    # Test with relative paths
    base_path = Path("project")
    file_path = Path("project/src/file.py")
    rel_path = get_relative_path(file_path, base_path)
    assert str(rel_path) == os.path.join("src", "file.py")


def test_sanitize_filename():
    """Test filename sanitization."""
    # Normal filename
    assert sanitize_filename("test.txt") == "test.txt"
    
    # Filename with spaces
    assert sanitize_filename("test file.txt") == "test-file.txt"
    
    # Filename with special characters
    assert sanitize_filename("test/file:name?.txt") == "test-file-name-.txt"
    
    # Filename with unicode
    assert sanitize_filename("téśt.txt") == "test.txt"
    
    # Extreme case
    assert sanitize_filename("?*/\\:\"<>|.txt") == "----------.txt"
    
    # Maximum length
    long_name = "a" * 200 + ".txt"
    assert len(sanitize_filename(long_name)) <= 100 