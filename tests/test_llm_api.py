"""Tests for the LLM API functionality."""

import pytest
import requests
from pathlib import Path
import os
import json
from unittest.mock import MagicMock, patch, AsyncMock

from np.llm_api import LLMApi


def test_is_openrouter_model():
    """Test detecting OpenRouter models."""
    # Creating an instance to test the method
    console = MagicMock()
    output_builder = MagicMock()
    task_dir = Path("test_dir")
    api = LLMApi("sk-or-fakekey", output_builder, task_dir, console)
    
    assert api._is_openrouter_model("google/gemini-pro") is True
    assert api._is_openrouter_model("anthropic/claude-3-sonnet") is True
    assert api._is_openrouter_model("openai/gpt-4") is True
    assert api._is_openrouter_model("qwen/qwen3-0.6b-04-28:free") is True
    assert api._is_openrouter_model("manual-review") is False
    assert api._is_openrouter_model("local-model") is False


@patch("np.llm_api.ThreadPoolExecutor")
@patch("np.llm_api.Live")
def test_process_llms(mock_live, mock_executor, mocker):
    """Test processing LLMs without actually making API calls."""
    # Create a mock API instance with mocked components
    console = MagicMock()
    output_builder = MagicMock()
    task_dir = Path("test_dir")
    api = LLMApi("sk-or-fakekey", output_builder, task_dir, console)
    
    # Mock the ThreadPoolExecutor context manager
    mock_executor_instance = MagicMock()
    mock_executor.return_value.__enter__.return_value = mock_executor_instance
    
    # Mock the Live context manager
    mock_live_instance = MagicMock()
    mock_live.return_value.__enter__.return_value = mock_live_instance
    
    # Test with mixed models including a free one
    llms = ["openai/gpt-4", "manual-review", "qwen/qwen3-0.6b-04-28:free"]
    prompt = "Test prompt"
    model_params = {
        "openai/gpt-4": {"temperature": 0.5},
        "qwen/qwen3-0.6b-04-28:free": {"max_tokens": 1000}
    }
    
    # Call process_llms
    api.process_llms(llms, prompt, model_params)
    
    # Check that we initialized status tracking for all models
    assert len(api._model_status) == 3
    
    # Verify that OpenRouter models were sent to executor
    assert mock_executor_instance.submit.call_count == 2
    
    # Verify manual models were marked with the right status
    assert api._model_status["manual-review"].status == "Manual Input"
    
    # Verify we used Live for status updates
    assert mock_live.called


@patch("np.llm_api.requests.post")
def test_send_request_success(mock_post, mocker):
    """Test sending a request with a successful response."""
    # Create a mock API instance
    console = MagicMock()
    output_builder = MagicMock()
    task_dir = Path("test_dir")
    api = LLMApi("sk-or-fakekey", output_builder, task_dir, console)
    
    # Setup initial status
    model_name = "openai/gpt-4"
    api._model_status = {model_name: MagicMock(status="Waiting...", name=model_name)}
    
    # Mock a successful response
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "This is a test response"}}],
        "usage": {"total_tokens": 100, "prompt_tokens": 50, "completion_tokens": 50}
    }
    mock_post.return_value = mock_response
    
    # Call the method
    api._send_request(model_name, "Test prompt", {})
    
    # Verify the request was made correctly
    mock_post.assert_called_once()
    call_args = mock_post.call_args
    assert "openai/gpt-4" in call_args[1]["json"]["model"]
    assert "Test prompt" in call_args[1]["json"]["messages"][0]["content"]
    
    # Verify status was updated
    assert api._model_status[model_name].status == "Done"
    assert api._model_status[model_name].result_content == "This is a test response"
    
    # Verify result was written to file
    output_builder.write_llm_response.assert_called_once_with(
        task_dir, model_name, "This is a test response"
    )


@patch("np.llm_api.requests.post")
def test_send_request_free_model(mock_post, mocker):
    """Test sending a request with a free model."""
    # Create a mock API instance
    console = MagicMock()
    output_builder = MagicMock()
    task_dir = Path("test_dir")
    api = LLMApi("sk-or-fakekey", output_builder, task_dir, console)
    
    # Setup initial status
    model_name = "qwen/qwen3-0.6b-04-28:free"
    api._model_status = {model_name: MagicMock(status="Waiting...", name=model_name)}
    
    # Mock a successful response
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "Response from free model"}}],
        "usage": {"total_tokens": 80, "prompt_tokens": 30, "completion_tokens": 50}
    }
    mock_post.return_value = mock_response
    
    # Call the method
    api._send_request(model_name, "Test prompt", {"max_tokens": 1000})
    
    # Verify the request was made correctly with the free model
    mock_post.assert_called_once()
    call_args = mock_post.call_args
    assert "qwen/qwen3-0.6b-04-28:free" in call_args[1]["json"]["model"]
    assert "max_tokens" in call_args[1]["json"]
    assert call_args[1]["json"]["max_tokens"] == 1000
    
    # Verify status was updated
    assert api._model_status[model_name].status == "Done"
    assert api._model_status[model_name].result_content == "Response from free model"
    
    # Verify result was written to file
    output_builder.write_llm_response.assert_called_once_with(
        task_dir, model_name, "Response from free model"
    )


@patch("np.llm_api.requests.post")
def test_send_request_error(mock_post, mocker):
    """Test handling API request errors."""
    # Create a mock API instance
    console = MagicMock()
    output_builder = MagicMock()
    task_dir = Path("test_dir")
    api = LLMApi("sk-or-fakekey", output_builder, task_dir, console)
    
    # Setup initial status
    model_name = "openai/gpt-4"
    api._model_status = {model_name: MagicMock(status="Waiting...", name=model_name)}
    
    # Mock a failed response
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = requests.HTTPError("API Error")
    mock_response.text = "Error message"
    mock_post.return_value = mock_response
    
    # Call the method
    api._send_request(model_name, "Test prompt", {})
    
    # Verify status was updated to Error
    assert api._model_status[model_name].status == "Error"
    assert "ERROR" in api._model_status[model_name].result_content
    assert api._model_status[model_name].error_message is not None
    
    # Verify error was written to file
    output_builder.write_llm_response.assert_called_once()
    assert "ERROR" in output_builder.write_llm_response.call_args[0][2]


def test_no_api_key():
    """Test processing when no API key is provided."""
    # Create an API instance with no key
    console = MagicMock()
    output_builder = MagicMock()
    task_dir = Path("test_dir")
    api = LLMApi(None, output_builder, task_dir, console)
    
    # Test with OpenRouter models
    llms = ["openai/gpt-4", "qwen/qwen3-0.6b-04-28:free"]
    prompt = "Test prompt"
    
    # Call process_llms
    api.process_llms(llms, prompt, {})
    
    # Verify all models were marked as error
    for name in llms:
        assert api._model_status[name].status == "Error"
        assert "API Key not configured" in api._model_status[name].error_message

    # Verify appropriate error messages were written
    assert output_builder.write_llm_response.call_count == 2
    for call_args in output_builder.write_llm_response.call_args_list:
        assert "API Key" in call_args[0][2]


def test_no_openrouter_models():
    """Test processing when no OpenRouter models are provided."""
    # Create a mock API instance
    console = MagicMock()
    output_builder = MagicMock()
    task_dir = Path("test_dir")
    api = LLMApi("sk-or-fakekey", output_builder, task_dir, console)
    
    # Test with only manual models
    llms = ["manual-model1", "manual-model2"]
    prompt = "Test prompt"
    
    # Call process_llms
    api.process_llms(llms, prompt, {})
    
    # Verify models were properly tracked
    for name in llms:
        assert api._model_status[name].status == "Manual Input"
    
    # Verify no API calls were made (no ThreadPoolExecutor used)
    console.print.assert_called_with(
        "[yellow]No OpenRouter models selected. Skipping API calls.[/yellow]"
    ) 