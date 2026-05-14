"""Compatibility module for platform state event storage."""

import sys
from importlib import import_module

sys.modules[__name__] = import_module("isotope.platform.state.event_store")
