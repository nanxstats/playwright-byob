# AGENTS.md

## Project intent

playwright-byob is a minimal Python package that helps Playwright launch the
real Google Chrome installed on a machine with a persistent Chrome profile. Keep
the public API small, typed, and close to Playwright's own concepts.

## Privacy rules

- Never launch or inspect a real user Chrome profile in tests.
- Tests must use temporary directories, explicit fake paths, and fake Playwright
  objects.
- Integration tests that launch Chrome must skip CI, avoid real user profile
  paths, and use isolated temporary user data directories.
- Do not add fixtures that read cookies, local storage, browser history, or other
  profile contents.
- When adding examples, clearly state that real profiles can contain sensitive
  user data.

## Development commands

Use `uv` for the environment:

```bash
uv sync --dev
uv run isort .
uv run ruff format
uv run ruff check
uv run mypy .
uv run pytest
```

If new dependencies are necessary, use `uv add <package>` and ask for permission
before installing.

## Design preferences

- Prefer standard-library code and Playwright's own Python API.
- Keep launch defaults conservative and explicit.
- Preserve escape hatches: callers should be able to pass custom paths, Chrome
  flags, and Playwright launch options.
- Keep platform detection pure and testable with explicit `env` and
  `sys_platform` parameters.
- Avoid brittle tests that require Google Chrome, a display server, network
  access, or a Playwright browser download.

## Documentation

The documentation site uses Zensical with Markdown files under `docs/`.
Update `zensical.toml` navigation when adding or renaming pages.
Keep prose concise and natural.
