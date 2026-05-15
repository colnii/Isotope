"""Thin app entry for the Isotope task flow."""

from isotope.features.tasks.runner import main


if __name__ == "__main__":
    raise SystemExit(main())
