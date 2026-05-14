"""Compatibility module for platform resource references."""

import sys
from importlib import import_module

sys.modules[__name__] = import_module("isotope.platform.schemas.refs")
