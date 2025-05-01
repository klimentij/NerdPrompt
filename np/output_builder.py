import os
import re
import shutil
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Optional, Tuple, Dict, Set

from rich.console import Console

from .utils import sanitize_filename, format_git_source_for_task_md

OUTPUT_DIR_NAME = "np_output"
TASK_FILE_NAME = "_task.md"
FOLDER_NAME_PATTERN = re.compile(r"^(\d+)-(.+)$") # Matches NNN-name


class OutputBuilder:
    """ Handles creation of output directories and files. """
    def __init__(self, project_root: Path, console: Optional[Console] = None):
        self.project_root = project_root
        self.output_dir = self.project_root / OUTPUT_DIR_NAME
        self.console = console or Console()
        self.output_dir.mkdir(exist_ok=True)

    def _scan_and_renumber_folders(self) -> Tuple[int, int]:
        """
        Scans the output directory, finds the max prefix number, determines padding,
        renames non-conforming folders, and returns the next number and padding.
        """
        max_num = 0
        existing_folders: Dict[int, Path] = {}
        non_conforming: List[Path] = []

        if self.output_dir.exists() and self.output_dir.is_dir():
            for item in self.output_dir.iterdir():
                if item.is_dir():
                    match = FOLDER_NAME_PATTERN.match(item.name)
                    if match:
                        num = int(match.group(1))
                        max_num = max(max_num, num)
                        existing_folders[num] = item
                    else:
                        non_conforming.append(item)

        # Determine padding (at least 2 digits, increases to 3 if max_num >= 99)
        padding = 3 if max_num >= 99 else 2
        next_num = max_num + 1

        # Rename non-conforming folders first
        non_conforming.sort(key=lambda p: p.stat().st_mtime) # Sort by creation/mod time
        renamed_count = 0
        for folder_path in non_conforming:
            while next_num in existing_folders: # Skip numbers already taken by conforming folders
                 next_num += 1
            new_name = f"{next_num:0{padding}d}-{folder_path.name}"
            new_path = self.output_dir / new_name
            try:
                folder_path.rename(new_path)
                self.console.print(f"[yellow]Renamed:[/yellow] '{folder_path.name}' -> '{new_name}' for consistent numbering.")
                existing_folders[next_num] = new_path # Add to map
                renamed_count += 1
                next_num += 1
            except OSError as e:
                self.console.print(f"[red]Error:[/red] Failed to rename '{folder_path.name}': {e}")

        # Check and rename existing conforming folders if padding needs adjustment
        padding_adjusted_count = 0
        current_max_after_rename = max(existing_folders.keys()) if existing_folders else 0
        required_padding = 3 if current_max_after_rename >= 99 else 2

        folders_to_repad: List[Tuple[int, Path]] = []
        for num, folder_path in existing_folders.items():
             match = FOLDER_NAME_PATTERN.match(folder_path.name)
             if match and len(match.group(1)) != required_padding:
                  folders_to_repad.append((num, folder_path))

        folders_to_repad.sort() # Repad in numerical order
        for num, folder_path in folders_to_repad:
             match = FOLDER_NAME_PATTERN.match(folder_path.name)
             if match:
                  base_name = match.group(2)
                  new_name = f"{num:0{required_padding}d}-{base_name}"
                  new_path = self.output_dir / new_name
                  if new_path != folder_path:
                       try:
                            folder_path.rename(new_path)
                            self.console.print(f"[yellow]Adjusted Padding:[/yellow] '{folder_path.name}' -> '{new_name}'")
                            padding_adjusted_count += 1
                       except OSError as e:
                            self.console.print(f"[red]Error:[/red] Failed to adjust padding for '{folder_path.name}': {e}")

        # Recalculate next_num after all renames/repadding
        final_max = 0
        if self.output_dir.exists() and self.output_dir.is_dir():
             for item in self.output_dir.iterdir():
                 if item.is_dir():
                      match = FOLDER_NAME_PATTERN.match(item.name)
                      if match:
                           final_max = max(final_max, int(match.group(1)))

        final_padding = 3 if final_max >= 99 else 2
        final_next_num = final_max + 1

        if renamed_count > 0 or padding_adjusted_count > 0:
             self.console.print(f"[blue]Folder numbering standardized. Next available number is {final_next_num}.[/blue]")

        return final_next_num, final_padding


    def get_next_folder_number(self) -> Tuple[int, str]:
        """
        Determines the next available sequential number and its padded string representation.
        Handles renaming of non-conforming folders.
        Returns (next_number_int, next_number_padded_str)
        """
        next_num, padding = self._scan_and_renumber_folders()
        return next_num, f"{next_num:0{padding}d}"

    def create_task_output_structure(
        self,
        task_number_str: str,
        task_name_sanitized: str,
        original_task_name: str,
        task_definition: str,
        included_local_files: List[Path],
        processed_git_repos: List[Tuple[str, str | None, str, Path]], # url, branch, commit, local_path
        estimated_tokens: int,
        llm_names: List[str],
    ) -> Path:
        """
        Creates the numbered task directory, generates _task.md, and empty response files.
        Returns the path to the created task directory.
        """
        task_folder_name = f"{task_number_str}-{task_name_sanitized}"
        task_dir_path = self.output_dir / task_folder_name
        task_dir_path.mkdir(exist_ok=True)

        # --- Generate _task.md ---
        task_md_path = task_dir_path / TASK_FILE_NAME
        now_utc = datetime.now(timezone.utc).isoformat(timespec='seconds')

        context_lines = []
        # Add local files/dirs relative to project root
        for file_path in sorted(included_local_files):
            relative_path = file_path.relative_to(self.project_root) if file_path.is_relative_to(self.project_root) else file_path
            context_lines.append(f"*   `{relative_path}`")

        # Add Git repos
        for url, branch, commit_hash, local_path in sorted(processed_git_repos, key=lambda x: x[3].name):
             context_lines.append(f"*   {format_git_source_for_task_md(url, branch, commit_hash, local_path, self.project_root)}")

        context_section = "\n".join(context_lines) if context_lines else "*   (No specific files listed - likely included './')"

        task_md_content = f"""
# Task: {original_task_name}

{task_definition}

---

## Included Context Sources

{context_section}

---

## Metadata

*   **Created:** {now_utc}
*   **Estimated Tokens:** ~{estimated_tokens}
*   **LLMs Targeted:** {', '.join(llm_names) if llm_names else 'None'}
"""
        try:
            with open(task_md_path, "w", encoding="utf-8") as f:
                f.write(task_md_content.strip() + "\n")
        except Exception as e:
            self.console.print(f"[red]Error:[/red] Failed to write {task_md_path}: {e}")

        # --- Create empty LLM response files ---
        created_files: Set[Path] = set()
        for llm_name in llm_names:
            filename_sanitized = sanitize_filename(llm_name) + ".md"
            response_file_path = task_dir_path / filename_sanitized

            # Avoid accidental overwrites if sanitization leads to collision (unlikely but possible)
            counter = 1
            original_path = response_file_path
            while response_file_path in created_files:
                filename_sanitized = f"{sanitize_filename(llm_name)}-{counter}.md"
                response_file_path = task_dir_path / filename_sanitized
                counter += 1

            if not response_file_path.exists():
                 try:
                      response_file_path.touch()
                      created_files.add(response_file_path)
                 except Exception as e:
                      self.console.print(f"[red]Error:[/red] Failed to create empty file {response_file_path}: {e}")

        self.console.print(f"Created task output structure in: [cyan]{task_dir_path.relative_to(self.project_root)}[/cyan]")
        return task_dir_path

    def write_llm_response(self, task_dir_path: Path, llm_name: str, content: str) -> None:
        """ Writes content (response or error) to the specific LLM file. """
        filename_sanitized = sanitize_filename(llm_name) + ".md"
        response_file_path = task_dir_path / filename_sanitized
        # Assume file was created earlier, overwrite it
        try:
            with open(response_file_path, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception as e:
            self.console.print(f"[red]Error:[/red] Failed to write response to {response_file_path}: {e}") 