"""Compatibility module for runtime action compilation."""

import sys
from importlib import import_module

sys.modules[__name__] = import_module("isotope.runtime.action_compiler")

