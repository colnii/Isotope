"""Compatibility module for the in-process runtime."""

import sys
from importlib import import_module

sys.modules[__name__] = import_module("isotope.runtime.in_process")
