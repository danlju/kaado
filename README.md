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

Use **Study now** on a deck to review its cards in order. Reveal each answer and mark whether you knew it. Cards marked **Didn’t know** return at the end of the queue and repeat until recalled correctly; the session finishes when all remaining cards have been answered correctly. Every response is saved as a card review event, so each card shows its review count, recall accuracy, and last studied date. Studying remains unrestricted; these records do not schedule cards or impose daily limits.

The deck page keeps the add-card form in view. Use **Browse cards** to search, paginate, edit, or delete cards without a long list pushing the form down.

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

