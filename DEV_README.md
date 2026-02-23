# Phantom Toolkit - Developer Documentation

## Prerequisites
*   **Python 3.12+**
*   **[uv](https://docs.astral.sh/uv/)** (Recommended for package management)
*   **Node.js v22+** (For GUI development)

## Backend Setup

1.  **Install Dependencies**:
    Using `uv`, sync the project dependencies including development tools (like `ruff`).
    ```bash
    uv sync --dev
    ```

2.  **Activate Virtual Environment**:
    ```bash
    source .venv/bin/activate
    ```

3.  **Run Backend Locally**:
    You can run the backend directly with python or `uv`.
    ```bash
    uv run phantom-backend
    ```

## Frontend (GUI) Setup

1.  **Navigate to GUI directory**:
    ```bash
    cd gui
    ```

2.  **Install Node Modules**:
    ```bash
    npm install
    ```

3.  **Run Dev Server**:
    ```bash
    npm run dev
    ```

## Code Quality & Linting

### Backend (Python)
We use `ruff` for both linting and formatting.
*   **Check code**:
    ```bash
    uv run ruff check .
    ```
*   **Format code**:
    ```bash
    uv run ruff format .
    ```

### Frontend (TypeScript/React)
*   **Lint**:
    ```bash
    cd gui
    npm run lint
    ```
*   **Type Check**:
    ```bash
    cd gui
    npm run type-check
    ```

## Linux Development

On Linux, the backend runs under **Proton** (via a Windows build) to attach to the game. Build the Windows exe by running the GitHub Actions build workflow on your fork/branch, then download the resulting artifact.

1.  **Start the game** (Elden Ring or Dark Souls III) via Steam with Proton.
2.  **Run the Windows backend under Proton**:
    ```bash
    ./scripts/run_proton_phantomtoolkit.sh --exe /path/to/PhantomToolkit.exe
    ```
    The script auto-detects the running game, Proton, and the Steam prefix. See `--help` for more options.

---

## Deployment & Building

### Running from Scripts
*   **Linux**: `./start.sh`
*   **Windows**: `start.bat`

### Building Executable
To build the standalone Linux executable:
```bash
./build-linux.sh
```
