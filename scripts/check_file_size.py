#!/usr/bin/env python3
"""Pre-commit hook: reject .py files that exceed the max line count.

Called by pre-commit framework (via .pre-commit-config.yaml) or directly
from .git/hooks/pre-commit.  Exit code 1 blocks the commit; 0 allows it.

Usage:
    python scripts/check_file_size.py file1.py [file2.py ...]
    python scripts/check_file_size.py --max-lines=2000 --warn-lines=500 file.py
"""

import argparse
from pathlib import Path
import sys


OVER_LIMIT_EXCEPTIONS = {
    "tests/unit/features/social/test_social_runner.py",
}


def _normalized_repo_path(path: str) -> str:
    candidate = Path(path)
    if candidate.is_absolute():
        try:
            candidate = candidate.relative_to(Path.cwd())
        except ValueError:
            pass
    return candidate.as_posix()


def check_file(
    path: str, max_lines: int, warn_lines: int
) -> tuple[bool, list[str]]:
    """Return (pass, messages).  pass is True iff the file is under max_lines."""
    with open(path, "rb") as f:
        line_count = sum(1 for _ in f)

    msgs: list[str] = []
    if line_count > max_lines:
        normalized_path = _normalized_repo_path(path)
        if normalized_path in OVER_LIMIT_EXCEPTIONS:
            msgs.append(
                f"  WARN  {path}: {line_count} lines "
                f"(max {max_lines}; allowed exception for coupled regression test)"
            )
            return True, msgs
        msgs.append(
            f"  FAIL  {path}: {line_count} lines (max {max_lines})"
        )
        return False, msgs

    if line_count > warn_lines:
        msgs.append(
            f"  WARN  {path}: {line_count} lines — consider splitting "
            f"(warn threshold {warn_lines})"
        )
    return True, msgs


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Python file line counts.")
    parser.add_argument("--max-lines", type=int, default=2000)
    parser.add_argument("--warn-lines", type=int, default=500)
    parser.add_argument("files", nargs="*")
    args = parser.parse_args()

    passed = True
    warnings: list[str] = []
    for f in args.files:
        ok, msgs = check_file(f, args.max_lines, args.warn_lines)
        if not ok:
            passed = False
        for m in msgs:
            if m.startswith("  WARN"):
                warnings.append(m)
            else:
                print(m, file=sys.stderr)

    # Print warnings to stdout (not stderr) so they're visible but non-blocking
    for w in warnings:
        print(w)

    if not passed:
        print(
            f"\nSome files exceed the {args.max_lines}-line limit. "
            f"Split them before committing, or use --no-verify to bypass.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
