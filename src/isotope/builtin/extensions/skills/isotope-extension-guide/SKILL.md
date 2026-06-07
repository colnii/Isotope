---
name: isotope-extension-guide
description: Explain how Isotope loads project, user, built-in, and compatibility extension assets.
---

# Isotope Extension Guide

Use this skill when explaining Isotope extension asset locations, source priority, progressive skill loading, or MCP JSON cold loading.

Default project assets live under `isotope.extensions/`. User assets live under `$ISOTOPE_HOME` or `~/.isotope`. Built-in assets are packaged with Isotope. Compatibility project assets under `.isotope/` still load with lower priority.
