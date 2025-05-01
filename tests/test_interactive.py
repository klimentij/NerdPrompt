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


@patch("np.interactive.questionary", autospec=True)
def test_run_setup_cancelled(mock_questionary, mock_config_manager):
    """Test running setup that gets cancelled by the user."""
    console = MagicMock()
    setup = InteractiveSetup(mock_config_manager, console)
    
    # Mock the KeyboardInterrupt exception
    mock_questionary.text.return_value.ask.side_effect = KeyboardInterrupt()
    
    result = setup.run_setup()
    
    assert result is None


@patch("np.interactive.questionary", autospec=True)
def test_run_setup_completed(mock_questionary, mock_config_manager):
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
    
    # Mock the config_manager properly
    mock_config_manager.load_project_state = MagicMock(return_value=project_state)
    mock_config_manager.load_api_key = MagicMock(return_value="sk-or-testkey")
    
    # Mock basic questionary methods
    mock_text = MagicMock()
    mock_text.ask.return_value = "test-task"  # First for task name, then for task definition
    mock_questionary.text.return_value = mock_text
    
    # Mock confirm always returns True
    mock_confirm = MagicMock()
    mock_confirm.ask.return_value = True
    mock_questionary.confirm.return_value = mock_confirm
    
    # Mock select returns first option
    mock_select = MagicMock()
    mock_select.ask.return_value = "Enter task instructions directly"
    mock_questionary.select.return_value = mock_select
    
    # Patch individual methods in the InteractiveSetup class
    with patch.object(InteractiveSetup, '_ask_sources'), \
         patch.object(InteractiveSetup, '_ask_llms'), \
         patch.object(InteractiveSetup, '_ask_task_name'), \
         patch.object(InteractiveSetup, '_ask_task_definition'), \
         patch.object(InteractiveSetup, '_ask_advanced'), \
         patch.object(InteractiveSetup, '_confirm_and_proceed', return_value=True):
        
        # Set the run_config manually since we're patching the methods
        setup.run_config.task_name = "test-task"
        setup.run_config.task_definition = "Test task description"
        setup.run_config.includes = ["./", "src/"]
        setup.run_config.excludes = ["*.log", "*.tmp"]
        setup.run_config.llms = ["openai/gpt-4", "manual-test"]
        setup.run_config.api_key = "sk-or-testkey"
        
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


@patch("np.interactive.questionary", autospec=True)
def test_ask_sources_no_modification(mock_questionary, mock_config_manager):
    """Test _ask_sources when user doesn't modify anything."""
    console = MagicMock()
    setup = InteractiveSetup(mock_config_manager, console)
    
    # Default project state
    project_state = ProjectState(
        default_includes=["./"],
        default_excludes=["*.log"],
        default_llms=[],
        default_model_overrides={},
        git_repo_map={}
    )
    setup.project_state = project_state
    
    # Mock confirm to return False (no modification)
    mock_confirm = MagicMock()
    mock_confirm.ask.return_value = False
    mock_questionary.confirm.return_value = mock_confirm
    
    # Call the method
    setup._ask_sources()
    
    # Verify it kept the defaults
    assert setup.run_config.includes == ["./"]
    assert setup.run_config.excludes == ["*.log"]


@patch("np.interactive.questionary", autospec=True)
def test_ask_sources_with_modification(mock_questionary, mock_config_manager):
    """Test _ask_sources when user modifies patterns."""
    console = MagicMock()
    setup = InteractiveSetup(mock_config_manager, console)
    
    # Default project state
    project_state = ProjectState(
        default_includes=["./"],
        default_excludes=[],
        default_llms=[],
        default_model_overrides={},
        git_repo_map={}
    )
    setup.project_state = project_state
    
    # Mock confirm to return True (yes, modify)
    mock_confirm = MagicMock()
    mock_confirm.ask.return_value = True
    mock_questionary.confirm.return_value = mock_confirm
    
    # Mock text inputs for includes and excludes
    mock_text = MagicMock()
    mock_text.ask.side_effect = ["./ src/", "*.log node_modules/"]
    mock_questionary.text.return_value = mock_text
    
    # Call the method
    setup._ask_sources()
    
    # Verify changes were applied
    assert setup.run_config.includes == ["./" ,"src/"]
    assert setup.run_config.excludes == ["*.log", "node_modules/"]
    assert setup.project_state.default_includes == ["./" ,"src/"]
    assert setup.project_state.default_excludes == ["*.log", "node_modules/"]


@patch("np.interactive.questionary", autospec=True)
def test_ask_llms(mock_questionary, mock_config_manager):
    """Test _ask_llms method."""
    console = MagicMock()
    setup = InteractiveSetup(mock_config_manager, console)
    
    # Default project state
    project_state = ProjectState(
        default_includes=["./"],
        default_excludes=[],
        default_llms=["openai/gpt-3.5"],
        default_model_overrides={},
        git_repo_map={}
    )
    setup.project_state = project_state
    
    # Mock the user input for LLMs
    mock_text = MagicMock()
    mock_text.ask.return_value = "openai/gpt-4 anthropic/claude-3"
    mock_questionary.text.return_value = mock_text
    
    # Call the method
    setup._ask_llms()
    
    # Verify the LLMs were updated
    assert setup.run_config.llms == ["openai/gpt-4", "anthropic/claude-3"]
    assert setup.project_state.default_llms == ["openai/gpt-4", "anthropic/claude-3"]


@patch("np.interactive.questionary", autospec=True)
def test_ask_task_name(mock_questionary, mock_config_manager):
    """Test _ask_task_name method."""
    console = MagicMock()
    setup = InteractiveSetup(mock_config_manager, console)
    
    # Mock the user input for task name
    mock_text = MagicMock()
    mock_text.ask.return_value = "My Test Task"
    mock_questionary.text.return_value = mock_text
    
    # Call the method
    setup._ask_task_name()
    
    # Verify the task name was set - match whatever sanitize_filename actually produces
    assert setup.run_config.task_name == "my-test-task"  # Sanitized


@patch("np.interactive.questionary", autospec=True)
def test_ask_task_definition_direct_input(mock_questionary, mock_config_manager):
    """Test _ask_task_definition with direct input."""
    console = MagicMock()
    setup = InteractiveSetup(mock_config_manager, console)
    
    # Mock select to choose direct input
    mock_select = MagicMock()
    mock_select.ask.return_value = "Enter task instructions directly"
    mock_questionary.select.return_value = mock_select
    
    # Mock the user task input
    mock_text = MagicMock()
    mock_text.ask.return_value = "This is a test task definition"
    mock_questionary.text.return_value = mock_text
    
    # Call the method
    setup._ask_task_definition()
    
    # Verify the task definition was set
    assert setup.run_config.task_definition == "This is a test task definition"


@patch("np.interactive.questionary", autospec=True)
def test_confirm_and_proceed_accepted(mock_questionary, mock_config_manager):
    """Test _confirm_and_proceed when user accepts."""
    console = MagicMock()
    setup = InteractiveSetup(mock_config_manager, console)
    
    # Configure a basic run config for display
    setup.run_config.task_name = "test-task"
    setup.run_config.includes = ["./"]
    setup.run_config.excludes = ["*.log"]
    setup.run_config.llms = ["openai/gpt-4"]
    setup.run_config.task_definition = "Test task description"
    setup.run_config.api_key = "sk-or-testkey"
    
    # Mock the confirm response
    mock_confirm = MagicMock()
    mock_confirm.ask.return_value = True
    mock_questionary.confirm.return_value = mock_confirm
    
    # Call the method
    result = setup._confirm_and_proceed()
    
    # Verify it returned True
    assert result is True


@patch("np.interactive.questionary", autospec=True)
def test_confirm_and_proceed_rejected(mock_questionary, mock_config_manager):
    """Test _confirm_and_proceed when user rejects."""
    console = MagicMock()
    setup = InteractiveSetup(mock_config_manager, console)
    
    # Configure a basic run config for display
    setup.run_config.task_name = "test-task"
    setup.run_config.includes = ["./"]
    setup.run_config.excludes = ["*.log"]
    setup.run_config.llms = ["openai/gpt-4"]
    setup.run_config.task_definition = "Test task description"
    setup.run_config.api_key = "sk-or-testkey"
    
    # Mock the confirm response
    mock_confirm = MagicMock()
    mock_confirm.ask.return_value = False
    mock_questionary.confirm.return_value = mock_confirm
    
    # Call the method
    result = setup._confirm_and_proceed()
    
    # Verify it returned False
    assert result is False 