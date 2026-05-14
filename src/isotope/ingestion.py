"""Compatibility module for RAG ingestion."""

import sys
from importlib import import_module

sys.modules[__name__] = import_module("isotope.rag.ingestion")
