"""Compatibility proxy for legacy schema imports."""

import sys
from importlib import import_module

sys.modules[__name__] = import_module("isotope.platform.schemas.models")
