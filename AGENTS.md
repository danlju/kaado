# Repository Guidelines

## Project Structure & Module Organization
Kaado is a server-rendered Django flashcard app for local use, with SQLite storage and Japanese furigana generation through Fugashi.
- `config/`: Django settings, root URLs, and ASGI/WSGI entry points.
- `flashcards/`: models, views, forms, URLs, Japanese text helpers, and default-user setup.
- `flashcards/templates/flashcards/` and `flashcards/static/flashcards/`: templates, JavaScript, and CSS.
- `flashcards/migrations/`: versioned database migrations.
- `flashcards/tests.py`: Django tests.
- `locale/ja/LC_MESSAGES/`: Japanese translation catalogs.

## Build, Test, and Development Commands
Use Python 3.12 to match CI. Create a virtual environment with `python -m venv .venv`, then run:

```sh
source .venv/bin/activate
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

The development server serves the app at `http://127.0.0.1:8000/`. There is no separate frontend build step.

Before submitting changes, run the same checks as GitHub Actions:

```sh
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
```

For model changes, generate and commit migrations with `python manage.py makemigrations`.

## Coding Style & Naming Conventions
Use four-space indentation for Python, `snake_case` functions and variables, and `PascalCase` classes. Follow surrounding code and use double-quoted strings. JavaScript uses two-space indentation, semicolons, and `camelCase` variables. Keep templates and static assets namespaced under `flashcards`. No formatter or linter is configured.

Wrap user-facing strings in Django translation helpers or template translation tags. After changing translations, run `python manage.py compilemessages --ignore=.venv` and commit both `.po` and `.mo` files; GNU gettext is required.

## Testing Guidelines
Use `django.test.TestCase` in `flashcards/tests.py`, with descriptive `test_` method names. Add regression coverage for changed behavior, including response status, redirects, and database effects where applicable. Run focused tests with `python manage.py test flashcards.tests`. No coverage percentage is enforced.

## Commit & Pull Request Guidelines
History uses short, descriptive subjects such as “Shuffle cards when reviewing”; no formal commit prefix is established. Keep commits focused. Pull requests should describe behavior changes, link relevant issues, and report validation results. Include screenshots for interface changes and note migrations or translation updates.

## Security & Configuration
Settings are intended for local development: debug mode is enabled and a default user is created without login. Review configuration before exposing the app beyond localhost. Keep secrets, local SQLite databases, and virtual environments out of commits.
