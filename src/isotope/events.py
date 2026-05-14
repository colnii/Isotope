"""Compatibility module for platform canonical events."""

import sys
from importlib import import_module

sys.modules[__name__] = import_module("isotope.platform.events.events")
