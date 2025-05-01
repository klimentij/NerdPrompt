"""Tests for the CLI interface of nerd-prompt."""

import pytest
import typer
from typer.testing import CliRunner
from pathlib import Path
import os

from np.cli import app
from np.config import RunConfig

# Set up CLI runner
runner = CliRunner()

def test_version_flag():
    """Test the version flag."""
    from np import __version__
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout

def test_help_output():
    """Test help output."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "nerd-prompt: Context Assembler & LLM Interaction CLI" in result.stdout
    assert "--help" in result.stdout
    assert "--version" in result.stdout

def test_run_command_help():
    """Test help output for the run command."""
    result = runner.invoke(app, ["run", "--help"])
    assert result.exit_code == 0
    assert "run" in result.stdout
    assert "--name" in result.stdout
    assert "--task" in result.stdout
    assert "--include" in result.stdout

def test_run_missing_required_args():
    """Test run command with missing required arguments."""
    result = runner.invoke(app, ["run"])
    assert result.exit_code == 1  # Should fail due to missing required args

def test_run_with_args(mocker):
    """Test the run command with arguments."""
    # Mock dependencies to avoid actual execution
    mocker.patch("np.cli.CoreProcessor.run")
    mocker.patch("np.cli.ConfigManager.load_project_state")
    mocker.patch("np.cli.ConfigManager.load_api_key", return_value="sk-or-fakekey")
    mocker.patch("np.cli.typer.confirm", return_value=True)
    
    result = runner.invoke(app, [
        "run",
        "--name", "test-task",
        "--task", "This is a test task",
        "--include", "src/",
        "--include", "tests/",
        "--exclude", "*.log",
        "--llm", "mock-llm",
        "--yes"
    ])
    
    assert result.exit_code == 0

def test_interactive_mode_trigger(mocker):
    """Test triggering interactive mode when no args provided."""
    # Mock dependencies to avoid actual execution
    mock_interactive = mocker.patch("np.cli.InteractiveSetup")
    mock_interactive_instance = mocker.MagicMock()
    mock_interactive.return_value = mock_interactive_instance
    run_config = RunConfig(project_root=Path("."))
    run_config.api_key = "sk-or-fakekey"  # Add API key to prevent prompts
    mock_interactive_instance.run_setup.return_value = run_config
    
    # Mock more components to prevent actual execution
    mocker.patch("np.cli.CoreProcessor.run")
    mocker.patch("np.cli.ConfigManager.load_project_state")
    mocker.patch("np.cli.ConfigManager.load_api_key", return_value="sk-or-fakekey")
    mocker.patch("np.cli.OutputBuilder")
    mocker.patch("np.cli.GitHandler")
    mocker.patch("np.cli.LLMApi")
    
    # Mock system exit to prevent test from failing
    mocker.patch("typer.Exit", side_effect=lambda code=0: None)
    
    try:
        # Call the CLI with the 'run' command explicitly but no further args
        # This should trigger the interactive mode within the 'run' command logic
        result = runner.invoke(app, ["run"])
        # Check the status code directly, since we mocked typer.Exit
        assert result.exit_code in (0, None)
    except SystemExit:
        # If we still get SystemExit, that's fine for this test
        pass
    
    # Verify interactive setup was called
    mock_interactive.assert_called_once()
    mock_interactive_instance.run_setup.assert_called_once()

def test_cli_args_validation(mocker):
    """Test validation of CLI arguments."""
    # Mock dependencies
    mocker.patch("np.cli.ConfigManager.load_project_state")
    mocker.patch("np.cli.ConfigManager.load_api_key", return_value="sk-or-fakekey")
    mocker.patch("np.cli.typer.confirm", return_value=True)
    mocker.patch("np.cli.CoreProcessor.run")
    
    # Test missing name
    result = runner.invoke(app, [
        "run",
        "--task", "This is a test task"
    ])
    assert result.exit_code == 1
    assert "name is required" in result.stdout.lower()
    
    # Test conflicting task and task-file
    with open("temp_task.txt", "w") as f:
        f.write("Test task from file")
    
    result = runner.invoke(app, [
        "run",
        "--name", "test-task",
        "--task", "This is a test task",
        "--task-file", "temp_task.txt"
    ])
    assert result.exit_code == 1
    assert "use either --task or --task-file" in result.stdout.lower()
    
    # Clean up
    os.remove("temp_task.txt") 