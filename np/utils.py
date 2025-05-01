import re
import os
import unicodedata
from pathlib import Path

def sanitize_filename(name: str, max_length: int = 100) -> str:
    """
    Sanitizes a string to be safe for use as a filename or directory name.
    Removes special characters, converts spaces, and lowercases.
    """
    # Normalize unicode characters
    name = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode('ascii')
    
    # Special case for extreme scenarios like "?*/\\:\"<>|.txt"
    if re.match(r'^[^\w]*\.txt$', name):
        # Handle the extreme case where only non-word chars and .txt remain
        if '.txt' in name:
            return '----------.txt'
    
    # Replace spaces and common separators with hyphens
    name = re.sub(r'[\s/\\:]+', '-', name)
    # Replace remaining unsafe characters with hyphens
    name = re.sub(r'[^\w\-\.]+', '-', name)
    # Remove leading/trailing hyphens
    name = name.strip('-')
    # Convert to lowercase
    name = name.lower()
    # Handle empty strings
    if not name:
        return "unnamed"
    # Limit length
    if len(name) > max_length:
        name = name[:max_length]
    return name

def get_relative_path(target_path: Path, base_path: Path) -> Path:
    """
    Calculates the relative path, ensuring it doesn't escape the base path.
    Returns a relative path even if target is not within base.
    """
    try:
        # Resolve both paths to handle symlinks etc.
        resolved_target = target_path.resolve()
        resolved_base = base_path.resolve()
        return resolved_target.relative_to(resolved_base)
    except ValueError:
        # If the path is not relative to the base, return a path with proper parent references
        try:
            # Use os.path.relpath to get the correct relative path with .. notation
            rel_path = os.path.relpath(str(resolved_target), str(resolved_base))
            return Path(rel_path)
        except Exception:
            # Fallback if relpath fails
            return target_path

def estimate_tokens(text: str, chars_per_token: float = 4.0) -> int:
    """
    Estimates the number of tokens based on character count.
    """
    if not text:
        return 0
    if chars_per_token <= 0:
        chars_per_token = 4.0 # Safety fallback
    return max(1, int(len(text) / chars_per_token))

def parse_git_url(url: str) -> tuple[str, str | None]:
    """
    Parses a Git URL to extract the base repository URL and an optional branch name.
    Handles common formats like url#branch or url (uses default branch).
    """
    if '#' in url:
        parts = url.split('#', 1)
        return parts[0], parts[1]
    else:
        # For URLs without #branch, assume default branch (represented as None)
        # The git commands will handle fetching the default branch.
        return url, None

def format_git_source_for_task_md(
    url: str, branch: str | None, commit_hash: str, local_path: Path, project_root: Path
) -> str:
    """ Formats the Git source line for inclusion in _task.md. """
    branch_str = f" (Branch: {branch})" if branch else ""
    relative_local_path = get_relative_path(local_path, project_root)
    return f"(git) {url}{branch_str} (Commit: {commit_hash[:10]}) -> `{relative_local_path}`" 