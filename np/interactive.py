from pathlib import Path
from typing import Optional, List, Dict, Any
import os
import stat
import time

import questionary
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from .config import ConfigManager, RunConfig, ProjectState, GLOBAL_CONFIG_DIR_NAME, API_KEY_ENV_VAR
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
        self.run_config.api_key = self.config_manager.load_api_key()
        self.gitignore_patterns = config_manager.load_gitignore_patterns()

    def _ask_sources(self) -> None:
        """ Step 1: Configure include/exclude patterns. Updates self.run_config. """
        self.console.print() # Add newline for spacing
        self.console.print(Panel("Step 1: Configure Sources", title="Interactive Setup", expand=False, style="blue"))

        # Display current settings from self.run_config
        table = Table(title="Current Source Configuration", show_header=False, box=None)
        table.add_row("[bold]Includes:[/bold]", "\\n".join(f"- `{p}`" for p in self.run_config.includes) or "[dim]None[/dim]")
        
        excludes_display_list = [f"`{p}`" for p in self.run_config.excludes]
        excludes_display_str = " ".join(excludes_display_list) if excludes_display_list else "None"
        table.add_row("[bold]Excludes:[/bold]", f"[dim]{excludes_display_str}[/dim]")

        if self.gitignore_patterns: # This comes from config_manager, not run_config
            table.add_row("[bold].gitignore:[/bold]", f"[dim]({len(self.gitignore_patterns)} patterns loaded)[/dim]")
        self.console.print(table)
        self.console.print() # Add newline for spacing

        modify = questionary.confirm(
            "Modify include/exclude patterns?",
            default=False,
            style=custom_style
        ).ask()

        if modify:
            includes_str = questionary.text(
                "Includes (space-separated paths/globs/URLs):",
                default=" ".join(self.run_config.includes), # Default from current run_config
                 instruction="Use './' for project root. URLs treated as Git.",
                 style=custom_style
            ).ask()
            self.run_config.includes = includes_str.split() if includes_str else ["./"]

            excludes_str = questionary.text(
                "Excludes (space-separated paths/globs):",
                 default=" ".join(self.run_config.excludes), # Default from current run_config
                 instruction="These are added to .gitignore patterns.",
                 style=custom_style
            ).ask()
            self.run_config.excludes = excludes_str.split() if excludes_str else []
        # self.project_state is updated centrally in run_setup

    def _ask_llms(self) -> None:
        """ Step 2: Configure target LLMs. Updates self.run_config. """
        self.console.print() # Add newline for spacing
        self.console.print(Panel("Step 2: Select LLMs", title="Interactive Setup", expand=False, style="blue"))
        
        current_llms_in_run_config = self.run_config.llms
        self.console.print(f"Current LLMs for this run: [cyan]{', '.join(current_llms_in_run_config) or 'None'}[/cyan]")
        self.console.print() # Add newline for spacing

        llms_str = questionary.text(
            "Enter LLM names (space-separated):",
            default=" ".join(current_llms_in_run_config), # Default from current run_config
            instruction="Use 'model/name' for OpenRouter auto-processing, others are manual placeholders.",
            style=custom_style
        ).ask()
        self.run_config.llms = llms_str.split() if llms_str else []
        # self.project_state is updated centrally in run_setup

    def _ask_task_name(self) -> None:
        """ Step 3: Get the task name. Updates self.run_config. """
        self.console.print() # Add newline for spacing
        self.console.print(Panel("Step 3: Name Your Task", title="Interactive Setup", expand=False, style="blue"))
        
        task_name = ""
        # Default to current run_config.task_name, which might have been pre-filled
        default_task_name = self.run_config.task_name or self.project_state.last_task_name or ""

        while not task_name:
             task_name = questionary.text(
                  "Enter a short, descriptive name for this task:",
                  default=default_task_name, 
                  validate=lambda text: True if len(text) > 0 else "Task name cannot be empty.",
                  style=custom_style
             ).ask()
        self.run_config.task_name = sanitize_filename(task_name)
        # self.project_state is updated centrally in run_setup

    def _ask_task_definition_interactive(self) -> None:
        """ Step 4a: Get task definition (interactive: choice of direct input or file). Updates self.run_config. """
        self.console.print() 
        self.console.print(Panel("Step 4: Define the Task", title="Interactive Setup", expand=False, style="blue"))
        method = questionary.select(
            "How do you want to provide the task definition?",
            choices=[
                "Enter task instructions directly",
                "Provide path to a task file (.md or .txt)"
            ],
            style=custom_style,
            default="Enter task instructions directly"
        ).ask()

        if method == "Enter task instructions directly":
            task_def = questionary.text("Enter task definition:", multiline=True, style=custom_style, default=self.run_config.task_definition or "").ask()
            self.run_config.task_definition = task_def or ""
        elif method == "Provide path to a task file (.md or .txt)":
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
                     self.run_config.task_definition = f"# Error loading task from {file_path_str}\n{e}" # Ensure newline
            else:
                 self.run_config.task_definition = "" 
        else: # Should not happen with questionary.select
            self.run_config.task_definition = ""

    def _ask_task_definition_direct(self) -> None:
        """ Step 4b: Get the task definition via direct input only. Updates self.run_config. """
        self.console.print() 
        self.console.print(Panel("Define Task/Prompt", title="Interactive Setup", expand=False, style="blue"))
        task_def = questionary.text(
            "Enter task definition/prompt:",
            multiline=True,
            style=custom_style,
            default=self.run_config.task_definition or "" 
        ).ask()
        self.run_config.task_definition = task_def or ""

    def _ask_advanced(self) -> None:
        """ Step 5: Optional advanced settings (API Key, Parameters). Updates self.run_config. """
        self.console.print() 
        self.console.print(Panel("Step 5: Advanced Settings", title="Interactive Setup", expand=False, style="blue"))

        # API Key Management first, as it's often the primary reason to enter advanced.
        # self.run_config.api_key should be pre-loaded in __init__
        if self.run_config.api_key:
            masked_key = f"{self.run_config.api_key[:8]}...{self.run_config.api_key[-4:]}" if len(self.run_config.api_key) > 12 else "***"
            self.console.print(f"Current API key: [green]{masked_key}[/green]")
        else:
            self.console.print("[yellow]No API key found.[/yellow]")
        
        # Define choices explicitly
        api_key_choices = [
            questionary.Choice(title="Keep existing / Skip", value="skip"),
            questionary.Choice(title="Update / Enter New Key", value="update")
        ]
        
        api_key_action = questionary.select(
            "Manage OpenRouter API Key?",
            choices=api_key_choices,
            style=custom_style,
            default=api_key_choices[0]  # Default to the first Choice object
        ).ask()

        if api_key_action == "update":
            # ... (Existing API key update logic - check_directory_access, verify_key_storage, etc.)
            # This logic should ultimately set self.run_config.api_key if successful
            # For brevity, assuming the existing logic is sound and updates self.config_manager / saves key
            # The crucial part is to get the new key into self.run_config.api_key
            import appdirs # Keep imports local if only used here
            
            # (Omitting the full local check_directory_access and verify_key_storage for brevity in this diff)
            # Assume these functions are defined correctly elsewhere or remain as is if they don't need self.
            # The key point is that new_api_key is obtained and then:
            new_api_key_input = questionary.password(
                 "Enter your OpenRouter API Key:",
                 validate=lambda key: True if key.startswith("sk-or-") else "Key should start with 'sk-or-'",
                 style=custom_style
            ).ask()
            if new_api_key_input:
                 if self.config_manager.save_api_key(new_api_key_input): # save_api_key handles global storage
                     self.run_config.api_key = new_api_key_input # Update run_config
                     masked_key = f"{new_api_key_input[:8]}...{new_api_key_input[-4:]}" if len(new_api_key_input) > 12 else "***"
                     self.console.print(f"[green]API key updated for this run and saved globally: {masked_key}[/green]")
                 else:
                     self.console.print("[red]Failed to save API key globally. Using for current run only.[/red]")
                     self.run_config.api_key = new_api_key_input # Still use for current run
            else:
                self.console.print("[yellow]API Key update cancelled.[/yellow]")
        
        self.console.print() # Spacing before parameter overrides

        # Parameter Overrides
        configure_params = questionary.confirm(
            "Set custom OpenRouter parameters for specific models?",
            default=bool(self.run_config.model_overrides), # Default to true if overrides exist
            style=custom_style
        ).ask()

        if configure_params:
            # Work on a copy from run_config, which was initialized from project_state
            temp_model_overrides = self.run_config.model_overrides.copy()
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
                
                # Allow empty string to clear a parameter
                if param_value_str is None: # User cancelled
                    continue
                
                param_value: Any
                if param_value_str == "":
                    # Logic to remove the parameter if value is empty string
                    if model_to_override in temp_model_overrides and param_key in temp_model_overrides[model_to_override]:
                        del temp_model_overrides[model_to_override][param_key]
                        if not temp_model_overrides[model_to_override]: # if no params left for model
                            del temp_model_overrides[model_to_override]
                        self.console.print(f"Cleared '{param_key}' for '{model_to_override}'")
                    else:
                        self.console.print(f"[dim]Parameter '{param_key}' not found for '{model_to_override}'.[/dim]")
                    continue

                try:
                     param_value = float(param_value_str)
                     if param_value.is_integer():
                          param_value = int(param_value)
                except ValueError:
                     if param_value_str.lower() == 'true':
                          param_value = True
                     elif param_value_str.lower() == 'false':
                          param_value = False
                     else:
                          param_value = param_value_str 

                if model_to_override not in temp_model_overrides:
                    temp_model_overrides[model_to_override] = {}
                temp_model_overrides[model_to_override][param_key] = param_value
                self.console.print(f"Set '{param_key}' = {param_value} for '{model_to_override}'")
            
            self.run_config.model_overrides = temp_model_overrides # Update run_config
        # self.project_state default_model_overrides updated centrally in run_setup

    def _show_quick_summary(self) -> None:
        """ Displays a quick summary of the current self.run_config. """
        self.console.print()
        self.console.print(Panel("Current Run Configuration", title="Summary", expand=False, style="green"))

        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_row("[bold]Task Name:[/bold]", self.run_config.task_name or "[dim]Not Set[/dim]")
        
        includes_display = "\\n".join(f"- `{p}`" for p in self.run_config.includes) if self.run_config.includes else "[dim]None[/dim]"
        table.add_row("[bold]Includes:[/bold]", f"[cyan]{includes_display}[/cyan]")
        
        excludes_display_list = [f"`{p}`" for p in self.run_config.excludes]
        excludes_display_str = " ".join(excludes_display_list) if excludes_display_list else "None"
        table.add_row("[bold]Excludes:[/bold]", f"[dim]{excludes_display_str}[/dim]")
        
        table.add_row("[bold]LLMs:[/bold]", f"[cyan]{', '.join(self.run_config.llms) or 'None'}[/cyan]")
        
        task_preview = (self.run_config.task_definition[:200].strip() + 
                        ("..." if len(self.run_config.task_definition) > 200 else ""))
        table.add_row("[bold]Task Def:[/bold]", task_preview or "[dim]Not Set[/dim]")
        
        if self.run_config.api_key:
            masked_key = f"{self.run_config.api_key[:8]}...{self.run_config.api_key[-4:]}" if len(self.run_config.api_key) > 12 else "***"
            api_status = f"[green]Set: {masked_key}[/green]"
        else:
            api_status = "[yellow]Not Set[/yellow]"
        table.add_row("[bold]API Key:[/bold]", api_status)
        
        if self.run_config.model_overrides:
            overrides_str = "\\n".join(f"  [bold]{m}:[/bold] {p}" for m, p in self.run_config.model_overrides.items())
            table.add_row("[bold]Overrides:[/bold]", overrides_str)
        else:
            table.add_row("[bold]Overrides:[/bold]", "[dim]None[/dim]")

        self.console.print(table)
        self.console.print()


    def _confirm_and_proceed(self) -> bool:
        """ Final confirmation step, using self.run_config. """
        self._show_quick_summary() # Re-use quick summary for display
        proceed = questionary.confirm("Proceed with this configuration?", default=True, style=custom_style).ask()
        return proceed or False


    def run_setup(self) -> Optional[RunConfig]:
        """ Executes the full interactive setup process. """
        try:
            # self.run_config.api_key is pre-loaded in __init__
            has_existing_config_file = self.config_manager.project_config_path.exists()

            if not has_existing_config_file:
                self.console.print("[italic]No project configuration file found. Starting full setup...[/italic]")
                self.console.print()
                # Initialize run_config from fresh ProjectState defaults for a new config
                fresh_project_state = ProjectState()
                self.run_config.includes = list(fresh_project_state.default_includes)
                self.run_config.excludes = list(fresh_project_state.default_excludes)
                self.run_config.llms = list(fresh_project_state.default_llms)
                self.run_config.task_name = sanitize_filename(Path(self.config_manager.project_root).name) # Default
                self.run_config.model_overrides = fresh_project_state.default_model_overrides.copy()
                # Task definition and API key (already loaded) will be handled by _ask methods

                self._ask_sources()
                self._ask_llms()
                self._ask_task_name()
                self._ask_task_definition_interactive() # Full version for new setup
                self._ask_advanced()
                
                if not self._confirm_and_proceed():
                    self.console.print("Operation cancelled by user.")
                    return None
            else:
                self.console.print(f"[italic]Existing project configuration loaded from {self.config_manager.project_config_path}[/italic]")
                self.console.print()
                # Populate run_config from the loaded self.project_state
                self.run_config.includes = list(self.project_state.default_includes)
                self.run_config.excludes = list(self.project_state.default_excludes)
                self.run_config.llms = list(self.project_state.default_llms)
                self.run_config.task_name = self.project_state.last_task_name or sanitize_filename(Path(self.config_manager.project_root).name + "-task")
                self.run_config.model_overrides = self.project_state.default_model_overrides.copy()
                # self.run_config.task_definition is initially empty, user must define or it stays empty.
                # self.run_config.api_key is already loaded.

                while True:
                    self._show_quick_summary()
                    choices = [
                        questionary.Choice("Define/Redefine Task Prompt", value="define_task"),
                        questionary.Separator(),
                        questionary.Choice("Edit Sources (Includes/Excludes)", value="edit_sources"),
                        questionary.Choice("Edit LLMs", value="edit_llms"),
                        questionary.Choice("Edit Task Name", value="edit_task_name"),
                        questionary.Choice("Edit Advanced Settings (API Key, Parameters)", value="edit_advanced"),
                        questionary.Separator(),
                        questionary.Choice("➡️ Proceed with this configuration", value="proceed"),
                        questionary.Choice("❌ Cancel Setup", value="cancel")
                    ]
                    
                    # Determine a sensible default action
                    default_action = choices[0] # Default to "Define Task"
                    if self.run_config.task_definition: # If task is already defined, maybe "Proceed" is better
                        default_action = next(c for c in choices if c.value == "proceed")


                    action = questionary.select(
                        "What would you like to do?",
                        choices=choices,
                        default=default_action,
                        style=custom_style
                    ).ask()

                    if action == "define_task":
                        self._ask_task_definition_direct()
                    elif action == "edit_sources":
                        self._ask_sources()
                    elif action == "edit_llms":
                        self._ask_llms()
                    elif action == "edit_task_name":
                        self._ask_task_name()
                    elif action == "edit_advanced":
                        self._ask_advanced()
                    elif action == "proceed":
                        if not self.run_config.task_definition:
                            self.console.print("[yellow]Task definition is empty. Please define the task first or confirm if you want to proceed with an empty task.[/yellow]")
                            if not questionary.confirm("Proceed with an empty task definition?", default=False, style=custom_style).ask():
                                continue # Go back to menu
                        
                        # No need for _confirm_and_proceed() here as summary was just shown
                        # and user explicitly chose to proceed.
                        self.console.print("[green]Configuration confirmed.[/green]")
                        break 
                    elif action == "cancel" or action is None:
                        self.console.print("Operation cancelled by user.")
                        return None
                    
                    # After an edit action, loop back to show summary and choices again.

            # ---- Common section for saving and returning ----
            # Save the final state of run_config to project_state for next time
            self.project_state.default_includes = list(self.run_config.includes)
            self.project_state.default_excludes = list(self.run_config.excludes)
            self.project_state.default_llms = list(self.run_config.llms)
            if self.run_config.task_name: # Ensure task_name is not None
                 self.project_state.last_task_name = self.run_config.task_name
            self.project_state.default_model_overrides = self.run_config.model_overrides.copy()

            self.config_manager.save_project_state(self.project_state)
            self.console.print(f"[dim]Project configuration preferences saved to {self.config_manager.project_config_path}[/dim]")
            self.console.print()

            return self.run_config

        except KeyboardInterrupt:
            self.console.print("\nOperation cancelled by user.")
            return None
        except Exception as e:
             # Make sure console is defined for print_exception
             if not hasattr(self, 'console') or self.console is None: 
                 self.console = Console() 
             self.console.print_exception(show_locals=False)
             self.console.print(f"[bold red]An unexpected error occurred during interactive setup: {e}[/bold red]")
             return None 