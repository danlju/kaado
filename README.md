# Kaado

A small server-rendered Django flashcard app for local use.

## Run locally

```sh
source .venv/bin/activate
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Open http://127.0.0.1:8000/. A local `default` user is created automatically. Decks belong to that user; cards belong to decks. No login is required.

Cards store the original Japanese, an editable furigana field, and an answer/definition. Use **Generate furigana** to fill the furigana field in `[reading]word` notation, then check or correct it before saving. The deck page renders that saved field as ruby text. Automatic readings can be wrong, so review them.

Use **Study now** on a deck for due cards, oldest due first, followed by up to 10 new cards per deck per day (Asia/Tokyo). Counts appear beside the button. Cards with existing practice history but no schedule enter through the new-card allowance. When nothing is available, the app shows **You’re caught up** and keeps **Free study** available. Reveal each answer and mark whether you knew it. Cards marked **Didn’t know** return at the end of the queue and repeat until recalled correctly; the session finishes when all remaining cards have been answered correctly. Use **Space** to reveal an answer, **1** for **Didn’t know**, and **2** for **Knew it**. Click **Undo last answer** or press **U** to reverse the most recent response, including after completing a session. Undo restores that card with its answer visible and removes the response from review history; only the latest response can be undone.

Scheduled study uses the first response to each card in a session to set its next review date. A successful first review schedules it in 1 day, the next success in 3 days, and later successes double the interval up to 365 days. A miss resets it to 1 day. Immediate retries are recorded as practice within the scheduled session and do not extend the interval. Undo also restores the previous schedule.

**Free study** lets you choose 1–1,000 cards from struggling cards, random cards, or never-studied cards. It defaults to 15 struggling cards and remembers your count and selection in the browser session. If fewer cards match, it uses those available; if none match, it lets you choose another option. Free study records answers without changing review dates or consuming the daily new-card allowance, even when practicing a due card.

Struggling-card selection uses the first answer in each of the last 10 sessions per card. Recent misses and repeated misses increase priority; immediate retries are ignored, and free-study observations receive half the weight of scheduled observations. Cards without any misses in that window are excluded. Existing review history remains available as practice history.

Every response is saved as a card review event. Browsing shows total attempts, scheduled/practice counts, recall accuracy across all attempts (including retries), last studied date, and the next review date when scheduled. Deck backups contain card content only; they do not include schedules or review history.

The deck page keeps the add-card form in view. Use **Browse cards** to search, paginate, edit, or delete cards without a long list pushing the form down.

## Tests

```sh
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
```

Keyboard-handler regression tests can also be run with Node.js: `node --test tests/study-keyboard.test.cjs`.

GitHub Actions runs these checks on every push and pull request. You can also run
the **Tests** workflow manually from the repository's Actions tab.

## Deck backups

Use **Export backup** on a deck to download a UTF-8 JSON file containing the deck name, description, and cards (Japanese, furigana, and answer). **Import backup** on the deck list restores that file as a new deck. Review history and derived study statistics are not included. Imports accept Kaado deck backup files up to 5 MB and 10,000 cards.

## Interface languages

The interface is available in English and Japanese. Choose a language from the header; this changes the app UI, not the language or content of your cards. English is the source language and Japanese translations are in `locale/ja/LC_MESSAGES/django.po`.

To add a language, add its locale code and display name to `LANGUAGES` in `config/settings.py`, then create its translation catalog and compile it:

```sh
python manage.py makemessages -l fr --ignore=.venv
# Translate the entries in locale/fr/LC_MESSAGES/django.po
python manage.py compilemessages --ignore=.venv
```

Replace `fr` with the locale code you’re adding. The GNU gettext utilities must be installed for these commands. Commit both the `.po` source catalog and the generated `.mo` file so translations are available when the app runs.

