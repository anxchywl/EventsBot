# Agents

Rules for AI models working in this repo.

## General

- Write all code, comments, and commit messages in English.
- Keep changes minimal — only touch what the task requires.
- Do not add features, abstractions, or error handling that was not asked for.
- Do not create new files unless editing an existing one is not possible.
- Do not leave debug prints, temporary variables, or commented-out code.

## Comments

Write comments only when the **why** is non-obvious — a hidden constraint, a workaround, or something that would genuinely surprise a reader.

Rules:

- All comments lowercase, no period or punctuation at the end.
- One line maximum — no multi-line comment blocks.
- Do not explain what the code does, only why it exists if that is not clear.

```python
# bad
# this function fetches the user from the database

# good
# aiogram does not pass a session in webhook context, so we open one here
```

## Code Style

- Follow existing patterns in the file you are editing.
- This is a fully async codebase — use async/await throughout (aiogram, SQLAlchemy async, FastAPI).
- Do not use bare `except:` — catch specific exceptions.
- Do not shadow builtins such as `type`, `id`, or `list`.
- Prefer early returns over deep nesting.
- Keep functions small — one responsibility per function.

## Naming

- `snake_case` for all Python identifiers.
- Short but descriptive — `get_user_events`, not `fetch` or `get_all_user_events_from_the_database`.
- Handler files should mirror what they handle — `moderation.py` contains moderation handlers.

## Database

- Always use async sessions — never call synchronous SQLAlchemy in handlers or services.
- Pass sessions as function arguments — do not create them inside service functions.
- Use SQLAlchemy models from `app/models/` — do not write raw SQL.
- Run `alembic upgrade head` after adding or changing models.

## Handlers

- Handlers in `app/handlers/` should be thin — delegate logic to `app/services/`.
- Do not query the database directly in handlers.
- Send all user-facing text through `app/localization.py` or consistent inline strings — do not mix styles.

## API

- All routes belong under `app/web/routers/`.
- Validate all input with Pydantic schemas from `app/web/schemas.py`.
- Return consistent JSON response shapes — do not vary the structure between endpoints.
- Protected endpoints require the session check from `app/web/auth.py`.

## Commits

- Lowercase imperative phrase: `fix reminder query`, `add share endpoint`, `remove unused import`.
- No period at the end.
- No issue or ticket numbers unless asked.
- Describe what changed and why if the reason is not obvious from the diff.

## What Not To Do

- Do not refactor code unrelated to the current task.
- Do not add logging unless asked.
- Do not write docstrings — type hints and good names are sufficient.
- Do not touch migrations unless a model actually changed.
- Do not hardcode values that belong in `app/config.py`.
