"""Test fixtures and helpers.

Fixtures are organized by domain to keep conftest.py lean and prevent
the '3000-line conftest.py' problem.

Each module exposes pytest fixtures or plain helper functions that can be
imported from individual test files.

To add a new fixture:
  1. Create the module here (e.g. llm.py for LLM-related fake providers).
  2. Define your fixture function(s).
  3. If tests need to opt in explicitly, import the fixture module in your
     test file or declare it in conftest.py.
"""
