import shutil
import subprocess
from pathlib import Path


EXCLUDE_DIRS = {".venv", ".workspaces", ".worktrees", "__pycache__", "node_modules", ".tox"}


def _ignore_excluded(directory: str, contents: list[str]) -> set[str]:
    """Return set of directory names to exclude during copytree."""
    return {name for name in contents if name in EXCLUDE_DIRS}


def create_sandbox(
    repo_path: str,
    workspace_dir: str,
    run_id: str,
    branch_name: str,
    base_branch: str = "main",
) -> str:
    """Copy a repo into an isolated sandbox workspace and checkout a new branch."""
    src = Path(repo_path)
    dest = Path(workspace_dir) / run_id
    dest.mkdir(parents=True, exist_ok=True)

    # Copy repo contents (excluding heavy dirs)
    for item in src.iterdir():
        if item.name in EXCLUDE_DIRS:
            continue
        if item.name == ".git":
            # Copy .git separately to preserve history
            shutil.copytree(item, dest / ".git")
            continue
        if item.is_dir():
            shutil.copytree(item, dest / item.name, ignore=_ignore_excluded)
        else:
            shutil.copy2(item, dest / item.name)

    # Checkout base branch, then create new branch
    subprocess.run(
        ["git", "checkout", base_branch],
        cwd=str(dest),
        capture_output=True,
    )
    subprocess.run(
        ["git", "checkout", "-b", branch_name],
        cwd=str(dest),
        capture_output=True,
        check=True,
    )

    return str(dest)


def cleanup_sandbox(sandbox_path: str) -> None:
    """Remove a sandbox workspace."""
    path = Path(sandbox_path)
    if path.exists():
        shutil.rmtree(path)
