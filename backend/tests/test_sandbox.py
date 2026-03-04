import os
import tempfile
import pytest
from pathlib import Path
from app.engine.sandbox import create_sandbox, cleanup_sandbox


@pytest.fixture
def fake_repo():
    """Create a fake git repo to sandbox."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo = Path(tmpdir) / "test-repo"
        repo.mkdir()
        (repo / "README.md").write_text("# Test")
        (repo / "src").mkdir()
        (repo / "src" / "main.py").write_text("print('hello')")
        # Init git
        os.system(f"cd {repo} && git init && git add . && git commit -m 'init'")
        yield repo


def test_create_sandbox(fake_repo, tmp_path):
    workspace_dir = tmp_path / ".workspaces"
    sandbox_path = create_sandbox(
        repo_path=str(fake_repo),
        workspace_dir=str(workspace_dir),
        run_id="test-run-1",
        branch_name="ai/test-feature",
        base_branch="master",
    )

    assert Path(sandbox_path).exists()
    assert (Path(sandbox_path) / "README.md").exists()
    assert (Path(sandbox_path) / "src" / "main.py").exists()
    assert (Path(sandbox_path) / ".git").exists()


def test_cleanup_sandbox(fake_repo, tmp_path):
    workspace_dir = tmp_path / ".workspaces"
    sandbox_path = create_sandbox(
        repo_path=str(fake_repo),
        workspace_dir=str(workspace_dir),
        run_id="test-run-2",
        branch_name="ai/test-feature",
        base_branch="master",
    )
    assert Path(sandbox_path).exists()

    cleanup_sandbox(sandbox_path)
    assert not Path(sandbox_path).exists()
