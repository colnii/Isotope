"""Compatibility module for platform event schema registry."""

import sys
from importlib import import_module

sys.modules[__name__] = import_module("isotope.platform.events.event_schema")
