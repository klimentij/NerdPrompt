"""Integration tests for the nerd-prompt CLI."""

import pytest
import os
import shutil
from pathlib import Path
import subprocess
from unittest.mock import patch

@pytest.fixture
def setup_test_project(tmp_path):
    """Create a temporary project for testing the CLI."""
    project_dir = tmp_path / "test_project"
    project_dir.mkdir()
    
    # Add some test files
    (project_dir / "file1.py").write_text("print('hello')")
    (project_dir / "file2.md").write_text("# Test Document")
    (project_dir / "src").mkdir()
    (project_dir / "src" / "main.py").write_text("def main():\n    return 'test'")
    
    # Add a .gitignore
    (project_dir / ".gitignore").write_text("*.log\n__pycache__/\n")
    
    # Add a task file
    task_file = project_dir / "task.md"
    task_file.write_text("This is a test task that does something.")
    
    # Change to the test directory
    original_dir = os.getcwd()
    os.chdir(project_dir)
    
    yield project_dir
    
    # Cleanup
    os.chdir(original_dir)
    shutil.rmtree(project_dir)

def test_cli_version():
    """Test that the CLI returns the correct version."""
    from np import __version__
    
    result = subprocess.run(["python", "-m", "np", "--version"], 
                           capture_output=True, text=True)
    
    assert result.returncode == 0
    assert __version__ in result.stdout

def test_run_with_noninteractive_args(setup_test_project):
    """Test running the CLI with non-interactive arguments."""
    # This test uses subprocess to call the actual CLI with arguments
    result = subprocess.run(
        [
            "python", "-m", "np", "run",
            "--name", "test-task",
            "--task", "This is a test task",
            "--include", "file1.py",
            "--llm", "manual-test",
            "-y"  # Skip confirmation
        ],
        capture_output=True,
        text=True
    )
    
    assert result.returncode == 0
    
    # Check that the output directory was created
    output_dir = setup_test_project / "np_output"
    assert output_dir.exists()
    
    # Check that the task directory was created (numbered)
    task_dirs = list(output_dir.glob("*-test-task"))
    assert len(task_dirs) == 1
    
    task_dir = task_dirs[0]
    
    # Check that the task file was created
    task_file = task_dir / "_task.md"
    assert task_file.exists()
    task_content = task_file.read_text()
    assert "This is a test task" in task_content
    assert "file1.py" in task_content
    
    # Check that the LLM output file was created
    llm_file = task_dir / "manual-test.md"
    assert llm_file.exists()
    
@patch('questionary.text')
@patch('questionary.checkbox')
@patch('questionary.confirm')
def test_interactive_mode(mock_confirm, mock_checkbox, mock_text, setup_test_project):
    """Test running the CLI in interactive mode."""
    # Skip running this test in CI environments
    if os.environ.get("CI"):
        pytest.skip("Skipping interactive test in CI environment")
    
    # Mock interactive inputs
    mock_text.return_value.ask.side_effect = [
        "test-interactive",  # Task name
        "This is an interactive test task",  # Task definition
    ]
    
    mock_checkbox.return_value.ask.side_effect = [
        ["file1.py"],  # Includes
        ["*.log"],     # Excludes
        ["manual-test"]  # LLMs
    ]
    
    mock_confirm.return_value.ask.return_value = True  # Confirm
    
    # Run the CLI in interactive mode
    with patch('sys.argv', ['np']):
        try:
            subprocess.run(
                ["python", "-m", "np"],
                capture_output=True,
                text=True,
                timeout=10  # Timeout after 10 seconds
            )
        except subprocess.TimeoutExpired:
            # This is expected since interactive mode would wait for input
            pass
    
    # Check that the output directory was created
    output_dir = setup_test_project / "np_output"
    assert output_dir.exists() 