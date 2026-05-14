"""Compatibility proxy.

New path:
    isotope.runtime.in_process

Planned removal:
    after import-map confirms no active internal imports.
"""

from isotope.runtime.in_process import *  # noqa: F401,F403
