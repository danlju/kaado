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

Use **Study now** on a deck to review its cards in order. Reveal each answer, mark whether you knew it, and see a session summary. Every response is saved as a card review event, so each card shows its review count, recall accuracy, and last studied date. Studying remains unrestricted; these records do not schedule cards or impose daily limits.

The deck page keeps the add-card form in view. Use **Browse cards** to search, paginate, edit, or delete cards without a long list pushing the form down.

