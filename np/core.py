import fnmatch
import os
import sys
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional, Set

import pyperclip # type: ignore
from rich.console import Console
from rich.panel import Panel

from .config import RunConfig, ConfigManager, ProjectState, DEFAULT_EXCLUDES
from .git_handler import GitHandler
from .output_builder import OutputBuilder
from .llm_api import LLMApi
from .utils import estimate_tokens, get_relative_path

def pattern_matches_any(path: str, patterns: List[str]) -> bool:
    """
    Check if a given path matches any of the provided glob patterns.
    """
    path = path.replace("\\", "/")  # Normalize path separators for matching
    
    for pattern in patterns:
        # Handle directory patterns (ending with /)
        if pattern.endswith('/'):
            if path.startswith(pattern) or path == pattern[:-1]:
                return True
        # Standard glob matching
        elif fnmatch.fnmatch(path, pattern):
            return True
    return False

class CoreProcessor:
    """ Orchestrates the main processing steps after configuration. """
    def __init__(
        self,
        config: RunConfig,
        config_manager: ConfigManager,
        output_builder: OutputBuilder,
        git_handler: GitHandler,
        llm_api: LLMApi,
        console: Console
    ):
        self.config = config
        self.config_manager = config_manager
        self.output_builder = output_builder
        self.git_handler = git_handler
        self.llm_api = llm_api
        self.console = console
        self.project_root = config.project_root

    def _discover_files(
        self,
        source_paths: List[Path],
        gitignore_patterns: List[str],
        effective_includes: List[str],
        effective_excludes: List[str]
    ) -> List[Path]:
        """ Walks source paths, applies filters, returns list of files to include. """
        self.console.print("[blue]Discovering and filtering files...[/blue]")
        included_files: Set[Path] = set()
        absolute_source_paths = [p.resolve() for p in source_paths]

        all_files_count = 0
        excluded_by_gitignore = 0
        excluded_by_config = 0
        included_count = 0

        # Add project root implicitly if './' is in includes or includes is empty but not explicitly excluded
        processed_roots = set()

        effective_search_paths = []
        specific_files_in_includes = set()

        # Separate specific files/dirs from Git paths already processed
        local_includes = [inc for inc in effective_includes if not inc.startswith(('http://', 'https://', 'git@'))]
        if not local_includes or "./" in local_includes:
             effective_search_paths.append(self.project_root)
        for pattern in local_includes:
             if pattern == "./": continue
             # Expand globs relative to project root
             try:
                 for path in self.project_root.glob(pattern):
                     if path.is_file():
                         specific_files_in_includes.add(path.resolve())
                         effective_search_paths.append(path.resolve()) # Check specific file
                     elif path.is_dir():
                         effective_search_paths.append(path.resolve())
                     else: # Broken symlink perhaps
                          pass
             except Exception as e:
                 self.console.print(f"[yellow]Warning:[/yellow] Could not process include pattern '{pattern}': {e}")


        # Add Git paths from handler
        for git_path in source_paths:
             effective_search_paths.append(git_path.resolve())

        # Deduplicate search paths
        unique_search_paths = sorted(list(set(effective_search_paths)), key=lambda p: len(p.parts))


        for search_path in unique_search_paths:
             # Check if path is already covered by a parent path to avoid redundant walks
             is_covered = False
             for processed in processed_roots:
                 try:
                     if search_path.is_relative_to(processed):
                         is_covered = True
                         break
                 except ValueError:
                     pass
             if is_covered: continue

             if search_path.is_file() and search_path not in included_files:
                 all_files_count += 1
                 file_rel_path = get_relative_path(search_path, self.project_root)
                 path_str = str(file_rel_path).replace("\\", "/") # Normalize slashes for matching

                 # Apply filters
                 is_gitignored = any(fnmatch.fnmatch(path_str, pat) or fnmatch.fnmatch(search_path.name, pat) for pat in gitignore_patterns)
                 if is_gitignored:
                     excluded_by_gitignore += 1
                     continue
                 is_excluded = any(fnmatch.fnmatch(path_str, pat) or fnmatch.fnmatch(search_path.name, pat) for pat in effective_excludes)
                 if is_excluded:
                     excluded_by_config += 1
                     continue

                 included_files.add(search_path)
                 included_count += 1


             elif search_path.is_dir():
                 processed_roots.add(search_path)
                 for item in search_path.rglob('*'):
                     if item.is_file():
                         all_files_count += 1
                         file_rel_path = get_relative_path(item, self.project_root)
                         path_str = str(file_rel_path).replace("\\", "/") # Normalize slashes for matching

                         # Apply filters
                         is_gitignored = any(fnmatch.fnmatch(path_str, pat) or fnmatch.fnmatch(item.name, pat) for pat in gitignore_patterns)
                         if is_gitignored:
                              excluded_by_gitignore += 1
                              continue
                         is_excluded = any(fnmatch.fnmatch(path_str, pat) or fnmatch.fnmatch(item.name, pat) for pat in effective_excludes)
                         if is_excluded:
                              excluded_by_config += 1
                              continue

                         # Add if it matches *any* include pattern (or if includes is just './')
                         # Note: This logic might need refinement depending on how specific includes should interact
                         # For simplicity now: if it passed excludes, include it.
                         included_files.add(item)
                         included_count += 1

        self.console.print(f"  Total files scanned: {all_files_count}")
        self.console.print(f"  Excluded by .gitignore: {excluded_by_gitignore}")
        self.console.print(f"  Excluded by config: {excluded_by_config}")
        self.console.print(f"  [bold green]Files included: {len(included_files)}[/bold green]")

        return sorted(list(included_files))

    def _assemble_prompt(self, included_files: List[Path], task_definition: str) -> Tuple[str, int]:
        """ Reads files, assembles the prompt string, returns (prompt, estimated_tokens). """
        self.console.print("[blue]Assembling prompt content...[/blue]")
        prompt_parts = []
        total_chars = 0

        # Add file contents
        for file_path in included_files:
            relative_path = get_relative_path(file_path, self.project_root)
            path_str = str(relative_path).replace('\\', '/')
            header = f"## Source: {path_str}\n\n"
            try:
                with open(file_path, 'r', encoding='utf-8', errors='replace') as infile:
                    content = infile.read()
                prompt_parts.append(header)
                prompt_parts.append(content)
                prompt_parts.append("\n\n---\n\n")
                total_chars += len(header) + len(content) + len("\n\n---\n\n")
            except Exception as e:
                error_msg = f"Error reading {relative_path}: {e}"
                prompt_parts.append(header)
                prompt_parts.append(f"```\n--- ERROR READING FILE ---\n{error_msg}\n```")
                prompt_parts.append("\n\n---\n\n")
                self.console.print(f"[red]Error:[/red] Failed to read file '{relative_path}': {e}")
                total_chars += len(header) + len(error_msg) + len("\n\n---\n\n") + 10 # Account for formatting

        # Add task definition sections
        task_header = """
================================================================================

# Main Instructions - Current Task

This section contains the primary instructions and current task to follow.

++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++

"""
        task_footer = """

--------------------------------------------------------------------------------

## Output Format Instructions

*   Your entire response **must** be formatted as valid Markdown.
*   Use standard Markdown syntax for headings, lists, code blocks, bolding, etc.
*   Ensure all links are embedded directly using Markdown syntax (e.g., `[text](URL)`) and are clickable. Do **not** use reference-style links (e.g., `[1]`, `[2]`) or footnotes for links.
*   Structure your response logically. Use code blocks with language identifiers (e.g., ```python ... ```) where appropriate.
"""
        prompt_parts.append(task_header)
        prompt_parts.append(task_definition)
        prompt_parts.append(task_footer)
        total_chars += len(task_header) + len(task_definition) + len(task_footer)

        final_prompt = "".join(prompt_parts)
        estimated_toks = estimate_tokens(final_prompt) # Estimate based on final combined content

        self.console.print(f"Prompt assembled. Total characters: {total_chars}, Estimated tokens: ~{estimated_toks}")
        return final_prompt, estimated_toks

    def run(self) -> None:
        """ Executes the core processing workflow. """
        self.console.print(Panel(f"Starting Processing: [bold cyan]{self.config.task_name}[/bold cyan]", title="Nerd Prompt", expand=False))

        # 1. Process Git Repositories
        git_urls_to_process = [inc for inc in self.config.includes if inc.startswith(('http://', 'https://', 'git@'))]
        processed_git_repos = self.git_handler.process_git_repos(git_urls_to_process)
        git_source_paths = [path for _, _, _, path in processed_git_repos]

        # 2. Discover Files
        gitignore_patterns = self.config_manager.load_gitignore_patterns()
        # Combine default excludes, config excludes, and CLI excludes
        # Make excludes unique
        effective_excludes_set = set(DEFAULT_EXCLUDES)
        effective_excludes_set.update(self.config_manager.load_project_state().default_excludes) # From config file
        effective_excludes_set.update(self.config.excludes) # From CLI/interactive args
        effective_excludes = sorted(list(effective_excludes_set))

        included_files = self._discover_files(
            source_paths=git_source_paths, # Only pass git paths initially, discovery handles root/other includes
            gitignore_patterns=gitignore_patterns,
            effective_includes=self.config.includes,
            effective_excludes=effective_excludes
        )

        # 3. Assemble Prompt & Estimate Tokens
        merged_prompt, estimated_tokens = self._assemble_prompt(included_files, self.config.task_definition)

        # 4. Copy to Clipboard
        try:
            pyperclip.copy(merged_prompt)
            self.console.print(f"[bold green]✅ Merged prompt (~{estimated_tokens} tokens) copied to clipboard![/bold green]")
        except Exception as e:
            self.console.print(f"[yellow]Warning:[/yellow] Could not copy prompt to clipboard: {e}")
            self.console.print("You may need to install 'xclip' or 'xsel' on Linux, or 'pbcopy' might be missing.")

        # 5. Create Output Structure
        task_num_int, task_num_str = self.output_builder.get_next_folder_number() # Get number for the *task* folder
        task_dir_path = self.output_builder.create_task_output_structure(
            task_number_str=task_num_str,
            task_name_sanitized=self.config.task_name, # Assumes name is already sanitized
            original_task_name=self.config.task_name, # Need original name here? Let's assume config holds sanitized
            task_definition=self.config.task_definition,
            included_local_files=included_files, # Pass discovered files
            processed_git_repos=processed_git_repos, # Pass processed git details
            estimated_tokens=estimated_tokens,
            llm_names=self.config.llms
        )

        # Update the LLMApi instance with the correct task directory path
        self.llm_api.task_dir_path = task_dir_path

        # 6. Process LLMs (if any)
        if self.config.llms:
            total_cost = self.llm_api.process_llms(
                llm_names=self.config.llms,
                merged_prompt=merged_prompt,
                model_overrides=self.config.model_overrides
            )
            if total_cost > 0:
                 self.console.print(f"[blue]Total OpenRouter Cost: ${total_cost:.6f}[/blue]")
            else:
                 # Check if any OR models *failed* vs just having manual models
                 or_models = [m for m in self.config.llms if self.llm_api._is_openrouter_model(m)]
                 if or_models:
                      self.console.print("[yellow]Note: No cost reported from OpenRouter (check for errors above).[/yellow]")

        else:
            self.console.print("[yellow]No LLMs specified. Skipping LLM processing.[/yellow]")

        self.console.print(Panel(f"Processing Complete for: [bold cyan]{self.config.task_name}[/bold cyan]", title="Nerd Prompt", expand=False)) 