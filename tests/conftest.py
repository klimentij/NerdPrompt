import pytest
from pathlib import Path
import shutil
import os

# Define fixtures common across tests

@pytest.fixture(scope="function")
def temp_project_dir(tmp_path_factory):
    """ Creates a temporary directory simulating a project root for testing. """
    project_dir = tmp_path_factory.mktemp("test_project_")
    # Create some dummy files/dirs
    (project_dir / "src").mkdir()
    (project_dir / "src" / "main.py").write_text("print('hello')")
    (project_dir / "docs").mkdir()
    (project_dir / "docs" / "spec.md").write_text("# Specification")
    (project_dir / "README.md").write_text("Test Project")
    (project_dir / ".gitignore").write_text("*.log\n__pycache__/\n.env\nnp_output/\n.np_git_cache/\n")
    (project_dir / "src" / "module.py").write_text("# Module")
    (project_dir / "src" / "data.log").write_text("Log entry")
    (project_dir / ".env").write_text("SECRET=123")
    # Create np_output structure base
    (project_dir / "np_output").mkdir()
    (project_dir / "np_output" / "001-old-task").mkdir()
    (project_dir / "np_output" / "002-another-task").mkdir()
    (project_dir / "np_output" / "unnumbered-task").mkdir() # For testing renumbering
    (project_dir / "np_output" / "00A-bad-prefix").mkdir() # For testing renumbering


    # Change CWD to the temp dir for the duration of the test
    original_cwd = Path.cwd()
    os.chdir(project_dir)
    yield project_dir
    os.chdir(original_cwd) # Change back after test

@pytest.fixture
def mock_config_manager(temp_project_dir, mocker):
    """ Mocks the ConfigManager """
    mocker.patch('appdirs.user_config_dir', return_value=str(temp_project_dir / ".config_global"))
    from np.config import ConfigManager
    cm = ConfigManager(project_root=temp_project_dir)
    # Ensure global dir exists for tests that might save API key
    cm.global_config_dir.mkdir(parents=True, exist_ok=True)
    return cm

@pytest.fixture
def mock_output_builder(temp_project_dir, mocker):
    """ Mocks the OutputBuilder """
    from np.output_builder import OutputBuilder
    # Mock console to avoid printing during tests unless needed
    console_mock = mocker.MagicMock()
    return OutputBuilder(project_root=temp_project_dir, console=console_mock)

@pytest.fixture
def mock_git_handler(temp_project_dir, mock_config_manager, mock_output_builder, mocker):
     """ Mocks the GitHandler """
     from np.git_handler import GitHandler
     from unittest.mock import MagicMock
     
     console_mock = mocker.MagicMock()
     handler = GitHandler(temp_project_dir, mock_config_manager, mock_output_builder, console=console_mock)
     
     # Mock subprocess calls within the handler for git commands
     handler._run_git_command = mocker.MagicMock(return_value=(0, "mock output", "")) # Default success
     
     # Mock config manager's load_project_state and update_git_repo_map methods
     project_state = MagicMock()
     project_state.git_repo_map = {}
     mock_config_manager.load_project_state = mocker.MagicMock(return_value=project_state)
     mock_config_manager.update_git_repo_map = mocker.MagicMock()
     
     # Mock output_builder's get_next_folder_number method
     mock_output_builder.get_next_folder_number = mocker.MagicMock(return_value=(3, "003"))
     
     return handler

@pytest.fixture
def mock_llm_api(temp_project_dir, mock_output_builder, mocker):
     """ Mocks the LLMApi """
     from np.llm_api import LLMApi
     console_mock = mocker.MagicMock()
     # Mock the executor and live display
     mocker.patch('np.llm_api.ThreadPoolExecutor')
     mocker.patch('np.llm_api.Live')
     mocker.patch('np.llm_api.requests.post') # Mock requests directly if needed
     api = LLMApi(api_key="sk-or-mockkey", output_builder=mock_output_builder, task_dir_path=temp_project_dir / "np_output/mock_task", console=console_mock)
     return api

@pytest.fixture
def mock_core_processor(temp_project_dir, mocker, mock_config_manager, mock_output_builder, mock_git_handler, mock_llm_api):
     """ Mocks the CoreProcessor and its dependencies """
     from np.core import CoreProcessor
     from np.config import RunConfig
     console_mock = mocker.MagicMock()
     # Mock pyperclip
     mocker.patch('np.core.pyperclip.copy')

     # Create a default RunConfig
     run_config = RunConfig(project_root=temp_project_dir, task_name="test-task")

     processor = CoreProcessor(
         config=run_config,
         config_manager=mock_config_manager,
         output_builder=mock_output_builder,
         git_handler=mock_git_handler,
         llm_api=mock_llm_api,
         console=console_mock
     )
     return processor 