from pathlib import Path


def test_action_is_one_thin_package_based_check() -> None:
    text = Path("action/action.yml").read_text()
    assert "uv tool install" in text
    assert "cuff-cli==$CUFF_VERSION" in text
    assert '"$UV_TOOL_BIN_DIR/cuff" check' in text
    assert '--work-item "$CUFF_WORK_ITEM"' in text
    assert '--base "$CUFF_BASE"' in text
    assert '--head "$CUFF_HEAD"' in text
    for retired in ("install.sh", "cuff_home", "--require-git", "cuff init", "pyinstaller"):
        assert retired not in text.lower()
