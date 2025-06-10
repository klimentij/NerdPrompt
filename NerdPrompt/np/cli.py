@app.command(
    "run",
    help="Runs nerd-prompt. If no arguments are given, enters interactive setup mode. Otherwise, uses provided arguments for a non-interactive run.",
    no_args_is_help=False,  # Important for allowing `np run` to trigger interactive mode
)
def run(
    name: str = typer.Option(None, "--name", "-n", help="Short name for the task (e.g., 'refactor-auth')."),
    task: str = typer.Option(None, "--task", "-t", help="Task definition text."),
    task_file: Path = typer.Option(None, "--task-file", "-f", help="Path to a file containing the task definition."),
    include: list[str] = typer.Option(None, "--include", "-i", help="Path/glob/URL to include. Can be repeated."),
    exclude: list[str] = typer.Option(None, "--exclude", "-e", help="Path/glob to exclude. Can be repeated."),
    llms: list[str] = typer.Option(None, "--llm", "-l", help="Target LLM names (e.g., 'google/gemini-pro'). Can be repeated."),
    params: list[str] = typer.Option(
        None,
        "--param",
        "-p",
        help="Override OpenRouter params (e.g., '-p model key value'). Can be repeated.",
        callback=validate_params,
    ),
    set_api_key: bool = typer.Option(
        False, "--set-api-key", help="Force prompt to update the OpenRouter API key.", is_flag=True
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip final confirmation prompt.", is_flag=True),
    from_config: bool = typer.Option(
        False,
        "--from-config",
        "-c",
        help="Run non-interactively, using only settings from .npconfig.toml.",
        is_flag=True,
    ),
):
    print("--- EDITABLE INSTALL TEST: cli.py loaded AND IS WORKING ---")
    """
    Runs the main nerd-prompt application.

    This function serves as the primary entry point for the `run` command.
    It determines whether to run in interactive or non-interactive mode based on
    the provided CLI arguments.
    """
    interactive_mode = not any([name, task, task_file, from_config])

    if interactive_mode:
        # No core arguments provided, run interactive setup
        setup = InteractiveSetup()
        if not setup.run():
            # User cancelled setup
            raise typer.Exit()
        config_manager = ConfigManager()
        run_config = config_manager.get_run_config_from_state()
    else:
        # Non-interactive mode
        # ... (rest of the function)
        run_config = RunConfig(
            name=name,
            task=task_text,
            includes=include if include else None,
            excludes=exclude if exclude else None,
            llms=llms if llms else None,
            model_overrides=model_overrides if model_overrides else None,
            confirm=not yes,
            from_config=from_config,
        )

    # Initialize and run the core processor
    try:
        processor = CoreProcessor(run_config, set_api_key)
        processor.run()
    except Exception as e:
        console.print(f"[bold red]An unexpected error occurred: {e}[/bold red]")
        raise typer.Exit(code=1) 