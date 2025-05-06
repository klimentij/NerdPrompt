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
from .utils import estimate_tokens, get_relative_path, sanitize_filename

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
        console: Console
    ):
        self.config = config
        self.config_manager = config_manager
        self.output_builder = output_builder
        self.git_handler = git_handler
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
        effective_excludes_set = set(DEFAULT_EXCLUDES)
        effective_excludes_set.update(self.config_manager.load_project_state().default_excludes)
        effective_excludes_set.update(self.config.excludes)
        effective_excludes = sorted(list(effective_excludes_set))

        included_files = self._discover_files(
            source_paths=git_source_paths,
            gitignore_patterns=gitignore_patterns,
            effective_includes=self.config.includes,
            effective_excludes=effective_excludes
        )

        # 3. Assemble Prompt & Estimate Tokens
        merged_prompt, estimated_tokens = self._assemble_prompt(included_files, self.config.task_definition)

        # 3.5 Copy the prompt to clipboard immediately
        try:
            pyperclip.copy(merged_prompt)
            self.console.print(f"[green]Copied prompt to clipboard. You can paste it to other applications while waiting for the response.[/green]")
        except pyperclip.PyperclipException as e:
            self.console.print(f"[yellow]Warning: Could not copy prompt to clipboard. {e}[/yellow]")
        except Exception as e:
            self.console.print(f"[red]Error copying prompt to clipboard: {e}[/red]")

        # 4. Create Task Output Structure
        task_name_sanitized = sanitize_filename(self.config.task_name)
        
        task_dir_path = self.output_builder.create_task_output_structure(
            task_number_str=self.output_builder.get_next_folder_number()[1],
            task_name_sanitized=task_name_sanitized,
            original_task_name=self.config.task_name,
            task_definition=self.config.task_definition,
            included_local_files=included_files,
            processed_git_repos=processed_git_repos,
            estimated_tokens=estimated_tokens,
            llm_names=self.config.llms
        )

        # 5. Instantiate LLMApi now that task_dir_path is known
        llm_api = LLMApi(
            api_key=self.config.api_key,
            output_builder=self.output_builder,
            task_dir_path=task_dir_path,
            console=self.console
        )

        # 6. Process LLMs
        if not self.config.llms:
            self.console.print("[yellow]Warning: No LLMs specified in the configuration. Skipping LLM processing.[/yellow]")
        elif not self.config.task_definition.strip():
            self.console.print("[yellow]Warning: Task definition is empty. Skipping LLM processing.[/yellow]")
        else:
            if not self.config.skip_confirmation:
                self.console.print(Panel(f"Estimated tokens for prompt: ~{estimated_tokens}", title="Token Estimate", expand=False))
                if not self.config_manager.confirm_proceed(f"Proceed with sending to {len(self.config.llms)} LLM(s)?"):
                    self.console.print("[yellow]Operation cancelled by user.[/yellow]")
                    return

            total_cost = llm_api.process_llms(
                llm_names=self.config.llms,
                merged_prompt=merged_prompt,
                model_overrides=self.config.model_overrides
            )
            self.console.print(f"[green]LLM processing complete. Total estimated cost: ${total_cost:.6f}[/green]")

        # 7. Copy LLM Response to Clipboard (always, if there's a primary LLM response)
        if self.config.llms:  # Always copy to clipboard if there are LLMs
            primary_llm_name = self.config.llms[0]
            filename_sanitized = sanitize_filename(primary_llm_name) + ".md"
            response_file_path = task_dir_path / filename_sanitized
            if response_file_path.exists():
                try:
                    with open(response_file_path, 'r', encoding='utf-8') as f:
                        response_content = f.read()
                    metadata_marker = "\n\n---\n**Model:**"
                    if metadata_marker in response_content:
                        response_content = response_content.split(metadata_marker)[0]
                    
                    pyperclip.copy(response_content)
                    self.console.print(f"[green]Copied LLM response from {primary_llm_name} to clipboard.[/green]")
                except pyperclip.PyperclipException as e:
                    self.console.print(f"[yellow]Warning: Could not copy response to clipboard. {e}[/yellow]")
                except Exception as e:
                    self.console.print(f"[red]Error reading response file for clipboard: {e}[/red]")
            else:
                self.console.print(f"[yellow]Warning: Primary LLM response file not found for clipboard copy: {response_file_path}[/yellow]")

        self.console.print(f"[bold green]Nerd Prompt task '{self.config.task_name}' finished.[/bold green]")
        self.console.print(f"Output written to: [cyan]{task_dir_path.relative_to(self.project_root)}[/cyan]") 