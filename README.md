# nerd-prompt (`np`)

**Context Assembler & LLM Interaction CLI**

`nerd-prompt` is a Python command-line tool designed for developers to streamline the process of:

1.  **Gathering Context:** Collecting relevant information from local project files, directories, and remote Git repositories.
2.  **Defining Tasks:** Clearly specifying instructions for a Large Language Model (LLM).
3.  **LLM Interaction (Optional):** Sending the combined context and task to LLMs via OpenRouter (supporting parallel requests).
4.  **Organizing Results:** Systematically storing the task definition, LLM responses (or placeholders for manual input), and referenced Git repositories within your project structure.

It aims to provide an elegant, efficient, and **vendor-lock-in-free** workflow for leveraging LLMs with complex project contexts.

## Core Philosophy

*   **Simplicity & Elegance:** Intuitive interface, minimal friction.
*   **Developer Experience:** Clear feedback (`rich` powered), cross-platform (macOS, Linux, Windows).
*   **Code Quality:** Exemplary, readable, maintainable, testable Python code.
*   **Flexibility:** Mix local/Git sources, use OpenRouter models or manual placeholders.
*   **Statefulness:** Remembers project preferences (`.npconfig.toml`).
*   **Reproducibility:** Tracks the exact state of Git repositories used.

## Installation

Ensure you have Python >= 3.9 and `pip` installed.

```bash
# Recommended: Install from PyPI (once published)
# pip install nerd-prompt

# Or, install directly from source:
git clone https://github.com/yourusername/nerd-prompt.git # Replace with actual URL
cd nerd-prompt
pip install .
# Or for development:
# pip install -e .[dev] # If you define a [dev] extra in pyproject.toml for test deps
```

You also need `git` installed and available in your system's PATH for Git repository features.

## Usage

`nerd-prompt` operates in two modes:

### 1. Interactive Mode

Simply navigate to your project's root directory in your terminal and run:

```bash
np
```

This will launch a guided setup process using interactive prompts (`questionary`) to configure:

*   **Sources:** Which files, directories (using globs), or Git repository URLs to include/exclude. Defaults are loaded from `.npconfig.toml` if it exists. `.gitignore` patterns are always respected.
*   **LLMs:** A space-separated list of target LLM names.
    *   Names containing a `/` (e.g., `google/gemini-pro`, `anthropic/claude-3-sonnet`) are assumed to be OpenRouter models and will be processed automatically if an API key is configured.
    *   Other names (e.g., `manual-gpt4o`, `local-llama`) act as placeholders, creating empty files for you to manually fill with responses.
*   **Task Name:** A short, descriptive name for this specific run (used for the output folder).
*   **Task Definition:** The instructions for the LLM, entered directly or loaded from a `.md`/`.txt` file.
*   **Advanced Settings (Optional):** Manage your OpenRouter API key globally or set model-specific parameters (like `temperature`).

Your preferences for includes, excludes, LLMs, and parameter overrides are saved to `.npconfig.toml` in your project directory for future runs.

### 2. Non-Interactive Mode

For scripting or direct command execution, provide arguments:

```bash
np run [OPTIONS]
```

**Key Options:**

*   `--name TEXT`: **Required.** Short name for the task.
*   `--task TEXT` / `--task-file FILE`: **Required (one of them).** Task definition.
*   `--include TEXT ...`: Paths/globs/URLs to include (overwrites config).
*   `--exclude TEXT ...`: Paths/globs to exclude (adds to defaults/gitignore).
*   `--llm TEXT ...`: Target LLM names (overwrites config).
*   `--param MODEL KEY VALUE ...`: Set OpenRouter parameter overrides.
*   `--set-api-key`: Force prompt to enter/update global API key.
*   `-y`, `--yes`: Skip the final confirmation prompt.
*   `--version`, `-V`: Show version and exit.
*   `--help`: Show help message.

**Example:**

```bash
np run \
    --name "refactor-auth" \
    --include ./src/auth/ \
    --include ./tests/auth/ \
    --include 'https://github.com/org/shared-utils.git#main' \
    --exclude "*.log" \
    --llm "google/gemini-2.5-pro-preview-03-25" \
    --llm "manual-review" \
    --task-file ./prompts/refactor-auth.md \
    --param "google/gemini-2.5-pro-preview-03-25" temperature 0.8 \
    -y
```

## Configuration

### Project Configuration (`.npconfig.toml`)

*   Located in your project root.
*   Stores default `include`, `exclude`, `llms`, `model_overrides` preferences (updated by interactive mode).
*   Contains an internal `[git_repo_map]` section mapping Git URLs to numbered output folders for consistent updates. **Do not edit `git_repo_map` manually.**

### Global Configuration (API Key)

*   Your OpenRouter API key is stored securely in a global configuration file specific to your user account (location determined by `appdirs`, e.g., `~/.config/nerd-prompt/settings.toml`).
*   Set the key interactively (`np` -> Advanced Settings) or use the `--set-api-key` flag non-interactively.
*   Alternatively, set the `OPENROUTER_API_KEY` environment variable (takes precedence).

## Git Repository Handling

*   When you include a Git repository URL (e.g., `https://.../repo.git` or `https://.../repo.git#branch`), `np` handles it intelligently:
    1.  **Mapping:** It checks `.npconfig.toml` to see if this specific URL+branch is already mapped to a numbered folder in `np_output/`.
    2.  **New Repo:** If not mapped, it gets the next available sequential number (e.g., `003`), creates a folder like `np_output/003-repo-name/`, clones the repo (`--depth 1`) into it, and saves the mapping to `.npconfig.toml`.
    3.  **Existing Repo:** If mapped, it navigates to the existing numbered folder (e.g., `np_output/003-repo-name/`) and attempts a `git pull` to fetch updates.
    4.  **Fallback:** If `pull` fails (e.g., directory was manually deleted or corrupted), it will attempt a fresh `clone` into the correct numbered directory.
    5.  **Commit Tracking:** After a successful clone or pull, the exact commit hash (`git rev-parse HEAD`) is recorded.
*   **Context Inclusion:** Files within the successfully cloned/updated numbered Git repository folder are then scanned (respecting `.gitignore` and exclude patterns) and included in the prompt assembly for the *current task*.
*   **`_task.md` Record:** The `_task.md` file generated for your task clearly lists which Git repos were used, the branch requested, the *exact commit hash* that was processed, and the path to the numbered folder where it resides within `np_output`.

## Output Structure (`np_output/`)

`np` organizes its work within an `np_output` directory in your project root:

```
your-project/
├── np_output/
│   ├── 001-repo-name/      # Cloned/updated Git repo
│   │   └── ... (repo content)
│   ├── 002-initial-setup/  # Output for the first task run
│   │   ├── _task.md        # Task def, included sources (with Git commit!), metadata
│   │   ├── google-gemini-pro.md   # LLM response (or error)
│   │   └── manual-gpt4.md         # Empty placeholder for manual input
│   ├── 003-another-repo/   # Another cloned/updated Git repo
│   │   └── ... (repo content)
│   └── 004-refactor-feature/ # Output for the second task run
│       ├── _task.md
│       └── ... (response files)
│
├── src/
├── tests/
├── .npconfig.toml
└── .gitignore
```

*   Folders are numbered sequentially based on creation order (tasks *and* newly added Git repos).
*   The tool automatically renumbers/re-pads existing folders if needed to maintain consistency.
*   `_task.md` provides a detailed record of each run's inputs.

## Token Estimation

Token counts are *estimated* based on the total character count of the assembled prompt using an approximate ratio (default: 4.0 characters/token). This is fast but not exact. The estimate is displayed and included in `_task.md`.

## Contributing

(Add contribution guidelines if you open-source the project)

## License

(Specify your chosen license - e.g., MIT License) 