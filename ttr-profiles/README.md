# Reader profiles

The certification fixtures use Core's shipped profiles via `just reader-cli`.
Keep authored demo overlays beside their inputs in `sources/`. This directory
is reserved for repo-owned profiles as they are adopted.

Run `python3 scripts/check_readers.py` from the repository root to regenerate
each fixture twice and check the tracked results. See [the fixture inventory](../sources/README.md).
