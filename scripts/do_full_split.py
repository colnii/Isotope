#!/usr/bin/env python3
"""Execute full split and sub-split oversized files."""
import re
from pathlib import Path

SRC = Path("tests/integration/codex/test_codex_supervisor_readonly.py")
OUT_DIR = Path("tests/integration/codex")

# First, run the main split script
import sys
sys.path.insert(0, str(Path.cwd()))
from scripts.split_readonly_tests import main as split_main

import argparse
# Pass --no-dry-run via argv manipulation
old_argv = sys.argv
sys.argv = ["split_readonly_tests.py"]
split_main()
sys.argv = old_argv

# Now split the oversized files further

# Step 1: Split test_runner_supervise.py into action/report
# By finding the test names within that file and splitting by sub-pattern
supervise_path = OUT_DIR / "test_runner_supervise.py"
lines = supervise_path.read_text().splitlines(keepends=True)

# Find test function boundaries
test_starts = []
for i, l in enumerate(lines):
    stripped = l.lstrip()
    if stripped.startswith("def test_codex_supervisor_") or stripped.startswith("def test_"):
        name = l[l.index("def ") + 4 : l.index("(")].strip()
        test_starts.append((i, name))

# Split supervise tests: first half "action" (execute/launch/resume), 
# second half "report" (supervise/report/review)
mid = len(test_starts) // 2
action_names = set(n for _, n in test_starts[:mid])
report_names = set(n for _, n in test_starts[mid:])

def write_subfile(filename: str, test_set: set, source_lines: list):
    path = OUT_DIR / filename
    body = []
    # Write import block (everything before first test function)
    first_test = len(source_lines)
    for i, l in enumerate(source_lines):
        stripped = l.lstrip()
        if stripped.startswith("def test_"):
            first_test = i
            break
    body.extend(source_lines[:first_test])
    body.append("\n")
    
    # Write selected tests
    i = first_test
    while i < len(source_lines):
        stripped = source_lines[i].lstrip()
        if stripped.startswith("def test_"):
            name = source_lines[i][source_lines[i].index("def ") + 4 : source_lines[i].index("(")].strip()
            if name in test_set:
                # Write this test to end of its block
                end = i + 1
                while end < len(source_lines):
                    nxt = source_lines[end].lstrip()
                    if nxt.startswith("def test_") and not nxt.startswith("def test__"):
                        break
                    end += 1
                body.extend(source_lines[i:end])
                body.append("\n")
            i += 1
        else:
            i += 1
    
    path.write_text("".join(body))
    line_count = len("".join(body).splitlines())
    print(f"  wrote {filename}: {len(test_set)} tests, ~{line_count} lines")

write_subfile("test_runner_supervise_action.py", action_names, lines)
write_subfile("test_runner_supervise_report.py", report_names, lines)
supervise_path.unlink()
print(f"  deleted test_runner_supervise.py")

# Step 2: Split test_runner_loop.py into 3 files
loop_path = OUT_DIR / "test_runner_loop.py"
lines = loop_path.read_text().splitlines(keepends=True)

test_starts = []
for i, l in enumerate(lines):
    stripped = l.lstrip()
    if stripped.startswith("def test_codex_supervisor_") or stripped.startswith("def test_"):
        name = l[l.index("def ") + 4 : l.index("(")].strip()
        test_starts.append((i, name))

n = len(test_starts)
split1 = n // 3
split2 = 2 * n // 3

loop_decision_names = set(n for _, n in test_starts[:split1])
loop_worker_names = set(n for _, n in test_starts[split1:split2])
loop_fanout_names = set(n for _, n in test_starts[split2:])

write_subfile("test_runner_loop_decision.py", loop_decision_names, lines)
write_subfile("test_runner_loop_worker.py", loop_worker_names, lines)
write_subfile("test_runner_loop_fanout.py", loop_fanout_names, lines)
loop_path.unlink()
print(f"  deleted test_runner_loop.py")

print("\nDone. Check file sizes:")
for f in sorted(OUT_DIR.glob("test_*.py")):
    line_count = len(f.read_text().splitlines())
    print(f"  {f.name}: {line_count} lines")
