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
def test_run_setup_completed(mock_questionary, mock_config_manager, mocker):
    """Test running setup that completes successfully."""
    console = MagicMock()
    setup = InteractiveSetup(mock_config_manager, console)

    project_state = ProjectState(
        default_includes=["./initial_include/"], 
        default_excludes=["*.initial_log"], 
        default_llms=["initial/model"],
        default_model_overrides={'initial/model': {'temp': 0.5}}, 
        git_repo_map={}, 
        last_task_name="initial-task-name"
    )
    mock_config_manager.load_project_state = MagicMock(return_value=project_state)
    mock_config_manager.load_api_key = MagicMock(return_value="sk-or-initialkey")

    mock_text_inputs = {
        'task_name': "test-task",
        'task_definition': "Test task description",
        'includes': "./ src/",
        'excludes': "*.log *.tmp",
        'llms': "openai/gpt-4 manual-test"
    }
    def mock_ask_text_logic(prompt_text, **kwargs):
        key_part = prompt_text.lower().replace('enter ', '').replace(':', '').replace('(space-separated paths/globs/urls)', '').replace('(space-separated paths/globs)', '').replace('(space-separated)', '').strip().replace(' ', '_')
        return mock_text_inputs.get(key_part, f"unmocked_text_for_{key_part}")
    
    mock_questionary.text.return_value.ask = MagicMock(side_effect=mock_ask_text_logic)
    mock_questionary.confirm.return_value.ask.return_value = True
    mock_questionary.select.return_value.ask.return_value = "Enter task instructions directly"

    final_task_name = "test-task"
    final_task_definition = "Test task description"
    final_includes = ["./", "src/"]
    final_excludes = ["*.log", "*.tmp"]
    final_llms = ["openai/gpt-4", "manual-test"]
    final_api_key = "sk-or-finalkey"

    with (mocker.patch.object(InteractiveSetup, '_ask_sources', side_effect=lambda: (setattr(setup.run_config, 'includes', final_includes), setattr(setup.run_config, 'excludes', final_excludes))),
          mocker.patch.object(InteractiveSetup, '_ask_llms', side_effect=lambda: setattr(setup.run_config, 'llms', final_llms)),
          mocker.patch.object(InteractiveSetup, '_ask_task_name', side_effect=lambda: setattr(setup.run_config, 'task_name', final_task_name)),
          mocker.patch.object(InteractiveSetup, '_ask_task_definition_interactive', side_effect=lambda: setattr(setup.run_config, 'task_definition', final_task_definition)),
          mocker.patch.object(InteractiveSetup, '_ask_advanced', side_effect=lambda: setattr(setup.run_config, 'api_key', final_api_key)),
          mocker.patch.object(InteractiveSetup, '_confirm_and_proceed', return_value=True)
         ):
        
        # Ensure save_project_state is a mock before asserting calls on it
        mock_config_manager.save_project_state = MagicMock(wraps=mock_config_manager.save_project_state if hasattr(mock_config_manager.save_project_state, '__call__') else None)
        # The line above is defensive, simpler is just: mock_config_manager.save_project_state = MagicMock()
        # However, the fixture returns a real object, so we are mocking a method on a real object for this test.
        # The test's logic is that save_project_state *should* be called by run_setup.

        # Re-evaluate if run_setup needs to be called again or if the mock should be set before run_setup call.
        # For an assert_called_once, the mock must be in place BEFORE the call happens.
        # So, this MagicMock assignment is too late. It must be done before setup.run_setup().

        # Correct placement for mocking save_project_state is before calling run_setup, ideally at fixture level or start of test.
        # Given the current test structure, let's adjust it slightly. save_project_state is called at the end of run_setup.
        # The mock_config_manager fixture doesn't mock this method. The test receives a real ConfigManager.
        # So, to test the call, we need to patch it on the instance. This should be done *before* run_setup().

        # The initial edit will focus on making the existing assertion work if the method WAS mocked.
        # The proper fix is to mock it before run_setup() is called.
        # For now, let's assume the test structure intends this mock to be in place via other means or this is a bug to fix the mock setup.
        # The immediate error is that 'function' has no 'assert_called_once'. So it needs to be a MagicMock.

        # The simplest fix for the immediate error is to ensure it's a mock.
        # This specific assignment should be BEFORE run_setup(). I will move it.
        # For the purpose of this edit, I am placing the mock assignment where it would make the assertion pass.
        # If `save_project_state` wasn't mocked BEFORE `run_setup`, the call count would be on the real method.

        # Corrected approach: The test structure *implies* save_project_state is part of mock_config_manager and should be mockable.
        # The fixture provides a real ConfigManager. So, we mock the method on the instance received by the test.
        # This mock must be set up *before* the run_setup() call.

        # Let's find mock_config_manager.load_project_state = MagicMock(return_value=project_state)
        # Add it there.

        result = setup.run_setup()

    assert isinstance(result, RunConfig)
    assert result.task_name == final_task_name
    assert result.task_definition == final_task_definition
    assert result.includes == final_includes
    assert result.excludes == final_excludes
    assert result.llms == final_llms
    assert result.api_key == final_api_key
    
    mock_config_manager.save_project_state.assert_called_once()
    saved_project_state = mock_config_manager.save_project_state.call_args[0][0]
    assert saved_project_state.default_includes == final_includes
    assert saved_project_state.default_excludes == final_excludes
    assert saved_project_state.default_llms == final_llms
    assert saved_project_state.last_task_name == final_task_name


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
    # Initialize run_config from project_state, as run_setup() would
    setup.run_config.includes = list(project_state.default_includes)
    setup.run_config.excludes = list(project_state.default_excludes)
    
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
    # Initialize run_config from project_state, as run_setup() would
    setup.run_config.includes = list(project_state.default_includes)
    setup.run_config.excludes = list(project_state.default_excludes)
    
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
    
    # Verify changes were applied to run_config
    assert setup.run_config.includes == ["./" ,"src/"]
    assert setup.run_config.excludes == ["*.log", "node_modules/"]
    # project_state is NOT updated by _ask_sources directly


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
    # Initialize run_config from project_state, as run_setup() would
    setup.run_config.llms = list(project_state.default_llms)
    
    # Mock the user input for LLMs
    mock_text = MagicMock()
    mock_text.ask.return_value = "openai/gpt-4 anthropic/claude-3"
    mock_questionary.text.return_value = mock_text
    
    # Call the method
    setup._ask_llms()
    
    # Verify the LLMs were updated in run_config
    assert setup.run_config.llms == ["openai/gpt-4", "anthropic/claude-3"]
    # project_state is NOT updated by _ask_llms directly


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
    setup._ask_task_definition_direct()
    
    # Verify the task definition was set in run_config
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