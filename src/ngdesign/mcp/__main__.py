"""``python -m ngdesign.mcp`` — same as the ``stomato-mcp`` console script."""

from ngdesign.mcp.server import main

if __name__ == "__main__":
    raise SystemExit(main())
