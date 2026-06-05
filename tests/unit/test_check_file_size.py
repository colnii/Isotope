from pathlib import Path

from scripts.check_file_size import check_file


def _write_lines(path: Path, line_count: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x\n" * line_count, encoding="utf-8")


def test_check_file_size_rejects_over_limit_source_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    source_path = Path("src/isotope/example.py")
    _write_lines(source_path, 4)

    passed, messages = check_file(str(source_path), max_lines=3, warn_lines=2)

    assert passed is False
    assert messages == ["  FAIL  src/isotope/example.py: 4 lines (max 3)"]


def test_check_file_size_rejects_over_limit_test_file(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    test_path = Path("tests/unit/features/social/test_social_runner.py")
    _write_lines(test_path, 4)

    passed, messages = check_file(str(test_path), max_lines=3, warn_lines=2)

    assert passed is False
    assert messages == [
        "  FAIL  tests/unit/features/social/test_social_runner.py: 4 lines (max 3)"
    ]
