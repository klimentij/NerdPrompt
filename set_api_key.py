#!/usr/bin/env python3
"""
Simple script to set the OpenRouter API key globally.
Run this script and enter your API key to save it globally for all projects.
"""

import sys
import os
import time
import toml
from pathlib import Path
import stat
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm

# Add parent directory to sys.path if running from project directory
current_dir = Path(__file__).parent
if (current_dir / "np").exists():
    sys.path.insert(0, str(current_dir))

try:
    from np.config import ConfigManager, GLOBAL_CONFIG_DIR_NAME, API_KEY_ENV_VAR
    import appdirs
except ImportError:
    print("Error: Could not import ConfigManager from np.config")
    print("Make sure you're running this script from the nerd-prompt directory or have it installed.")
    sys.exit(1)

def test_directory_access(path: Path, console: Console) -> bool:
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

def main():
    console = Console()
    console.print(Panel("OpenRouter API Key Setup", title="nerd-prompt", expand=False, style="blue"))
    
    # Check for global config directory
    global_config_dir = Path(appdirs.user_config_dir(GLOBAL_CONFIG_DIR_NAME))
    console.print(f"Global config directory: [cyan]{global_config_dir}[/cyan]")
    
    # Test if we can write to the global config directory
    write_access = test_directory_access(global_config_dir, console)
    if not write_access:
        console.print("[yellow]Warning: Cannot write to global config directory[/yellow]")
        if not Confirm.ask("Continue anyway?", default=True):
            return
    
    # Get API key from command line or prompt
    api_key = None
    if len(sys.argv) > 1:
        api_key = sys.argv[1]
    
    if not api_key:
        try:
            import getpass
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
    
    # Save the API key
    config_manager = ConfigManager(Path.cwd(), console)
    success = config_manager.set_global_api_key(api_key)
    
    if success:
        console.print("[green]API key has been saved.[/green]")
        
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
            console.print("[green]✓ API key verified: Successfully loaded the saved key[/green]")
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

if __name__ == "__main__":
    main() 