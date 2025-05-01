import pytest
from pathlib import Path
import os
import toml

from np.config import ConfigManager, ProjectState, API_KEY_ENV_VAR, GLOBAL_CONFIG_FILENAME, PROJECT_CONFIG_FILENAME

# Use the fixtures defined in conftest.py

def test_load_project_state_defaults(temp_project_dir):
    """ Test loading project state when no config file exists. """
    cm = ConfigManager(project_root=temp_project_dir)
    state = cm.load_project_state()
    assert isinstance(state, ProjectState)
    assert state.default_includes == ["./"]
    assert PROJECT_CONFIG_FILENAME in state.default_excludes # Ensure self-exclusion default
    assert state.default_llms == []
    assert state.git_repo_map == {}

def test_save_and_load_project_state(temp_project_dir):
    """ Test saving and reloading project state. """
    cm = ConfigManager(project_root=temp_project_dir)
    state = ProjectState(
        default_includes=["src/", "docs/spec.md", "https://some.repo#main"],
        default_excludes=["*.tmp", "build/"],
        default_llms=["model1", "manual/model2"],
        default_model_overrides={"model1": {"temp": 0.5}},
        git_repo_map={"https://some.repo#main": "001-some-repo"}
    )
    cm.save_project_state(state)

    assert cm.project_config_path.exists()

    loaded_state = cm.load_project_state()
    assert loaded_state.default_includes == state.default_includes
    assert loaded_state.default_excludes == state.default_excludes
    assert loaded_state.default_llms == state.default_llms
    assert loaded_state.default_model_overrides == state.default_model_overrides
    assert loaded_state.git_repo_map == state.git_repo_map

def test_update_git_repo_map(temp_project_dir):
    """ Test adding/updating the git repo map saves correctly. """
    cm = ConfigManager(project_root=temp_project_dir)
    # Initial save should create the map
    cm.update_git_repo_map("https://new.repo#dev", "003-new-repo")
    state1 = cm.load_project_state()
    assert state1.git_repo_map == {"https://new.repo#dev": "003-new-repo"}

    # Update existing
    cm.update_git_repo_map("https://new.repo#dev", "004-new-repo-renamed") # Simulate renumbering
    state2 = cm.load_project_state()
    assert state2.git_repo_map == {"https://new.repo#dev": "004-new-repo-renamed"}

    # Add another
    cm.update_git_repo_map("https://another.repo#main", "005-another")
    state3 = cm.load_project_state()
    assert state3.git_repo_map == {
        "https://new.repo#dev": "004-new-repo-renamed",
        "https://another.repo#main": "005-another"
    }

def test_load_api_key_env_var(mocker, temp_project_dir):
    """ Test loading API key from environment variable. """
    mock_api_key = "sk-or-envkey123"
    mocker.patch.dict(os.environ, {API_KEY_ENV_VAR: mock_api_key})
    # Mock appdirs to avoid actual user config dir access
    mocker.patch('appdirs.user_config_dir', return_value=str(temp_project_dir / ".config_global"))

    cm = ConfigManager(project_root=temp_project_dir)
    assert cm.load_api_key() == mock_api_key

def test_load_api_key_global_config(mock_config_manager):
    """ Test loading API key from the global config file. """
    cm = mock_config_manager
    mock_api_key = "sk-or-globalkey456"
    # Create a dummy global config file
    global_settings = {"settings": {API_KEY_ENV_VAR: mock_api_key}}
    with open(cm.global_config_path, "w") as f:
        toml.dump(global_settings, f)

    # Ensure ENV var is not set
    if API_KEY_ENV_VAR in os.environ:
        del os.environ[API_KEY_ENV_VAR]

    assert cm.load_api_key() == mock_api_key

def test_load_api_key_precedence(mocker, mock_config_manager):
    """ Test that ENV var takes precedence over global config file. """
    cm = mock_config_manager
    env_key = "sk-or-envpriority"
    global_key = "sk-or-globalshouldbeignored"

    mocker.patch.dict(os.environ, {API_KEY_ENV_VAR: env_key})
    global_settings = {"settings": {API_KEY_ENV_VAR: global_key}}
    with open(cm.global_config_path, "w") as f:
        toml.dump(global_settings, f)

    assert cm.load_api_key() == env_key

def test_save_api_key(mock_config_manager):
    """ Test saving API key to the global config file. """
    cm = mock_config_manager
    api_key_to_save = "sk-or-saveme789"

    assert cm.save_api_key(api_key_to_save) is True
    assert cm.global_config_path.exists()

    # Verify content
    with open(cm.global_config_path, "r") as f:
        data = toml.load(f)
    assert data == {"settings": {API_KEY_ENV_VAR: api_key_to_save}}

    # Verify loading it back
    assert cm.load_api_key() == api_key_to_save

def test_load_gitignore(temp_project_dir):
    """ Test loading .gitignore patterns. """
    cm = ConfigManager(project_root=temp_project_dir)
    patterns = cm.load_gitignore_patterns()
    assert "*.log" in patterns
    assert "__pycache__/" in patterns
    assert ".env" in patterns
    assert "np_output/" in patterns
    assert "# Specification" not in patterns # Ignore comments

def test_load_gitignore_not_found(temp_project_dir):
    """ Test loading .gitignore when the file doesn't exist. """
    gitignore_path = temp_project_dir / ".gitignore"
    gitignore_path.unlink()
    cm = ConfigManager(project_root=temp_project_dir)
    patterns = cm.load_gitignore_patterns()
    assert patterns == [] 