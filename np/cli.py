import sys
from pathlib import Path
from typing import List, Optional, Tuple, Annotated

import typer
from rich.console import Console

from .config import ConfigManager, RunConfig, ProjectState, DEFAULT_EXCLUDES
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
    no_args_is_help=False, # Allow running with no args for interactive mode
)

console = Console()

def version_callback(value: bool):
    if value:
        console.print(f"nerd-prompt version: {__version__}")
        raise typer.Exit()

@app.callback()
def main_callback(
    version: Annotated[Optional[bool], typer.Option("--version", "-V", callback=version_callback, is_eager=True, help="Show version and exit.")] = None,
):
    """ Nerd Prompt CLI entry point """
    pass


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


@app.command(no_args_is_help=False) # Allow calling without subcommands if we want 'np' alone for interactive
def run(
    # --- Arguments mirroring interactive steps ---
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
        if set_api_key and not api_key:
             console.print("[yellow]--set-api-key used, but no key found. Attempting to prompt...[/yellow]")
             # Fallback to prompt if forced and no key exists
             set_api_key = True # Ensure prompt happens

        if set_api_key:
            import questionary # Import only if needed
            from .interactive import custom_style # Import style
            new_api_key = questionary.password(
                 "Enter your OpenRouter API Key:",
                 validate=lambda k: True if k and k.startswith("sk-or-") else "Key should start with 'sk-or-'",
                 style=custom_style
            ).ask()
            if new_api_key:
                if config_manager.save_api_key(new_api_key):
                     console.print("[green]API Key saved globally.[/green]")
                     run_config.api_key = new_api_key
                else:
                     console.print("[red]Failed to save API key. Exiting.[/red]")
                     raise typer.Exit(code=1)
            else:
                console.print("[red]API key entry required (--set-api-key) but cancelled. Exiting.[/red]")
                raise typer.Exit(code=1)
        else:
             run_config.api_key = api_key # Use loaded key


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
    output_builder = OutputBuilder(project_root, console)
    git_handler = GitHandler(project_root, config_manager, output_builder, console)
    llm_api = LLMApi(run_config.api_key, output_builder, Path("."), console) # Task dir path set later

    # --- Run Core Processing ---
    core_processor = CoreProcessor(
        config=run_config,
        config_manager=config_manager,
        output_builder=output_builder,
        git_handler=git_handler,
        llm_api=llm_api, # Pass the instance
        console=console
    )

    # Need to set the correct task_dir_path on llm_api before calling process_llms
    # This happens inside core_processor.run() after output_builder creates the dir.
    # We might need to refactor how llm_api gets the path or pass it during the call.
    # Let's assume core_processor handles this coordination.
    # A cleaner way might be for llm_api.process_llms to accept task_dir_path as an argument.

    try:
        core_processor.run()
    except Exception as e:
        console.print_exception(show_locals=False)
        console.print(f"[bold red]An unexpected error occurred during processing: {e}[/bold red]")
        raise typer.Exit(code=1)


# This allows running 'python -m np ...'
if __name__ == "__main__":
    app() 