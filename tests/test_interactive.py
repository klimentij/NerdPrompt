"""Tests for the interactive setup functionality."""

import pytest
from pathlib import Path
import os
from unittest.mock import MagicMock, patch

from np.interactive import InteractiveSetup
from np.config import RunConfig, ProjectState


def test_interactive_setup_initialization(mock_config_manager):
    """Test initialization of interactive setup."""
    console = MagicMock()
    setup = InteractiveSetup(mock_config_manager, console)
    
    assert setup.config_manager == mock_config_manager
    assert setup.console == console


def test_run_setup_cancelled(mock_config_manager, mocker):
    """Test running setup that gets cancelled by the user."""
    console = MagicMock()
    setup = InteractiveSetup(mock_config_manager, console)
    
    # Mock questionary to simulate cancellation
    mock_questionary = mocker.patch("np.interactive.questionary")
    mock_questionary.text.return_value.ask.return_value = None  # Simulate Ctrl+C
    
    result = setup.run_setup()
    
    assert result is None


@patch("np.interactive.questionary")
def test_run_setup_completed(mock_questionary, mock_config_manager, mocker):
    """Test running setup that completes successfully."""
    console = MagicMock()
    setup = InteractiveSetup(mock_config_manager, console)
    
    # Set up mock project state
    project_state = ProjectState(
        default_includes=["./"],
        default_excludes=["*.log"],
        default_llms=["openai/gpt-4"],
        default_model_overrides={},
        git_repo_map={}
    )
    mock_config_manager.load_project_state.return_value = project_state
    mock_config_manager.load_api_key.return_value = "sk-or-testkey"
    
    # Mock all the questionary prompts
    mock_questionary.text.return_value.ask.side_effect = [
        "test-task",                    # Task name
        "Test task description",        # Task definition
        None                            # Cancel API key prompt
    ]
    mock_questionary.checkbox.return_value.ask.side_effect = [
        ["./", "src/"],                 # Sources
        ["*.log", "*.tmp"],             # Excludes
        ["openai/gpt-4", "manual-test"] # LLMs
    ]
    mock_questionary.confirm.return_value.ask.side_effect = [
        True,                           # Confirm task definition 
        True,                           # Use OpenRouter API key
        True                            # Confirm configuration
    ]
    
    # Mock parameter configuration
    setup._configure_model_params = mocker.MagicMock(return_value={})
    
    # Run setup
    result = setup.run_setup()
    
    # Check result
    assert isinstance(result, RunConfig)
    assert result.task_name == "test-task"
    assert result.task_definition == "Test task description"
    assert set(result.includes) == {"./", "src/"}
    assert set(result.excludes) == {"*.log", "*.tmp"}
    assert set(result.llms) == {"openai/gpt-4", "manual-test"}
    assert result.api_key == "sk-or-testkey"


@patch("np.interactive.questionary")
def test_configure_sources(mock_questionary, mock_config_manager):
    """Test configuring sources in interactive mode."""
    console = MagicMock()
    setup = InteractiveSetup(mock_config_manager, console)
    
    # Set up mock project state with default includes
    project_state = ProjectState(
        default_includes=["./"],
        default_excludes=[],
        default_llms=[],
        default_model_overrides={},
        git_repo_map={}
    )
    
    # Mock the checkbox prompt
    mock_questionary.checkbox.return_value.ask.return_value = ["./", "src/", "https://github.com/user/repo.git"]
    
    # Test configuring sources
    includes = setup._configure_sources(project_state)
    
    # Should return the values from the prompt
    assert includes == ["./", "src/", "https://github.com/user/repo.git"]
    
    # Check the checkbox was configured properly
    call_args = mock_questionary.checkbox.call_args[1]
    assert "sources" in call_args["message"].lower()
    assert "./" in call_args["choices"]


@patch("np.interactive.questionary")
def test_configure_excludes(mock_questionary, mock_config_manager):
    """Test configuring excludes in interactive mode."""
    console = MagicMock()
    setup = InteractiveSetup(mock_config_manager, console)
    
    # Set up mock project state with default excludes
    project_state = ProjectState(
        default_includes=[],
        default_excludes=["*.log"],
        default_llms=[],
        default_model_overrides={},
        git_repo_map={}
    )
    
    # Mock the checkbox prompt
    mock_questionary.checkbox.return_value.ask.return_value = ["*.log", "*.tmp", "node_modules/"]
    
    # Test configuring excludes
    excludes = setup._configure_excludes(project_state)
    
    # Should return the values from the prompt
    assert excludes == ["*.log", "*.tmp", "node_modules/"]
    
    # Check the checkbox was configured properly
    call_args = mock_questionary.checkbox.call_args[1]
    assert "exclude" in call_args["message"].lower()
    assert "*.log" in call_args["choices"]


@patch("np.interactive.questionary")
def test_confirm_and_proceed(mock_questionary, mock_config_manager):
    """Test the confirmation step."""
    console = MagicMock()
    setup = InteractiveSetup(mock_config_manager, console)
    
    # Create a test config
    config = RunConfig(
        project_root=Path("."),
        task_name="test-task",
        task_definition="Test task",
        includes=["./"],
        excludes=["*.log"],
        llms=["openai/gpt-4"],
        api_key="sk-or-testkey"
    )
    
    # Test with confirmation
    mock_questionary.confirm.return_value.ask.return_value = True
    assert setup._confirm_and_proceed(config) is True
    
    # Test without confirmation
    mock_questionary.confirm.return_value.ask.return_value = False
    assert setup._confirm_and_proceed(config) is False 