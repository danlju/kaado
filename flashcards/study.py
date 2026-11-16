"""Card selection and the deliberately small first-version review scheduler."""

from collections import defaultdict
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import Card, CardReview


DAILY_NEW_LIMIT = 10


def scheduled_cards(deck, now=None):
    now = now or timezone.now()
    due_ids = list(deck.cards.filter(due_at__lte=now).order_by("due_at", "pk").values_list("pk", flat=True))
    introduced_today = deck.cards.filter(introduced_at__date=timezone.localdate(now)).count()
    allowance = max(0, DAILY_NEW_LIMIT - introduced_today)
    new_ids = list(deck.cards.filter(due_at__isnull=True).order_by("pk").values_list("pk", flat=True)[:allowance])
    return due_ids, new_ids


def struggling_card_ids(deck):
    # Only the first answer per card/session measures recall after a gap.
    # This also handles historical reviews, which did not mark retries.
    sessions = defaultdict(dict)
    for review in CardReview.objects.filter(card__deck=deck).order_by("reviewed_at", "pk"):
        sessions[review.card_id].setdefault(review.session_id, review)
    scores = []
    for card_id, observations in sessions.items():
        recent = list(observations.values())[-10:]
        weighted_misses = 0
        total_weight = 0
        for age, review in enumerate(reversed(recent)):
            weight = (0.8 ** age) * (0.5 if review.mode == CardReview.Mode.FREE else 1)
            total_weight += weight
            if not review.knew_it:
                weighted_misses += weight
        if weighted_misses:
            score = weighted_misses / total_weight + min(weighted_misses, 3) * 0.1
            scores.append((score, card_id))
    return [card_id for score, card_id in sorted(scores, reverse=True)]


@transaction.atomic
def record_answer(card, knew_it, study):
    card = Card.objects.select_for_update().get(pk=card.pk)
    retry = card.reviews.filter(session_id=study["session_id"]).exists()
    previous = None
    now = timezone.now()
    if study["mode"] == CardReview.Mode.SCHEDULED and not retry:
        # A second tab/session may already have reviewed this card.
        if card.due_at is None or card.due_at <= now:
            previous = {
                "due_at": card.due_at.isoformat() if card.due_at else None,
                "interval_days": card.interval_days,
                "introduced_at": card.introduced_at.isoformat() if card.introduced_at else None,
            }
            if not knew_it or not card.interval_days:
                card.interval_days = 1
            elif card.interval_days == 1:
                card.interval_days = 3
            else:
                card.interval_days = min(card.interval_days * 2, 365)
            card.due_at = now + timedelta(days=card.interval_days)
            card.introduced_at = card.introduced_at or now
            card.save(update_fields=["due_at", "interval_days", "introduced_at"])
    return CardReview.objects.create(
        card=card, knew_it=knew_it, session_id=study["session_id"],
        mode=study["mode"], is_retry=retry, previous_schedule=previous,
    )


@transaction.atomic
def undo_answer(deck, study, review_id):
    review = CardReview.objects.filter(
        pk=review_id, session_id=study["session_id"], card__deck=deck,
    ).first()
    if review is None:
        return
    card = Card.objects.select_for_update().get(pk=review.card_id)
    if review.previous_schedule is not None:
        # Preserve a newer scheduling decision made in another session.
        later_schedule = card.reviews.filter(pk__gt=review.pk, previous_schedule__isnull=False).exists()
        if later_schedule:
            return False
        previous = review.previous_schedule
        card.due_at = parse_datetime(previous["due_at"]) if previous["due_at"] else None
        card.interval_days = previous["interval_days"]
        card.introduced_at = parse_datetime(previous["introduced_at"]) if previous["introduced_at"] else None
        card.save(update_fields=["due_at", "interval_days", "introduced_at"])
    review.delete()
    return True
