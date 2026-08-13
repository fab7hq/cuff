from pathlib import Path


def test_action_is_one_thin_package_based_check() -> None:
    text = Path("action/action.yml").read_text()
    assert "uv tool install" in text
    assert "fab7-cli==$FAB7_VERSION" in text
    assert '"$UV_TOOL_BIN_DIR/fab7" check' in text
    assert '--work-item "$FAB7_WORK_ITEM"' in text
    assert '--base "$FAB7_BASE"' in text
    assert '--head "$FAB7_HEAD"' in text
    for retired in ("install.sh", "fab7_home", "--require-git", "fab7 init", "pyinstaller"):
        assert retired not in text.lower()
