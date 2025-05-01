from pathlib import Path
from typing import Optional, List, Dict, Any

import questionary
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from .config import ConfigManager, RunConfig, ProjectState
from .utils import sanitize_filename

# Style for questionary
custom_style = questionary.Style([
    ('qmark', 'fg:#673ab7 bold'),       # Mark question with '?'.
    ('question', 'bold'),               # Question text.
    ('answer', 'fg:#ff5722 bold'),      # Answer text has yellowish color.
    ('pointer', 'fg:#673ab7 bold'),     # Pointer symbol '»'.
    ('highlighted', 'fg:#673ab7 bold'), # Highlighted selection in a list.
    ('selected', 'fg:#cc5454'),         # Marked choice in a checkbox prompt.
    ('separator', 'fg:#cc5454'),        # Separator in lists.
    ('instruction', ''),                # Guidance instructions.
    ('text', ''),                       # Plain text.
    ('disabled', 'fg:#858585 italic')   # Disabled choices.
])

class InteractiveSetup:
    """ Handles the interactive configuration flow using questionary. """
    def __init__(self, config_manager: ConfigManager, console: Console):
        self.config_manager = config_manager
        self.console = console
        self.project_state: ProjectState = config_manager.load_project_state()
        self.run_config = RunConfig(project_root=config_manager.project_root)
        self.gitignore_patterns = config_manager.load_gitignore_patterns()

    def _ask_sources(self) -> None:
        """ Step 1: Configure include/exclude patterns. """
        self.console.print(Panel("Step 1: Configure Sources", title="Interactive Setup", expand=False, style="blue"))

        # Display current settings
        table = Table(title="Current Source Configuration", show_header=False, box=None)
        table.add_row("[bold]Includes:[/bold]", "\n".join(f"- `{p}`" for p in self.project_state.default_includes) or "[dim]None[/dim]")
        table.add_row("[bold]Excludes:[/bold]", "\n".join(f"- `{p}`" for p in self.project_state.default_excludes) or "[dim]None[/dim]")
        if self.gitignore_patterns:
            table.add_row("[bold].gitignore:[/bold]", f"[dim]({len(self.gitignore_patterns)} patterns loaded)[/dim]")
        self.console.print(table)

        modify = questionary.confirm(
            "Modify include/exclude patterns?",
            default=False,
            style=custom_style
        ).ask()

        if modify:
            includes_str = questionary.text(
                "Includes (space-separated paths/globs/URLs):",
                default=" ".join(self.project_state.default_includes),
                 instruction="Use './' for project root. URLs treated as Git.",
                 style=custom_style
            ).ask()
            self.project_state.default_includes = includes_str.split() if includes_str else ["./"]

            excludes_str = questionary.text(
                "Excludes (space-separated paths/globs):",
                 default=" ".join(self.project_state.default_excludes),
                 instruction="These are added to .gitignore patterns.",
                 style=custom_style
            ).ask()
            self.project_state.default_excludes = excludes_str.split() if excludes_str else []

        # Use the potentially modified state for the current run
        self.run_config.includes = self.project_state.default_includes
        self.run_config.excludes = self.project_state.default_excludes # Core will combine these later

    def _ask_llms(self) -> None:
        """ Step 2: Configure target LLMs. """
        self.console.print(Panel("Step 2: Select LLMs", title="Interactive Setup", expand=False, style="blue"))
        current_llms = self.project_state.default_llms
        self.console.print(f"Current default LLMs: [cyan]{', '.join(current_llms) or 'None'}[/cyan]")

        llms_str = questionary.text(
            "Enter LLM names (space-separated):",
            default=" ".join(current_llms),
            instruction="Use 'model/name' for OpenRouter auto-processing, others are manual placeholders.",
            style=custom_style
        ).ask()
        selected_llms = llms_str.split() if llms_str else []
        self.run_config.llms = selected_llms
        self.project_state.default_llms = selected_llms # Update default for next time

    def _ask_task_name(self) -> None:
        """ Step 3: Get the task name. """
        self.console.print(Panel("Step 3: Name Your Task", title="Interactive Setup", expand=False, style="blue"))
        task_name = ""
        while not task_name:
             task_name = questionary.text(
                  "Enter a short, descriptive name for this task:",
                  validate=lambda text: True if len(text) > 0 else "Task name cannot be empty.",
                  style=custom_style
             ).ask()
        # Sanitize here for immediate use, core might re-sanitize but that's okay
        self.run_config.task_name = sanitize_filename(task_name)

    def _ask_task_definition(self) -> None:
        """ Step 4: Get the task definition. """
        self.console.print(Panel("Step 4: Define the Task", title="Interactive Setup", expand=False, style="blue"))
        method = questionary.select(
            "How do you want to provide the task definition?",
            choices=[
                "Enter task instructions directly",
                "Provide path to a task file (.md or .txt)"
            ],
            style=custom_style
        ).ask()

        if method == "Enter task instructions directly":
            task_def = questionary.text("Enter task definition:", multiline=True, style=custom_style).ask()
            self.run_config.task_definition = task_def or ""
        else:
            file_path_str = questionary.path(
                 "Enter path to task file:",
                 validate=lambda p: Path(p).is_file() or "File not found.",
                 file_filter=lambda p: p.endswith(('.md', '.txt')),
                 style=custom_style
             ).ask()
            if file_path_str:
                try:
                     with open(file_path_str, 'r', encoding='utf-8') as f:
                         self.run_config.task_definition = f.read()
                except Exception as e:
                     self.console.print(f"[red]Error reading task file '{file_path_str}': {e}[/red]")
                     self.run_config.task_definition = f"# Error loading task from {file_path_str}\n{e}"
            else:
                 self.run_config.task_definition = "" # User cancelled path prompt

    def _ask_advanced(self) -> None:
        """ Step 5: Optional advanced settings (API Key, Parameters). """
        self.console.print(Panel("Step 5: Advanced Settings (Optional)", title="Interactive Setup", expand=False, style="blue"))

        configure_advanced = questionary.confirm("Configure advanced settings?", default=False, style=custom_style).ask()
        if not configure_advanced:
            return

        # API Key Management
        api_key_action = questionary.select(
            "Manage OpenRouter API Key?",
            choices=[
                 {"name": "Keep existing / Skip (if key already set)", "value": "skip"},
                 {"name": "Update / Enter New Key", "value": "update"},
            ],
            style=custom_style
        ).ask()

        if api_key_action == "update":
            new_api_key = questionary.password(
                 "Enter your OpenRouter API Key:",
                 validate=lambda key: True if key.startswith("sk-or-") else "Key should start with 'sk-or-'",
                 style=custom_style
            ).ask()
            if new_api_key:
                 if self.config_manager.save_api_key(new_api_key):
                     self.console.print("[green]API Key saved globally.[/green]")
                     self.run_config.api_key = new_api_key # Use the newly entered key for this run
                 else:
                     self.console.print("[red]Failed to save API key. Using existing key if available.[/red]")
                     self.run_config.api_key = self.config_manager.load_api_key() # Fallback
            else:
                self.console.print("[yellow]API Key update cancelled.[/yellow]")
                self.run_config.api_key = self.config_manager.load_api_key()
        else:
             # Load existing key for the run if skipping update
             self.run_config.api_key = self.config_manager.load_api_key()


        # Parameter Overrides
        configure_params = questionary.confirm(
            "Set custom OpenRouter parameters for specific models?",
            default=False,
            style=custom_style
        ).ask()
        if configure_params:
            self.run_config.model_overrides = self.project_state.default_model_overrides.copy() # Start with defaults
            while True:
                model_to_override = questionary.text(
                    "Enter model name to override (or leave blank to finish):",
                    instruction="e.g., google/gemini-pro",
                    style=custom_style
                ).ask()
                if not model_to_override:
                    break

                param_key = questionary.text(f"Parameter key for '{model_to_override}':", style=custom_style).ask()
                if not param_key: continue

                param_value_str = questionary.text(f"Parameter value for '{param_key}':", style=custom_style).ask()
                if not param_value_str: continue

                # Attempt to convert value to appropriate type (float, int, bool, str)
                try:
                     param_value: Any = float(param_value_str)
                     if param_value.is_integer():
                          param_value = int(param_value)
                except ValueError:
                     if param_value_str.lower() == 'true':
                          param_value = True
                     elif param_value_str.lower() == 'false':
                          param_value = False
                     else:
                          param_value = param_value_str # Keep as string

                if model_to_override not in self.run_config.model_overrides:
                    self.run_config.model_overrides[model_to_override] = {}
                self.run_config.model_overrides[model_to_override][param_key] = param_value
                self.console.print(f"Set '{param_key}' = {param_value} for '{model_to_override}'")

            # Update project state defaults for next time
            self.project_state.default_model_overrides = self.run_config.model_overrides


    def _confirm_and_proceed(self) -> bool:
        """ Final confirmation step. """
        self.console.print(Panel("Run Configuration Summary", title="Confirmation", expand=False, style="green"))

        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_row("[bold]Task Name:[/bold]", self.run_config.task_name)
        table.add_row("[bold]Includes:[/bold]", f"[cyan]{' '.join(self.run_config.includes)}[/cyan]")
        table.add_row("[bold]Excludes:[/bold]", f"[dim]{' '.join(self.run_config.excludes) or 'None'}[/dim]")
        table.add_row("[bold]LLMs:[/bold]", f"[cyan]{' '.join(self.run_config.llms) or 'None'}[/cyan]")
        task_preview = self.run_config.task_definition[:200].strip() + ("..." if len(self.run_config.task_definition) > 200 else "")
        table.add_row("[bold]Task Def:[/bold]", task_preview or "[dim]Empty[/dim]")
        api_status = "[green]Set/Found[/green]" if self.run_config.api_key else "[yellow]Not Set[/yellow]"
        table.add_row("[bold]API Key:[/bold]", api_status)
        if self.run_config.model_overrides:
            overrides_str = "\n".join(f"  [bold]{m}:[/bold] {p}" for m, p in self.run_config.model_overrides.items())
            table.add_row("[bold]Overrides:[/bold]", overrides_str)

        self.console.print(table)

        proceed = questionary.confirm("Proceed with this configuration?", default=True, style=custom_style).ask()
        return proceed or False


    def run_setup(self) -> Optional[RunConfig]:
        """ Executes the full interactive setup process. """
        try:
            self._ask_sources()
            self._ask_llms()
            self._ask_task_name()
            self._ask_task_definition()
            self._ask_advanced() # This step loads/updates run_config.api_key

            # Save confirmed preferences (not task name/def) back to config
            # The git_repo_map is saved separately by git_handler
            self.config_manager.save_project_state(self.project_state)
            self.console.print(f"[dim]Default includes/excludes/LLMs saved to {self.config_manager.project_config_path}[/dim]")


            if self._confirm_and_proceed():
                return self.run_config
            else:
                self.console.print("Operation cancelled by user.")
                return None
        except KeyboardInterrupt:
            self.console.print("\nOperation cancelled by user.")
            return None
        except Exception as e:
             self.console.print_exception(show_locals=False)
             self.console.print(f"[bold red]An unexpected error occurred during interactive setup: {e}[/bold red]")
             return None 