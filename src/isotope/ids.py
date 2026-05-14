"""Compatibility module for platform ID helpers."""

import sys
from importlib import import_module

sys.modules[__name__] = import_module("isotope.platform.ids")

