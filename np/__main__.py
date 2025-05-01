import sys
import typer # Import typer explicitly if needed for app definition elsewhere

# Import the app instance from cli.py
# This structure assumes 'app' is defined in cli.py using typer.Typer()
from .cli import app

# Optional: Add any pre-execution setup here if needed

# Execute the Typer app
if __name__ == "__main__":
     # Check if running without args for interactive mode clarification
     # Note: Typer itself handles the no_args_is_help=False logic in the @app.command,
     # but this check in __main__ can provide an extra layer or alternative control flow if needed.
     # For this setup, relying on the Typer command definition is cleaner.
     # is_interactive_candidate = len(sys.argv) == 1 or (len(sys.argv) == 2 and sys.argv[1] == "run") # Check if only 'np' or 'np run' was called

     app() # Run the Typer application defined in cli.py 