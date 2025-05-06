import sys
from pathlib import Path
from typing import List, Optional, Tuple, Annotated
import os
import stat
import time

import typer
from rich.console import Console
from rich.panel import Panel

from .config import ConfigManager, RunConfig, ProjectState, DEFAULT_EXCLUDES, API_KEY_ENV_VAR, GLOBAL_CONFIG_DIR_NAME
from .interactive import InteractiveSetup
from .core import CoreProcessor
from .output_builder import OutputBuilder
from .git_handler import GitHandler
from .llm_api import LLMApi
from . import __version__

# Create Typer app
app = typer.Typer(
    name="np",
    help="nerd-prompt: Context Assembler & LLM Interaction CLI.",
    add_completion=True,
    no_args_is_help=False,
    invoke_without_command=True
)

console = Console()

def version_callback(value: bool):
    if value:
        console.print(f"nerd-prompt version: {__version__}")
        raise typer.Exit()

@app.callback()
def main_callback(
    ctx: typer.Context,
    version: Annotated[Optional[bool], typer.Option("--version", "-V", callback=version_callback, is_eager=True, help="Show version and exit.")] = None,
):
    """ Nerd Prompt CLI entry point """
    if ctx.invoked_subcommand is None:
        # If no subcommand is given (e.g., just 'np'), run the interactive setup.
        # We need to manually call the logic that the 'run' command would execute
        # when it decides to go into interactive mode.
        project_root = Path.cwd()
        config_manager = ConfigManager(project_root, console)
        console.print("[bold green]No command specified. Starting interactive setup...[/bold green]")
        interactive_setup = InteractiveSetup(config_manager, console)
        run_config_obj = interactive_setup.run_setup()
        if not run_config_obj:
            raise typer.Exit(code=1)
        
        # Since we are bypassing the direct call to the 'run' command, 
        # we need to manually trigger the core processing if setup was successful.
        # This duplicates the latter part of the 'run' command logic.
        # Ensure API key is in run_config (should be handled by interactive_setup)
        if not run_config_obj.api_key and any("/" in llm_name for llm_name in run_config_obj.llms):
            console.print("[yellow]Warning: API key not set. OpenRouter models may fail.[/yellow]")

        # Correctly instantiate all components before CoreProcessor
        output_builder = OutputBuilder(config_manager.project_root, console)
        git_handler = GitHandler(run_config_obj.project_root, config_manager, output_builder, console)
        # LLMApi will be instantiated inside CoreProcessor.run()
        
        processor = CoreProcessor(
            config=run_config_obj,
            config_manager=config_manager,
            output_builder=output_builder,
            git_handler=git_handler,
            # llm_api removed
            console=console
        )

        # The llm_api.set_task_dir_path will be called within core_processor.run() via output_builder
        try:
            processor.run()
            console.print(f"[bold green]Processing Complete for: {run_config_obj.task_name}[/bold green]")
        except Exception as e:
            # Ensure console is available for printing exceptions
            current_console = getattr(processor, 'console', Console())
            current_console.print_exception(show_locals=False)
            current_console.print(f"[bold red]An unexpected error occurred during core processing: {e}[/bold red]")
            raise typer.Exit(code=1)


# --- Key management helper functions ---
def check_directory_access(path: Path, console: Console) -> bool:
    """Test if we can write to a directory"""
    if not path.exists():
        try:
            path.mkdir(parents=True, exist_ok=True)
            console.print(f"[green]Created directory:[/green] {path}")
        except Exception as e:
            console.print(f"[red]Error creating directory:[/red] {path}\n{str(e)}")
            return False
    
    # Try writing a test file
    test_file = path / "test_write.txt"
    try:
        test_file.write_text("test")
        test_file.unlink()  # Delete after successful test
        console.print(f"[green]Successfully wrote to directory:[/green] {path}")
        return True
    except Exception as e:
        console.print(f"[red]Error writing to directory:[/red] {path}\n{str(e)}")
        return False


def verify_key_storage(api_key: str, config_manager: ConfigManager, console: Console) -> bool:
    """Verify API key is stored in the global config"""
    global_config_path = config_manager.global_config_path
    success = True
    
    # Check global config
    if global_config_path.exists():
        try:
            import toml
            with open(global_config_path, "r", encoding="utf-8") as f:
                data = toml.load(f)
            stored_key = data.get("settings", {}).get(API_KEY_ENV_VAR)
            if stored_key == api_key:
                console.print(f"[green]✓ Key verified in global config:[/green] {global_config_path}")
            else:
                console.print(f"[red]✗ Key in global config doesn't match input key[/red]")
                success = False
        except Exception as e:
            console.print(f"[red]✗ Error reading global config: {e}[/red]")
            success = False
    else:
        console.print(f"[red]✗ Global config file doesn't exist[/red]")
        success = False
    
    return success


# --- Non-Interactive Command Definition ---
# We use a single command function that handles the logic if arguments are present.
# Typer automatically handles the case where no arguments are given if we structure it right,
# or we check sys.argv length in __main__.

# Define options using Annotated for richer help/validation
IncludeOpt = Annotated[Optional[List[str]], typer.Option("--include", "-i", help="Path/glob/URL to include. Repeatable. Overwrites config includes.", show_default=False)]
ExcludeOpt = Annotated[Optional[List[str]], typer.Option("--exclude", "-e", help="Path/glob to exclude (adds to defaults/gitignore). Repeatable.", show_default=False)]
LLMOpt = Annotated[Optional[List[str]], typer.Option("--llm", "-l", help="LLM name (OpenRouter or manual). Repeatable. Overwrites config LLMs.", show_default=False)]
NameOpt = Annotated[str, typer.Option("--name", "-n", help="Short name for the task (required for non-interactive).")]
TaskOpt = Annotated[Optional[str], typer.Option("--task", "-t", help="Task definition text.")]
TaskFileOpt = Annotated[Optional[Path], typer.Option("--task-file", "-f", help="Path to file with task definition.", exists=True, file_okay=True, dir_okay=False, readable=True)]
ParamOpt = Annotated[Optional[List[str]], typer.Option("--param", "-p", help="Override OpenRouter param: MODEL KEY VALUE. Repeatable.")] # We'll handle the grouping in 3s in the code
SetApiKeyOpt = Annotated[bool, typer.Option("--set-api-key", help="Force prompt to enter/update OpenRouter API key.")]
YesOpt = Annotated[bool, typer.Option("-y", "--yes", help="Skip final confirmation prompt.")]


@app.command(no_args_is_help=False)
def run(
    ctx: typer.Context,
    include: IncludeOpt = None,
    exclude: ExcludeOpt = None,
    llm: LLMOpt = None,
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Short name for the task (required for non-interactive)."),
    task: TaskOpt = None,
    task_file: TaskFileOpt = None,
    param: Annotated[Optional[List[str]], typer.Option("--param", "-p", help="Override OpenRouter param: MODEL KEY VALUE (repeatable). Use quotes for values with spaces.", show_default=False)] = None,
    set_api_key: SetApiKeyOpt = False,
    yes: YesOpt = False,
) -> None:
    """
    Runs nerd-prompt. If no arguments are given, enters interactive setup mode.
    Otherwise, uses provided arguments for a non-interactive run.
    """
    project_root = Path.cwd()
    config_manager = ConfigManager(project_root, console)

    # --- Interactive Mode Trigger ---
    # Check if *any* relevant CLI option was provided (excluding -y, --set-api-key for now)
    # A more robust check might inspect Typer's context or check if required args like --name are missing.
    is_non_interactive = any([include, exclude, llm, name, task, task_file, param])

    if not is_non_interactive:
        # --- Run Interactive Mode ---
        console.print("[bold green]No arguments detected. Starting interactive setup...[/bold green]")
        interactive_setup = InteractiveSetup(config_manager, console)
        run_config = interactive_setup.run_setup()
        if not run_config:
            raise typer.Exit(code=1) # Exit if user cancelled
        # API key loaded/prompted during interactive setup

    else:
        # --- Run Non-Interactive Mode ---
        console.print("[bold green]Arguments detected. Running non-interactively...[/bold green]")

        # Validation
        if not name:
            console.print("[bold red]Error:[/bold red] --name is required for non-interactive mode.")
            raise typer.Exit(code=1)
        if task is not None and task_file is not None:
            console.print("[bold red]Error:[/bold red] Use either --task or --task-file, not both.")
            raise typer.Exit(code=1)
        if task is None and task_file is None:
            console.print("[bold red]Error:[/bold red] Either --task or --task-file is required for non-interactive mode.")
            raise typer.Exit(code=1)

        # Load defaults
        project_state = config_manager.load_project_state()

        # Build RunConfig from args + defaults
        run_config = RunConfig(project_root=project_root)
        run_config.task_name = name # Already validated as required
        run_config.includes = list(include) if include else project_state.default_includes
        # Excludes from CLI add to defaults+gitignore (handled in core)
        run_config.excludes = list(exclude) if exclude else []
        run_config.llms = list(llm) if llm else project_state.default_llms
        run_config.skip_confirmation = yes

        # Load task definition
        if task_file:
            try:
                with open(task_file, 'r', encoding='utf-8') as f:
                    run_config.task_definition = f.read()
            except Exception as e:
                console.print(f"[bold red]Error:[/bold red] Failed to read task file '{task_file}': {e}")
                raise typer.Exit(code=1)
        else:
            run_config.task_definition = task or "" # task is Optional[str]

        # Parse parameter overrides
        run_config.model_overrides = project_state.default_model_overrides.copy() # Start with config defaults
        if param:
             current_model = ""
             current_params: Dict[str,Any] = {}
             param_list = list(param) # Make mutable copy
             # This parsing assumes flat list "MODEL KEY VALUE MODEL KEY VALUE ..."
             # A better approach might be Typer's tuple parsing or custom callback if needed.
             # Simple string parsing for now:
             try:
                  grouped_params = [param_list[i:i+3] for i in range(0, len(param_list), 3)]
                  for p_model, p_key, p_value_str in grouped_params:
                      try:
                          p_value: Any = float(p_value_str)
                          if p_value.is_integer(): p_value = int(p_value)
                      except ValueError:
                          if p_value_str.lower() == 'true': p_value = True
                          elif p_value_str.lower() == 'false': p_value = False
                          else: p_value = p_value_str # Keep as string

                      if p_model not in run_config.model_overrides:
                          run_config.model_overrides[p_model] = {}
                      run_config.model_overrides[p_model][p_key] = p_value
             except Exception as e:
                  console.print(f"[bold red]Error parsing --param arguments:[/bold red] Expected groups of MODEL KEY VALUE. {e}")
                  raise typer.Exit(code=1)


        # Handle API key
        api_key = config_manager.load_api_key()
        if api_key:
            masked_key = f"{api_key[:8]}...{api_key[-4:]}" if len(api_key) > 12 else "***"
            console.print(f"[green]Using existing API key: {masked_key}[/green]")
            run_config.api_key = api_key
            
        if set_api_key or not api_key:
            if set_api_key:
                console.print("[yellow]--set-api-key flag used. Will prompt for API key.[/yellow]")
            elif not api_key:
                console.print("[yellow]No API key found. Will prompt for API key.[/yellow]")
                
            # Instead of inline prompting, suggest using the dedicated command
            console.print("[cyan]For a better API key setup experience, use the dedicated command:[/cyan]")
            console.print("   [bold]np set-key[/bold]")
            
            if not yes:  # If not using -y/--yes flag
                proceed = typer.confirm("Continue with inline API key setup?", default=True)
                if not proceed:
                    console.print("Run 'np set-key' and then try again.")
                    raise typer.Exit(code=0)
            
            # Import here to avoid circular imports
            import getpass
            try:
                new_api_key = getpass.getpass("Enter your OpenRouter API Key: ")
            except Exception:
                new_api_key = input("Enter your OpenRouter API Key: ")
                
            if new_api_key:
                if not new_api_key.startswith("sk-or-"):
                    console.print("[yellow]Warning: Key doesn't start with 'sk-or-'[/yellow]")
                    if not typer.confirm("Continue anyway?", default=False):
                        console.print("Operation cancelled.")
                        raise typer.Exit(code=0)
                
                # Save the key
                masked_key = f"{new_api_key[:8]}...{new_api_key[-4:]}" if len(new_api_key) > 12 else "***"
                if config_manager.set_global_api_key(new_api_key):
                    console.print(f"[green]API key has been saved globally: {masked_key}[/green]")
                    
                    # Verify by loading back
                    time.sleep(0.2)  # Give filesystem a moment
                    loaded_key = config_manager.load_api_key()
                    if loaded_key and loaded_key == new_api_key:
                        console.print(f"[green]✓ API key verified: Successfully loaded the saved key[/green]")
                        run_config.api_key = loaded_key
                    else:
                        console.print("[yellow]Warning: Could not verify the saved key. Using for current run only.[/yellow]")
                        run_config.api_key = new_api_key
                else:
                    console.print(f"[yellow]Failed to save API key globally. Using for current run only: {masked_key}[/yellow]")
                    run_config.api_key = new_api_key
            else:
                console.print("[red]No API key provided. Cannot continue.[/red]")
                raise typer.Exit(code=1)


        # Display summary if not skipping confirmation
        if not yes:
            # (Code similar to _confirm_and_proceed in interactive.py to display summary)
            # ... display summary table ...
            confirmed = typer.confirm("Proceed with this configuration?")
            if not confirmed:
                console.print("Operation cancelled.")
                raise typer.Exit()

    # --- Instantiate Core Components ---
    # (Do this *after* determining mode and getting config)
    # Ensure correct instantiation order and arguments for non-interactive 'run' command as well
    output_builder = OutputBuilder(project_root, console) # project_root is Path.cwd() here
    git_handler = GitHandler(project_root, config_manager, output_builder, console)
    # LLMApi will be instantiated inside CoreProcessor.run()

    # --- Run Core Processing ---
    processor = CoreProcessor(
        config=run_config,
        config_manager=config_manager,
        output_builder=output_builder,
        git_handler=git_handler,
        # llm_api removed
        console=console
    )

    # Need to set the correct task_dir_path on llm_api before calling process_llms
    # This happens inside core_processor.run() after output_builder creates the task directory.
    # task_dir_path is initialized to Path(".") here and updated in CoreProcessor.run()

    try:
        processor.run()
    except Exception as e:
        console.print_exception(show_locals=False)
        console.print(f"[bold red]An unexpected error occurred during processing: {e}[/bold red]")
        raise typer.Exit(code=1)


@app.command()
def set_key(
    api_key: Optional[str] = typer.Argument(None, help="Your OpenRouter API key. If not provided, will prompt for it."),
    force: bool = typer.Option(False, "--force", "-f", help="Force overwrite of existing key.")
) -> None:
    """
    Set your OpenRouter API key globally.
    The key will be stored in the user's global config directory and used for all nerd-prompt projects.
    """
    import appdirs
    import getpass
    from rich.prompt import Confirm
    import toml

    console.print(Panel("OpenRouter API Key Setup", title="nerd-prompt", expand=False, style="blue"))
    
    # Check for global config directory
    global_config_dir = Path(appdirs.user_config_dir(GLOBAL_CONFIG_DIR_NAME))
    console.print(f"Global config directory: [cyan]{global_config_dir}[/cyan]")
    
    # Test if we can write to the global config directory
    write_access = check_directory_access(global_config_dir, console)
    if not write_access:
        console.print("[yellow]Warning: Cannot write to global config directory[/yellow]")
        if not Confirm.ask("Continue anyway?", default=True):
            return
    
    # Get API key from command line or prompt
    if not api_key:
        try:
            api_key = getpass.getpass("Enter your OpenRouter API key: ")
        except ImportError:
            api_key = input("Enter your OpenRouter API key: ")
    
    if not api_key:
        console.print("[red]No API key provided. Exiting.[/red]")
        return
    
    if not api_key.startswith("sk-or-"):
        console.print("[yellow]Warning: API key doesn't start with 'sk-or-'[/yellow]")
        if not Confirm.ask("Continue anyway?", default=False):
            return
    
    # Check if key exists and confirm overwrite if it does
    config_manager = ConfigManager(Path.cwd(), console)
    existing_key = config_manager.load_api_key()
    
    if existing_key and not force:
        masked_existing = f"{existing_key[:8]}...{existing_key[-4:]}" if len(existing_key) > 12 else "***"
        console.print(f"[yellow]An API key is already set: [bold]{masked_existing}[/bold][/yellow]")
        if not Confirm.ask("Overwrite existing API key?", default=False):
            return
    
    # Save the API key
    success = config_manager.set_global_api_key(api_key)
    
    if success:
        masked_key = f"{api_key[:8]}...{api_key[-4:]}" if len(api_key) > 12 else "***"
        console.print(f"[green]API key has been saved: [bold]{masked_key}[/bold][/green]")
        
        # Check file permissions
        try:
            for path in [global_config_dir, config_manager.global_config_path]:
                if path.exists():
                    mode = path.stat().st_mode
                    perms = stat.filemode(mode)
                    console.print(f"[dim]Permissions for {path}: {perms}[/dim]")
        except Exception as e:
            console.print(f"[yellow]Could not check file permissions: {e}[/yellow]")
        
        # Verify key storage in global config
        console.print("\n[bold]Verifying API key storage:[/bold]")
        verify_success = verify_key_storage(api_key, config_manager, console)
        
        # Verify by loading the key back through ConfigManager
        time.sleep(0.2)  # Give filesystem a moment
        loaded_key = config_manager.load_api_key()
        if loaded_key and loaded_key == api_key:
            console.print(f"[green]✓ API key verified: Successfully loaded the saved key [bold]{masked_key}[/bold][/green]")
        else:
            console.print("[red]⚠️ Warning: Could not verify the saved key[/red]")
            console.print("[yellow]Running debug to diagnose the issue:[/yellow]")
            config_manager.debug_api_key(verbose=True)
        
        if verify_success:
            console.print("\n[green bold]✓ API key successfully stored globally[/green bold]")
            console.print("[dim]You can now use nerd-prompt without needing to re-enter your API key.[/dim]")
            console.print("[dim]Best practice: API keys are stored in the user's global config directory, separate from any project files.[/dim]")
        else:
            console.print("\n[yellow]⚠️ There were some issues with API key storage.[/yellow]")
    else:
        console.print("[red]Failed to save API key. See error messages above for details.[/red]")
        console.print("[yellow]Running debug to diagnose the issue:[/yellow]")
        config_manager.debug_api_key(verbose=True)


@app.command()
def debug_api():
    """
    Debug API key storage and retrieval.
    Helps diagnose issues with OpenRouter API key persistence.
    """
    console.print(Panel("API Key Diagnostics", title="nerd-prompt", expand=False, style="blue"))
    
    project_root = Path.cwd()
    config_manager = ConfigManager(project_root, console)
    
    console.print("\n[bold]API Key Storage Diagnostics:[/bold]")
    config_manager.debug_api_key()
    
    console.print("\n[bold]Global Config Information:[/bold]")
    console.print(f"Global config directory: [cyan]{config_manager.global_config_dir}[/cyan]")
    console.print(f"Global config file: [cyan]{config_manager.global_config_path}[/cyan]")
    
    console.print("\n[bold]API Key Status:[/bold]")
    api_key = config_manager.load_api_key()
    if api_key:
        masked_key = f"{api_key[:8]}...{api_key[-4:]}" if len(api_key) > 12 else "***"
        console.print(f"[green]✓ API key is available for use: {masked_key}[/green]")
    else:
        console.print("[red]✗ No API key available[/red]")
        console.print("\n[bold]Recommended Actions:[/bold]")
        console.print("Run: [cyan]np set-key[/cyan] to set a global API key")
        console.print("or add [cyan]OPENROUTER_API_KEY=sk-or-your-key[/cyan] to your environment variables")


# This allows running 'python -m np ...'
if __name__ == "__main__":
    app() 