import os
import toml
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Set
from dataclasses import dataclass, field

import appdirs
from dotenv import load_dotenv
from rich.console import Console

# --- Constants ---
PROJECT_CONFIG_FILENAME = ".npconfig.toml"
GLOBAL_CONFIG_DIR_NAME = "nerd-prompt"
GLOBAL_CONFIG_FILENAME = "settings.toml"
API_KEY_ENV_VAR = "OPENROUTER_API_KEY"
DEFAULT_CHARS_PER_TOKEN = 4.0

DEFAULT_EXCLUDES = [
    ".git/",
    "__pycache__/",
    "node_modules/",
    ".vscode/",
    "*.log",
    PROJECT_CONFIG_FILENAME,
    ".np_git_cache/", # Excluded for file discovery, not the repo itself
    "np_output/", # Exclude the output dir from context gathering
    # Common image formats
    "*.png", "*.jpg", "*.jpeg", "*.gif", "*.svg", "*.webp", "*.ico", "*.bmp",
    # Other common artifacts
    ".DS_Store",
    "*.pyc",
    "*.pyo",
    "*~$*", # Temp Word files etc.
    ".env", # Often contains secrets
    "venv/",
    ".venv/",
    "dist/",
    "build/",
    "*.egg-info/",
]

# --- Dataclasses for Configuration ---

@dataclass
class RunConfig:
    """ Holds the final configuration for a single run. """
    includes: List[str] = field(default_factory=lambda: ["./"])
    excludes: List[str] = field(default_factory=list) # Will be combined with defaults + gitignore
    llms: List[str] = field(default_factory=list)
    task_name: str = ""
    task_definition: str = ""
    model_overrides: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    skip_confirmation: bool = False
    project_root: Path = field(default_factory=Path.cwd)
    api_key: Optional[str] = None # Loaded separately


@dataclass
class ProjectState:
    """ Represents the persistent state stored in .npconfig.toml """
    # User Preferences / Defaults for next run
    default_includes: List[str] = field(default_factory=lambda: ["./"])
    default_excludes: List[str] = field(default_factory=lambda: list(DEFAULT_EXCLUDES))
    default_llms: List[str] = field(default_factory=list)
    default_model_overrides: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    # Internal State
    git_repo_map: Dict[str, str] = field(default_factory=dict) # "url#branch": "NNN-repo-name"

# --- Configuration Management Class ---

class ConfigManager:
    """ Handles loading, saving, and managing project and global configurations. """
    def __init__(self, project_root: Path = Path.cwd(), console: Optional[Console] = None):
        self.project_root = project_root
        self.project_config_path = self.project_root / PROJECT_CONFIG_FILENAME
        self.global_config_dir = Path(appdirs.user_config_dir(GLOBAL_CONFIG_DIR_NAME))
        self.global_config_path = self.global_config_dir / GLOBAL_CONFIG_FILENAME
        self.console = console or Console()

    def load_project_state(self) -> ProjectState:
        """ Loads project state from .npconfig.toml, returning defaults if not found. """
        state = ProjectState() # Start with defaults
        if self.project_config_path.exists():
            try:
                with open(self.project_config_path, "r", encoding="utf-8") as f:
                    data = toml.load(f)
                # Load preferences
                state.default_includes = data.get("include", state.default_includes)
                state.default_excludes = data.get("exclude", state.default_excludes)
                state.default_llms = data.get("llms", state.default_llms)
                state.default_model_overrides = data.get("model_overrides", state.default_model_overrides)
                # Load internal state
                state.git_repo_map = data.get("git_repo_map", state.git_repo_map)
            except Exception as e:
                self.console.print(f"[yellow]Warning:[/yellow] Could not load project config '{self.project_config_path}': {e}")
        return state

    def save_project_state(self, state: ProjectState) -> None:
        """ Saves the project state (prefs + git map) to .npconfig.toml. """
        data = {
            "include": state.default_includes,
            "exclude": state.default_excludes,
            "llms": state.default_llms,
            "model_overrides": state.default_model_overrides,
            "git_repo_map": state.git_repo_map,
        }
        try:
            with open(self.project_config_path, "w", encoding="utf-8") as f:
                toml.dump(data, f)
        except Exception as e:
            self.console.print(f"[red]Error:[/red] Could not save project config '{self.project_config_path}': {e}")

    def update_git_repo_map(self, repo_key: str, folder_name: str) -> None:
        """ Adds or updates an entry in the git_repo_map and saves immediately. """
        state = self.load_project_state()
        if state.git_repo_map.get(repo_key) != folder_name:
            state.git_repo_map[repo_key] = folder_name
            self.save_project_state(state)
            self.console.print(f"[dim]Updated git repo map for '{repo_key}' -> '{folder_name}' in {self.project_config_path}[/dim]")

    def load_api_key(self) -> Optional[str]:
        """ Loads OpenRouter API key from ENV var first, then global config, then project backup. """
        load_dotenv() # Load .env file if present in CWD or parent dirs
        api_key = os.getenv(API_KEY_ENV_VAR)
        if api_key:
            # self.console.print("[dim]Using API key from environment variable[/dim]")
            return api_key.strip()

        # Try global config first
        # self.console.print(f"[dim]Looking for API key in global config: {self.global_config_path}[/dim]")
        if self.global_config_path.exists():
            try:
                with open(self.global_config_path, "r", encoding="utf-8") as f:
                    data = toml.load(f)
                api_key = data.get("settings", {}).get(API_KEY_ENV_VAR)
                if api_key:
                    # self.console.print("[dim]Found API key in global config[/dim]")
                    return api_key.strip()
                else:
                    # self.console.print("[dim]No API key in global config (key exists but empty)[/dim]")
                    pass
            except Exception as e:
                self.console.print(f"[yellow]Warning:[/yellow] Could not load global config '{self.global_config_path}': {e}")
        else:
            # self.console.print("[dim]Global config file not found[/dim]")
            pass
            
        # Try project config as fallback
        if self.project_config_path.exists():
            try:
                with open(self.project_config_path, "r", encoding="utf-8") as f:
                    data = toml.load(f)
                api_key = data.get("api_key_backup")
                if api_key:
                    self.console.print("[yellow]Using API key from project config (fallback)[/yellow]")
                    return api_key.strip()
            except Exception as e:
                # Silently ignore project config errors here
                pass
                
        return None

    def save_api_key(self, api_key: str) -> bool:
        """ Saves OpenRouter API key to the global config file. """
        global_success = False
        try:
            self.global_config_dir.mkdir(parents=True, exist_ok=True)
            # Attempt to set permissions (works reliably on Unix-like systems)
            try:
                os.chmod(self.global_config_dir, 0o700)
            except OSError:
                pass # Ignore if chmod fails (e.g., on Windows)

            data = {"settings": {API_KEY_ENV_VAR: api_key}}
            with open(self.global_config_path, "w", encoding="utf-8") as f:
                toml.dump(data, f)
            try:
                os.chmod(self.global_config_path, 0o600)
            except OSError:
                pass # Ignore if chmod fails
            
            # Print location information to confirm global storage
            self.console.print(f"[green]API Key saved globally to:[/green] [cyan]{self.global_config_path}[/cyan]")
            self.console.print("[dim]This key will be used for all nerd-prompt projects[/dim]")
            global_success = True
        except Exception as e:
            self.console.print(f"[red]Error:[/red] Could not save API key to global config: {e}")
            global_success = False
        
        # Always save to project config as well as a fallback
        try:
            project_state = self.load_project_state()
            # Create a special section just for the API key
            project_data = {
                "include": project_state.default_includes,
                "exclude": project_state.default_excludes,
                "llms": project_state.default_llms,
                "model_overrides": project_state.default_model_overrides,
                "git_repo_map": project_state.git_repo_map,
                # Add a section for the API key
                "api_key_backup": api_key,
            }
            with open(self.project_config_path, "w", encoding="utf-8") as f:
                toml.dump(project_data, f)
            
            if not global_success:
                self.console.print(f"[yellow]API Key saved to project config as fallback:[/yellow] [cyan]{self.project_config_path}[/cyan]")
            
            return True
        except Exception as e:
            if not global_success:
                self.console.print(f"[red]Error:[/red] Could not save API key to project config either: {e}")
                return False
            else:
                # Global save succeeded, so we're good even if project save failed
                return True

    def load_gitignore_patterns(self) -> List[str]:
        """ Loads patterns from .gitignore in the project root. """
        gitignore_path = self.project_root / ".gitignore"
        patterns = []
        if gitignore_path.exists():
            try:
                with open(gitignore_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#"):
                            patterns.append(line)
            except Exception as e:
                self.console.print(f"[yellow]Warning:[/yellow] Could not read '{gitignore_path}': {e}")
        return patterns

    def debug_api_key(self, verbose: bool = True) -> None:
        """
        Debug helper for API key issues.
        Checks environment variables and global config file to diagnose API key problems.
        """
        if verbose:
            self.console.print(f"[dim]Checking API key storage locations...[/dim]")
            self.console.print(f"[dim]Environment variable: {API_KEY_ENV_VAR}[/dim]")
            self.console.print(f"[dim]Global config path: {self.global_config_path}[/dim]")
        
        # Check environment
        env_key = os.getenv(API_KEY_ENV_VAR)
        if env_key:
            if verbose:
                masked_key = f"{env_key[:8]}...{env_key[-4:]}" if len(env_key) > 12 else "***"
                self.console.print(f"[green]✓[/green] API key found in environment variable: {masked_key}")
        else:
            if verbose:
                self.console.print(f"[yellow]⚠[/yellow] No API key found in environment variable")
        
        # Check global config
        if self.global_config_path.exists():
            if verbose:
                self.console.print(f"[green]✓[/green] Global config file exists")
            try:
                with open(self.global_config_path, "r", encoding="utf-8") as f:
                    data = toml.load(f)
                global_key = data.get("settings", {}).get(API_KEY_ENV_VAR)
                if global_key:
                    if verbose:
                        masked_key = f"{global_key[:8]}...{global_key[-4:]}" if len(global_key) > 12 else "***"
                        self.console.print(f"[green]✓[/green] API key found in global config: {masked_key}")
                else:
                    if verbose:
                        self.console.print(f"[yellow]⚠[/yellow] No API key entry in global config")
            except Exception as e:
                if verbose:
                    self.console.print(f"[red]✗[/red] Error reading global config: {e}")
        else:
            if verbose:
                self.console.print(f"[yellow]⚠[/yellow] Global config file does not exist")
        
        # Check file permissions on global config dir and file
        if self.global_config_dir.exists():
            if verbose:
                self.console.print(f"[green]✓[/green] Global config directory exists")
            try:
                import stat
                dir_mode = self.global_config_dir.stat().st_mode
                dir_perms = stat.filemode(dir_mode)
                if verbose:
                    self.console.print(f"[dim]Directory permissions: {dir_perms}[/dim]")
                
                if self.global_config_path.exists():
                    file_mode = self.global_config_path.stat().st_mode
                    file_perms = stat.filemode(file_mode)
                    if verbose:
                        self.console.print(f"[dim]File permissions: {file_perms}[/dim]")
            except Exception as e:
                if verbose:
                    self.console.print(f"[dim]Could not check file permissions: {e}[/dim]")
        else:
            if verbose:
                self.console.print(f"[yellow]⚠[/yellow] Global config directory does not exist")
        
        # Check if we can load the key successfully
        api_key = self.load_api_key()
        if api_key:
            if verbose:
                self.console.print(f"[green]✓[/green] Successfully loaded API key through normal channels")
        else:
            if verbose:
                self.console.print(f"[red]✗[/red] No API key could be loaded") 