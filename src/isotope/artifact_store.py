"""Compatibility module for workspace artifact storage."""

import sys
from importlib import import_module

sys.modules[__name__] = import_module("isotope.workspace.artifacts")
