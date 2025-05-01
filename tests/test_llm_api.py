"""Tests for the LLM API functionality."""

import pytest
import requests
from pathlib import Path
import os
import json
from unittest.mock import MagicMock, patch

from np.llm_api import LLMApi


def test_is_openrouter_model():
    """Test detecting OpenRouter models."""
    assert LLMApi.is_openrouter_model("google/gemini-pro") is True
    assert LLMApi.is_openrouter_model("anthropic/claude-3-sonnet") is True
    assert LLMApi.is_openrouter_model("openai/gpt-4") is True
    assert LLMApi.is_openrouter_model("manual-review") is False
    assert LLMApi.is_openrouter_model("local-model") is False

def test_process_llms(mock_output_builder, mocker):
    """Test processing LLMs with a mock request."""
    # Create a mock API instance
    console = MagicMock()
    task_dir = Path("test_dir")
    api = LLMApi("sk-or-fakekey", mock_output_builder, task_dir, console)
    
    # Setup mock
    api._process_manual_llm = mocker.MagicMock()
    api._process_openrouter_llm = mocker.MagicMock()
    mocker.patch("np.llm_api.LLMApi.is_openrouter_model", side_effect=[True, False, True])
    
    # Test with mixed models
    llms = ["openai/gpt-4", "manual-review", "anthropic/claude-3"]
    prompt = "Test prompt"
    model_params = {
        "openai/gpt-4": {"temperature": 0.5},
        "anthropic/claude-3": {"max_tokens": 2000}
    }
    
    api.process_llms(llms, prompt, model_params)
    
    # Should have called _process_openrouter_llm twice and _process_manual_llm once
    assert api._process_openrouter_llm.call_count == 2
    assert api._process_manual_llm.call_count == 1

def test_process_manual_llm(mock_output_builder, mocker):
    """Test processing manual LLM (creating empty file)."""
    # Create a mock API instance
    console = MagicMock()
    task_dir = Path("test_dir")
    api = LLMApi("sk-or-fakekey", mock_output_builder, task_dir, console)
    
    # Setup output builder mock
    output_file = Path("test_dir/manual-model.md")
    mock_output_builder.create_llm_output_file.return_value = output_file
    
    # Mock file.write_text
    mocker.patch.object(Path, "write_text")
    
    # Test processing manual LLM
    api._process_manual_llm("manual-model", "Test prompt")
    
    # Should have created the file
    mock_output_builder.create_llm_output_file.assert_called_once_with(task_dir, "manual-model")
    
    # Should have written placeholder text
    Path.write_text.assert_called_once()
    # Verify that it contains empty placeholder
    call_args = Path.write_text.call_args[0][0]
    assert "PLACEHOLDER" in call_args
    assert "Test prompt" not in call_args  # Prompt shouldn't be in output file

@pytest.mark.asyncio
async def test_process_openrouter_llm(mock_output_builder, mocker):
    """Test processing OpenRouter LLM with a mock response."""
    # Create a mock API instance
    console = MagicMock()
    task_dir = Path("test_dir")
    api = LLMApi("sk-or-fakekey", mock_output_builder, task_dir, console)
    
    # Setup output builder mock
    output_file = Path("test_dir/openai-gpt4.md")
    mock_output_builder.create_llm_output_file.return_value = output_file
    
    # Mock the request
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "This is a test response"}}]
    }
    mocker.patch("requests.post", return_value=mock_response)
    
    # Mock file.write_text
    mocker.patch.object(Path, "write_text")
    
    # Test with successful request
    model_name = "openai/gpt-4"
    prompt = "Test prompt"
    model_overrides = {"temperature": 0.7}
    
    await api._process_openrouter_llm(model_name, prompt, model_overrides)
    
    # Verify request was made
    requests_post_args = requests.post.call_args
    assert "https://openrouter.ai/api/v1/chat/completions" in requests_post_args[0][0]
    assert "sk-or-fakekey" in requests_post_args[1]["headers"]["Authorization"]
    assert model_name in requests_post_args[1]["json"]["model"]
    assert "temperature" in requests_post_args[1]["json"]
    assert requests_post_args[1]["json"]["temperature"] == 0.7
    
    # Verify file was written
    Path.write_text.assert_called_once()
    call_args = Path.write_text.call_args[0][0]
    assert "This is a test response" in call_args
    
    # Test error case
    mock_response.status_code = 400
    mock_response.json.return_value = {"error": {"message": "Test error"}}
    mock_response.text = json.dumps({"error": {"message": "Test error"}})
    Path.write_text.reset_mock()
    
    await api._process_openrouter_llm(model_name, prompt, model_overrides)
    
    # Verify error was written to file
    Path.write_text.assert_called_once()
    call_args = Path.write_text.call_args[0][0]
    assert "ERROR" in call_args
    assert "Test error" in call_args 