"""Compatibility module for platform state checkpoint storage."""

import sys
from importlib import import_module

sys.modules[__name__] = import_module("isotope.platform.state.checkpoint_store")
