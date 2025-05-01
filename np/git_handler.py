import subprocess
import shutil
from pathlib import Path
from typing import List, Optional, Tuple, Dict

from rich.console import Console

from .config import ConfigManager
from .output_builder import OutputBuilder
from .utils import parse_git_url, sanitize_filename

class GitHandler:
    """ Handles cloning and updating Git repositories into the np_output structure. """
    def __init__(
        self,
        project_root: Path,
        config_manager: ConfigManager,
        output_builder: OutputBuilder,
        console: Optional[Console] = None
    ):
        self.project_root = project_root
        self.output_dir = project_root / "np_output" # Ensure consistency
        self.config_manager = config_manager
        self.output_builder = output_builder
        self.console = console or Console()

    def _run_git_command(self, cmd: List[str], cwd: Optional[Path] = None) -> Tuple[int, str, str]:
        """ Runs a git command using subprocess, returns (returncode, stdout, stderr). """
        try:
            process = subprocess.run(
                cmd,
                cwd=cwd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace' # Handle potential decoding errors
            )
            return process.returncode, process.stdout.strip(), process.stderr.strip()
        except FileNotFoundError:
            self.console.print("[red]Error: 'git' command not found. Please ensure Git is installed and in your PATH.[/red]")
            return -1, "", "'git' command not found"
        except Exception as e:
            self.console.print(f"[red]Error running git command {' '.join(cmd)}: {e}[/red]")
            return -1, "", str(e)

    def process_git_repos(
        self,
        git_urls: List[str]
    ) -> List[Tuple[str, Optional[str], str, Path]]:
        """
        Processes a list of Git URLs. Clones or pulls them into numbered folders
        within np_output, updates the config map, and returns details of successful operations.

        Returns: List of tuples: (url, branch, commit_hash, local_path)
        """
        processed_repos = []
        git_repo_map = self.config_manager.load_project_state().git_repo_map

        for url in git_urls:
            base_url, branch = parse_git_url(url)
            repo_key = f"{base_url}#{branch or 'DEFAULT'}" # Use 'DEFAULT' for clarity if no branch specified
            repo_name = sanitize_filename(base_url.split('/')[-1].replace('.git', ''))
            target_path: Optional[Path] = None
            folder_name: Optional[str] = git_repo_map.get(repo_key)
            is_new_repo = False

            if folder_name:
                target_path = self.output_dir / folder_name
                self.console.print(f"Found existing mapping for [cyan]{base_url}[/] (Branch: {branch or 'default'}) -> [cyan]{target_path.relative_to(self.project_root)}[/cyan]")
            else:
                # Get next number and create folder name
                _num_int, num_str = self.output_builder.get_next_folder_number()
                folder_name = f"{num_str}-{repo_name}"
                target_path = self.output_dir / folder_name
                is_new_repo = True
                self.console.print(f"Assigning new folder for [cyan]{base_url}[/] (Branch: {branch or 'default'}) -> [cyan]{target_path.relative_to(self.project_root)}[/cyan]")


            if not target_path or not folder_name:
                self.console.print(f"[red]Error:[/red] Could not determine target path for Git URL: {url}")
                continue

            target_path.mkdir(parents=True, exist_ok=True)

            # 1. Attempt Pull (only if directory exists and seems like a git repo)
            pull_successful = False
            if not is_new_repo and (target_path / ".git").is_dir():
                self.console.print(f"[blue]ℹ️ Attempting pull for {repo_name} ({branch or 'default'}) into {target_path.name}...[/blue]")
                # Ensure correct branch is checked out first
                checkout_cmd = ['git', '-C', str(target_path), 'checkout', branch] if branch else ['git', '-C', str(target_path), 'checkout', 'HEAD'] # Or query default branch if needed
                ret_co, _, err_co = self._run_git_command(checkout_cmd)
                if ret_co != 0 and branch: # If checkout specific branch fails, maybe it needs fetching
                    self._run_git_command(['git', '-C', str(target_path), 'fetch', 'origin'])
                    ret_co, _, err_co = self._run_git_command(checkout_cmd) # Retry checkout

                if ret_co == 0:
                    pull_cmd = ['git', '-C', str(target_path), 'pull', 'origin', branch] if branch else ['git', '-C', str(target_path), 'pull']
                    ret_pull, _, err_pull = self._run_git_command(pull_cmd)
                    if ret_pull == 0:
                        pull_successful = True
                        self.console.print(f"[green]✅ Pull successful for {repo_name}.[/green]")
                    else:
                        self.console.print(f"[yellow]⚠️ Pull failed for {repo_name}: {err_pull}[/yellow]")
                else:
                     self.console.print(f"[yellow]⚠️ Checkout failed for {repo_name} (Branch: {branch or 'default'}): {err_co}[/yellow]")


            # 2. Attempt Clone (if pull failed or it's a new repo)
            clone_successful = False
            if not pull_successful:
                if not is_new_repo: # Only warn if pull failed on existing dir
                    self.console.print(f"[yellow]⚠️ Pull failed or repo invalid. Attempting fresh clone...[/yellow]")
                    try:
                        if target_path.exists():
                             shutil.rmtree(target_path) # Clean up before clone
                        target_path.mkdir(parents=True, exist_ok=True) # Recreate dir
                    except Exception as e:
                         self.console.print(f"[red]Error cleaning directory {target_path} before clone: {e}[/red]")
                         continue # Skip this repo

                self.console.print(f"[blue]ℹ️ Cloning {repo_name} ({branch or 'default'}) into {target_path.name}...[/blue]")
                clone_cmd = ['git', 'clone', '--depth', '1']
                if branch:
                    clone_cmd.extend(['-b', branch])
                clone_cmd.extend([base_url, str(target_path)])

                ret_clone, _, err_clone = self._run_git_command(clone_cmd)
                if ret_clone == 0:
                    clone_successful = True
                    self.console.print(f"[green]✅ Clone successful for {repo_name}.[/green]")
                else:
                    self.console.print(f"[red]❌ Failed to clone {repo_name}: {err_clone}[/red]")
                    # Optionally remove the failed clone attempt directory
                    # shutil.rmtree(target_path, ignore_errors=True)
                    continue # Skip this repo

            # 3. Get Commit Hash and Update Map/Result
            if pull_successful or clone_successful:
                hash_cmd = ['git', '-C', str(target_path), 'rev-parse', 'HEAD']
                ret_hash, commit_hash, err_hash = self._run_git_command(hash_cmd)

                if ret_hash == 0 and commit_hash:
                    processed_repos.append((base_url, branch, commit_hash, target_path))
                    # Update map in config only if it was a *new* repo assignment
                    if is_new_repo:
                        self.config_manager.update_git_repo_map(repo_key, folder_name)
                else:
                    self.console.print(f"[red]Error:[/red] Could not get commit hash for {repo_name}: {err_hash}")

        return processed_repos 