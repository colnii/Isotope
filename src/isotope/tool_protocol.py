"""Compatibility module for platform tool protocol schemas."""

import sys
from importlib import import_module

sys.modules[__name__] = import_module("isotope.platform.schemas.tool_protocol")
