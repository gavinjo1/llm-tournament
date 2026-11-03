import os

from engine.run import ENV_FILE, load_env


def test_env_file_is_the_project_root(tmp_path):
    assert ENV_FILE.name == ".env" and (ENV_FILE.parent / "pyproject.toml").exists()


def test_load_env_reads_keys(tmp_path, monkeypatch):
    monkeypatch.delenv("S2DEVIL_TEST_KEY", raising=False)
    env = tmp_path / ".env"
    env.write_text("S2DEVIL_TEST_KEY=from-file\n")
    load_env(env)
    assert os.environ["S2DEVIL_TEST_KEY"] == "from-file"
    monkeypatch.delenv("S2DEVIL_TEST_KEY")


def test_shell_variable_wins_over_env_file(tmp_path, monkeypatch):
    monkeypatch.setenv("S2DEVIL_TEST_KEY", "from-shell")
    env = tmp_path / ".env"
    env.write_text("S2DEVIL_TEST_KEY=from-file\n")
    load_env(env)
    assert os.environ["S2DEVIL_TEST_KEY"] == "from-shell"


def test_missing_env_file_is_fine(tmp_path):
    load_env(tmp_path / "nope.env")


def test_env_files_are_git_ignored():
    rules = (ENV_FILE.parent / ".gitignore").read_text().splitlines()
    assert ".env" in rules and "!.env.example" in rules
