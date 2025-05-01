import json
import time
import threading
from concurrent.futures import ThreadPoolExecutor, Future
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime
from pathlib import Path

import requests
from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.spinner import Spinner

from .output_builder import OutputBuilder

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
REQUEST_TIMEOUT_SECONDS = 120 # Timeout for the HTTP request itself
DEFAULT_TEMPERATURE = 1.0
DEFAULT_API_TIMEOUT = 60 # Timeout parameter sent *to* OpenRouter

# Structure to hold results/status for each model
class ModelStatus:
    def __init__(self, name: str, is_openrouter: bool):
        self.name = name
        self.is_openrouter = is_openrouter
        self.status = "Waiting..."
        self.result_content: Optional[str] = None
        self.error_message: Optional[str] = None
        self.cost: float = 0.0
        self.future: Optional[Future] = None
        self.start_time = time.monotonic()
        self.end_time: Optional[float] = None

    def get_display(self) -> str:
        elapsed = f" ({time.monotonic() - self.start_time:.1f}s)" if self.status not in ["Done", "Error", "Manual Input"] else ""
        if self.status == "Done":
             return f"[green]✅ {self.name}[/green]{elapsed}"
        elif self.status == "Error":
             return f"[red]❌ {self.name}[/red]{elapsed}"
        elif self.status == "Manual Input":
             return f"[yellow]✏️ {self.name}[/yellow] Pending manual input"
        else:
             spinner = Spinner("dots", text="")
             return f"[blue]{spinner.render(time.time())} {self.name}[/blue] {self.status}{elapsed}"


class LLMApi:
    """ Handles interaction with the OpenRouter API. """
    def __init__(
        self,
        api_key: Optional[str],
        output_builder: OutputBuilder,
        task_dir_path: Path,
        console: Optional[Console] = None,
        max_workers: int = 5,
    ):
        self.api_key = api_key
        self.output_builder = output_builder
        self.task_dir_path = task_dir_path
        self.console = console or Console()
        self.max_workers = max_workers
        self._model_status: Dict[str, ModelStatus] = {}
        self._lock = threading.Lock() # To safely update shared status

    def _is_openrouter_model(self, model_name: str) -> bool:
        """ Basic heuristic to identify OpenRouter models. """
        # A more robust check might involve fetching available models from OpenRouter
        # or using a more specific naming convention.
        return '/' in model_name

    def _send_request(self, model_name: str, merged_prompt: str, overrides: Dict[str, Any]) -> None:
        """ Sends a single request to OpenRouter. Runs in a thread. """
        start_time = time.monotonic()
        status_key = model_name # Use original name as key

        if not self.api_key:
            with self._lock:
                 self._model_status[status_key].status = "Error"
                 self._model_status[status_key].error_message = "API Key not configured."
                 self._model_status[status_key].end_time = time.monotonic()
            return

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/yourusername/nerd-prompt", # Optional but good practice
            "X-Title": "nerd-prompt", # Optional
        }

        payload = {
            "model": model_name,
            "messages": [{"role": "user", "content": merged_prompt}],
            "temperature": overrides.get("temperature", DEFAULT_TEMPERATURE),
            "timeout": overrides.get("timeout", DEFAULT_API_TIMEOUT),
            # Add other overrides dynamically
            **{k: v for k, v in overrides.items() if k not in ["temperature", "timeout"]}
        }

        response_content: Optional[str] = None
        error_msg: Optional[str] = None
        cost: float = 0.0

        try:
            with self._lock:
                 self._model_status[status_key].status = "Sending..."
            response = requests.post(
                OPENROUTER_API_URL,
                headers=headers,
                json=payload,
                timeout=REQUEST_TIMEOUT_SECONDS
            )
            response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)

            # --- Process Success ---
            data = response.json()
            response_content = data.get("choices", [{}])[0].get("message", {}).get("content")
            if not response_content:
                 error_msg = "Error: Received empty content from API."

            # --- Extract Cost (Adjust based on actual OpenRouter response structure) ---
            # Example: Check 'usage' object if present
            usage = data.get("usage")
            if isinstance(usage, dict) and "total_tokens" in usage:
                # OpenRouter cost varies; this is a placeholder.
                # A more accurate approach might need model-specific pricing lookup.
                # For now, we'll just indicate tokens processed if available.
                 total_tokens = usage.get('total_tokens', 0)
                 prompt_tokens = usage.get('prompt_tokens', 0)
                 completion_tokens = usage.get('completion_tokens', 0)
                 # Fake cost for demonstration if needed: cost = total_tokens * 0.000001
                 # Storing raw usage might be better:
                 # response_content += f"\n\n---\n*Usage: {usage}*"


        except requests.exceptions.Timeout:
            error_msg = f"Error: Request timed out after {REQUEST_TIMEOUT_SECONDS} seconds."
        except requests.exceptions.RequestException as e:
            error_body = ""
            if hasattr(e.response, 'text'):
                try:
                     error_detail = json.dumps(e.response.json(), indent=2)
                     error_body = f"\n```json\n{error_detail}\n```"
                except (json.JSONDecodeError, AttributeError):
                     error_body = f"\n```\n{e.response.text[:500]}\n```" # Show raw text excerpt
            error_msg = f"Error: API request failed: {e}{error_body}"
        except Exception as e:
            error_msg = f"Error: An unexpected error occurred: {e}"

        # Update status safely
        with self._lock:
            status_obj = self._model_status[status_key]
            status_obj.end_time = time.monotonic()
            status_obj.cost = cost # Store calculated cost
            if error_msg:
                status_obj.status = "Error"
                status_obj.error_message = error_msg
                status_obj.result_content = f"# ERROR: Failed to get response from {model_name}\n\n**Timestamp:** {datetime.now().isoformat()}\n**Error Details:**\n{error_msg}"
            elif response_content:
                status_obj.status = "Done"
                status_obj.result_content = response_content
            else: # Should not happen if error handling is correct
                status_obj.status = "Error"
                status_obj.error_message = "Unknown error: No content and no specific error."
                status_obj.result_content = f"# ERROR: Unknown failure for {model_name}"

            # Write result/error to file immediately after processing
            if status_obj.result_content:
                 self.output_builder.write_llm_response(
                      self.task_dir_path, status_obj.name, status_obj.result_content
                 )


    def _generate_status_table(self) -> Table:
        """ Creates a Rich Table to display current model statuses. """
        table = Table(show_header=False, box=None, padding=0)
        table.add_column()

        sorted_names = sorted(self._model_status.keys())
        for name in sorted_names:
            status_obj = self._model_status[name]
            table.add_row(status_obj.get_display())
        return table

    def process_llms(
        self,
        llm_names: List[str],
        merged_prompt: str,
        model_overrides: Dict[str, Dict[str, Any]]
    ) -> float:
        """
        Processes the list of LLMs, sending requests to OpenRouter models in parallel.
        Displays live status updates using Rich. Writes results to files.
        Returns the total calculated cost.
        """
        self._model_status = {}
        openrouter_tasks = []

        # Initialize status for all models
        for name in llm_names:
            is_or = self._is_openrouter_model(name)
            self._model_status[name] = ModelStatus(name, is_or)
            if is_or:
                openrouter_tasks.append(name)
            else:
                # Set final status for manual models immediately
                self._model_status[name].status = "Manual Input"
                self._model_status[name].end_time = time.monotonic()


        if not openrouter_tasks:
            self.console.print("[yellow]No OpenRouter models selected. Skipping API calls.[/yellow]")
            # Display final table once
            self.console.print(self._generate_status_table())
            return 0.0 # No cost

        if not self.api_key:
             self.console.print("[yellow]OpenRouter API Key not found or provided. Skipping API calls.[/yellow]")
             # Mark all OR models as error
             for name in openrouter_tasks:
                  self._model_status[name].status = "Error"
                  self._model_status[name].error_message = "API Key not configured."
                  self._model_status[name].end_time = time.monotonic()
                  self.output_builder.write_llm_response(
                       self.task_dir_path, name, self._model_status[name].result_content or "# Error: API Key missing"
                  )
             self.console.print(self._generate_status_table())
             return 0.0

        # Use ThreadPoolExecutor for parallel requests
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit tasks
            for model_name in openrouter_tasks:
                overrides = model_overrides.get(model_name, {})
                future = executor.submit(self._send_request, model_name, merged_prompt, overrides)
                self._model_status[model_name].future = future

            # Display live updates
            with Live(self._generate_status_table(), console=self.console, refresh_per_second=4, transient=False) as live:
                active_futures = len(openrouter_tasks)
                while active_futures > 0:
                    active_futures = 0
                    with self._lock:
                         for status in self._model_status.values():
                              if status.is_openrouter and status.end_time is None:
                                   active_futures += 1
                    live.update(self._generate_status_table())
                    time.sleep(0.1) # Prevent busy-waiting

        # Final table update after loop finishes (optional, Live usually shows final state)
        # self.console.print(self._generate_status_table())

        # Calculate total cost
        total_cost = sum(status.cost for status in self._model_status.values())
        return total_cost 