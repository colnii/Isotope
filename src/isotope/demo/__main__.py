"""Allow `python -m isotope.demo` to work as a package entry point."""

from isotope.demo import main

if __name__ == "__main__":
    raise SystemExit(main())
