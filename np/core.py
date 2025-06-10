import fnmatch
from pathlib import Path
from typing import Dict, List, Tuple

import pyperclip  # type: ignore
from rich.console import Console
from rich.panel import Panel

from .config import DEFAULT_EXCLUDES, ConfigManager, RunConfig
from .git_handler import GitHandler
from .llm_api import LLMApi
from .output_builder import OutputBuilder
from .utils import estimate_tokens, get_relative_path, sanitize_filename


def pattern_matches_any(path: str, patterns: List[str]) -> bool:
    """
    Check if a given path matches any of the provided glob patterns.
    """
    path = path.replace("\\", "/")  # Normalize path separators for matching

    for pattern in patterns:
        # Special handling for .git/ pattern specifically
        if pattern == ".git/":
            # Check for .git/ at any path level
            if "/.git/" in path or path.startswith(".git/") or path == ".git":
                return True
        # Handle other directory patterns (ending with /)
        elif pattern.endswith('/'):
            pattern_no_slash = pattern[:-1]
            # For regular directory patterns, only match from the start or exact match
            if path == pattern_no_slash or path.startswith(pattern):
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
                 is_excluded = pattern_matches_any(path_str, effective_excludes)
                 if not is_excluded:
                     # Still check filename directly as a fallback
                     is_excluded = any(fnmatch.fnmatch(search_path.name, pat) for pat in effective_excludes)

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

                         # Check if this file is in a .git directory by checking its full path
                         is_excluded = pattern_matches_any(path_str, effective_excludes)
                         if not is_excluded:
                             # Still check filename directly as a fallback for simple patterns
                             is_excluded = any(fnmatch.fnmatch(item.name, pat) for pat in effective_excludes)

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

    def _assemble_prompt(self, included_files: List[Path], task_definition: str) -> Tuple[str, int, Dict[str, int]]:
        """Reads files, assembles the prompt string and returns prompt, token estimate, and token usage per folder."""
        self.console.print("[blue]Assembling prompt content...[/blue]")
        prompt_parts = []
        total_chars = 0
        folder_tokens: Dict[str, int] = {}

        # Add file contents
        for file_path in included_files:
            relative_path = get_relative_path(file_path, self.project_root)
            path_str = str(relative_path).replace('\\', '/')
            header = f"## Source: {path_str}\n\n"
            try:
                with file_path.open(encoding="utf-8", errors="replace") as infile:
                    content = infile.read()
                prompt_parts.append(header)
                prompt_parts.append(content)
                prompt_parts.append("\n\n---\n\n")
                total_chars += len(header) + len(content) + len("\n\n---\n\n")
                tokens_this_file = estimate_tokens(content)
                folder_tokens[str(relative_path.parent)] = folder_tokens.get(str(relative_path.parent), 0) + tokens_this_file
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
        return final_prompt, estimated_toks, folder_tokens

    def _preview_context(self, estimated_tokens: int, folder_tokens: Dict[str, int]) -> str:
        """Display token summary and ask user how to proceed.

        Returns one of "proceed", "update", or "cancel"."""
        try:
            import questionary
            from rich.table import Table
        except Exception:
            self.console.print("[red]Interactive prompts unavailable.[/red]")
            return "proceed"

        custom_style = questionary.Style([
            ('qmark', 'fg:#673ab7 bold'),
            ('question', 'bold'),
            ('answer', 'fg:#ff5722 bold'),
            ('pointer', 'fg:#673ab7 bold'),
            ('highlighted', 'fg:#673ab7 bold'),
            ('selected', 'fg:#cc5454'),
            ('separator', 'fg:#cc5454'),
            ('instruction', ''),
            ('text', ''),
            ('disabled', 'fg:#858585 italic')
        ])

        self.console.print(Panel(f"Estimated tokens for prompt: ~{estimated_tokens}", title="Token Estimate", expand=False))

        while True:
            action = questionary.select(
                "Continue with these context files?",
                choices=[
                    questionary.Choice("Proceed", "proceed"),
                    questionary.Choice("More Info", "more"),
                    questionary.Choice("Update Context", "update"),
                    questionary.Choice("Cancel", "cancel")
                ],
                style=custom_style
            ).ask()

            if action == "more":
                table = Table(title="Top Token Folders", show_header=True, header_style="bold magenta")
                table.add_column("Folder", style="red")
                table.add_column("~Tokens", justify="right")
                for folder, toks in sorted(folder_tokens.items(), key=lambda x: x[1], reverse=True)[:5]:
                    table.add_row(folder or ".", str(toks))
                self.console.print(table)
                continue

            return action or "cancel"

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

        while True:
            # 3. Assemble Prompt & Estimate Tokens
            merged_prompt, estimated_tokens, folder_tokens = self._assemble_prompt(included_files, self.config.task_definition)

            if not self.config.skip_confirmation:
                action = self._preview_context(estimated_tokens, folder_tokens)
                if action == "update":
                    included_files = self._discover_files(
                        source_paths=git_source_paths,
                        gitignore_patterns=gitignore_patterns,
                        effective_includes=self.config.includes,
                        effective_excludes=effective_excludes
                    )
                    continue
                elif action == "cancel":
                    self.console.print("[yellow]Operation cancelled by user.[/yellow]")
                    return
            break

        # 3.5 Copy prompt to clipboard and save to file
        output_base_dir = self.output_builder.output_dir # Correct attribute
        last_prompt_file = output_base_dir / "last_prompt.md"
        copied = False
        saved = False
        try:
            pyperclip.copy(merged_prompt)
            copied = True
        except pyperclip.PyperclipException as e:
            self.console.print(f"[yellow]Warning: Could not copy prompt to clipboard. {e}[/yellow]")
        except Exception as e:
            self.console.print(f"[red]Error copying prompt to clipboard: {e}[/red]")

        try:
            output_base_dir.mkdir(parents=True, exist_ok=True) # Ensure np_output exists
            with last_prompt_file.open('w', encoding='utf-8') as f:
                f.write(merged_prompt)
            saved = True
        except Exception as e:
            self.console.print(f"[red]Error saving prompt to {last_prompt_file}: {e}[/red]")

        if copied and saved:
             self.console.print(f"[green]Copied prompt to clipboard and saved to [cyan]{last_prompt_file.relative_to(self.project_root)}[/cyan].[/green]")
        elif copied:
             self.console.print("[green]Copied prompt to clipboard.[/green] [yellow]Could not save to file.[/yellow]")
        elif saved:
             self.console.print(f"[green]Saved prompt to [cyan]{last_prompt_file.relative_to(self.project_root)}[/cyan].[/green] [yellow]Could not copy to clipboard.[/yellow]")


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
                if not self.config_manager.confirm_proceed(f"Proceed with sending to {len(self.config.llms)} LLM(s)?"):
                    self.console.print("[yellow]Operation cancelled by user.[/yellow]")
                    return
            else:
                self.console.print(Panel(f"Estimated tokens for prompt: ~{estimated_tokens}", title="Token Estimate", expand=False))

            total_cost = llm_api.process_llms(
                llm_names=self.config.llms,
                merged_prompt=merged_prompt,
                model_overrides=self.config.model_overrides
            )
            self.console.print(f"[green]LLM processing complete. Total estimated cost: ${total_cost:.6f}[/green]")

        self.console.print(f"[bold green]Nerd Prompt task '{self.config.task_name}' finished.[/bold green]")
        self.console.print(f"Output written to: [cyan]{task_dir_path.relative_to(self.project_root)}[/cyan]")

