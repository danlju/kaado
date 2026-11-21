from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import override
from datetime import datetime, timedelta
from importlib import import_module
from unittest.mock import patch
from zoneinfo import ZoneInfo
import uuid

from .models import Card, CardReview, Deck
from .seed_default_user import ensure_default_user
from .study import record_answer, scheduled_cards, struggling_card_ids


class FlashcardSmokeTests(TestCase):
    def test_home_page_creates_default_user(self):
        response = self.client.get(reverse("deck_list"))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(get_user_model().objects.filter(username="default").exists())

    def test_create_deck(self):
        response = self.client.post(
            reverse("deck_list"),
            {"name": "Japanese", "description": "Everyday words"},
        )

        deck = Deck.objects.get(name="Japanese")
        self.assertEqual(deck.user.username, "default")
        self.assertEqual(deck.description, "Everyday words")
        self.assertRedirects(response, reverse("deck_detail", args=[deck.pk]))

    def test_create_card(self):
        deck = Deck.objects.create(user=ensure_default_user(), name="Japanese")

        response = self.client.post(
            reverse("deck_detail", args=[deck.pk]),
            {"front": "猫", "front_furigana": "[ねこ]猫", "back": "cat"},
        )

        card = deck.cards.get()
        self.assertEqual(card.front, "猫")
        self.assertEqual(card.front_furigana, "[ねこ]猫")
        self.assertEqual(card.back, "cat")
        self.assertRedirects(response, reverse("deck_detail", args=[deck.pk]))

    def test_study_session_records_review_and_completes(self):
        deck = Deck.objects.create(user=ensure_default_user(), name="Japanese")
        card = Card.objects.create(deck=deck, front="猫", back="cat")
        session_url = reverse("study_session", args=[deck.pk])

        response = self.client.get(reverse("study_start", args=[deck.pk]))
        self.assertRedirects(response, session_url)
        self.client.post(session_url, {"action": "show"})
        response = self.client.post(session_url, {"action": "knew"}, follow=True)

        review = CardReview.objects.get(card=card)
        self.assertTrue(review.knew_it)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["complete"])
        self.assertEqual(response.context["summary"], {"reviewed": 1, "knew": 1, "missed": 0})


class StudyUndoTests(TestCase):
    def setUp(self):
        self.deck = Deck.objects.create(user=ensure_default_user(), name="Japanese")
        self.card = Card.objects.create(deck=self.deck, front="猫", back="cat")
        self.url = reverse("study_session", args=[self.deck.pk])
        self.client.get(reverse("study_start", args=[self.deck.pk]))

    def answer(self, action):
        self.client.post(self.url, {"action": "show"})
        return self.client.post(self.url, {"action": action}, follow=True)

    def test_undo_completed_session_restores_card_and_removes_review(self):
        response = self.answer("knew")
        self.assertTrue(response.context["complete"])
        self.assertContains(response, 'data-study-key="u"', count=1)
        self.assertNotContains(response, "<title>Study Japanese · Kaado<form")
        response = self.client.post(self.url, {"action": "undo"}, follow=True)
        self.assertFalse(response.context["complete"])
        self.assertEqual(response.context["card"], self.card)
        self.assertTrue(response.context["study"]["revealed"])
        self.assertEqual(response.context["progress_percent"], 0)
        self.assertFalse(CardReview.objects.exists())
        self.assertNotContains(response, 'value="undo"')
        response = self.client.post(self.url, {"action": "missed"}, follow=True)
        self.assertFalse(response.context["complete"])
        self.assertFalse(CardReview.objects.get().knew_it)

    def test_undo_missed_restores_queue_and_preserves_earlier_reviews(self):
        self.answer("missed")
        first_review = CardReview.objects.get()
        before = self.client.session[f"study_{self.deck.pk}"]
        self.answer("missed")
        response = self.client.post(self.url, {"action": "undo"}, follow=True)
        study = response.context["study"]
        for key in ("card_ids", "index", "correct_card_ids", "total_cards"):
            self.assertEqual(study[key], before[key])
        self.assertEqual(list(CardReview.objects.values_list("pk", flat=True)), [first_review.pk])
        self.client.post(self.url, {"action": "undo"})
        self.assertTrue(CardReview.objects.filter(pk=first_review.pk).exists())

    def test_undo_after_revealing_next_card_restores_previous_card(self):
        other = Card.objects.create(deck=self.deck, front="犬", back="dog")
        self.client.get(reverse("study_start", args=[self.deck.pk]))
        first = self.client.get(self.url).context["card"]
        self.answer("knew")
        self.client.post(self.url, {"action": "show"})
        response = self.client.post(self.url, {"action": "undo"}, follow=True)
        self.assertEqual(response.context["card"], first)
        self.assertEqual(set(response.context["study"]["card_ids"]), {self.card.pk, other.pk})
        self.assertTrue(response.context["study"]["revealed"])
        self.assertFalse(CardReview.objects.exists())

    def test_restart_clears_undo_and_keeps_review_history(self):
        self.answer("knew")
        self.client.get(reverse("study_start", args=[self.deck.pk]))
        response = self.client.post(self.url, {"action": "undo"}, follow=True)
        self.assertFalse(response.context["study"]["revealed"])
        self.assertTrue(CardReview.objects.exists())

    def test_answer_requires_reveal_and_shortcuts_match_available_actions(self):
        response = self.client.post(self.url, {"action": "knew"}, follow=True)
        self.assertFalse(CardReview.objects.exists())
        self.assertContains(response, 'data-study-key=" "')
        self.assertNotContains(response, 'data-study-key="1"')
        response = self.client.post(self.url, {"action": "show"}, follow=True)
        self.assertContains(response, 'data-study-key="1"')
        self.assertContains(response, 'data-study-key="2"')
        self.assertNotContains(response, 'data-study-key=" "')

    def test_deleted_card_does_not_break_undo(self):
        self.answer("knew")
        self.card.delete()
        response = self.client.post(self.url, {"action": "undo"}, follow=True)
        self.assertTrue(response.context["complete"])
        self.assertEqual(response.context["summary"]["reviewed"], 0)


class SpacedRepetitionTests(TestCase):
    def setUp(self):
        self.deck = Deck.objects.create(user=ensure_default_user(), name="Japanese")
        self.card = Card.objects.create(deck=self.deck, front="猫", back="cat")
        self.start = reverse("study_start", args=[self.deck.pk])
        self.url = reverse("study_session", args=[self.deck.pk])
        self.free = reverse("free_study", args=[self.deck.pk])

    def answer(self, action):
        self.client.post(self.url, {"action": "show"})
        return self.client.post(self.url, {"action": action}, follow=True)

    def test_due_cards_precede_new_cards_and_future_cards_are_excluded(self):
        now = timezone.now()
        due = Card.objects.create(deck=self.deck, front="犬", back="dog", due_at=now)
        overdue = Card.objects.create(deck=self.deck, front="鳥", back="bird", due_at=now - timedelta(days=3))
        Card.objects.create(deck=self.deck, front="魚", back="fish", due_at=now + timedelta(days=1))
        response = self.client.get(self.start)
        self.assertRedirects(response, self.url)
        self.assertEqual(self.client.session[f"study_{self.deck.pk}"]["card_ids"], [overdue.pk, due.pk, self.card.pk])

    def test_new_card_allowance_resets_on_study_day_and_does_not_limit_due_cards(self):
        now = timezone.now()
        for index in range(12):
            Card.objects.create(deck=self.deck, front=str(index), back="new")
        due, new = scheduled_cards(self.deck, now)
        self.assertEqual(len(new), 10)
        self.deck.cards.filter(pk__in=new).update(introduced_at=now, due_at=now - timedelta(hours=1))
        due, new = scheduled_cards(self.deck, now)
        self.assertEqual(len(due), 10)
        self.assertEqual(new, [])
        due, new = scheduled_cards(self.deck, now + timedelta(days=1))
        self.assertEqual(len(new), 3)

    def test_first_success_schedules_and_undo_restores_new_state(self):
        self.client.get(self.start)
        now = datetime(2026, 11, 17, 23, 30, tzinfo=ZoneInfo("Asia/Tokyo"))
        with patch("flashcards.study.timezone.now", return_value=now):
            self.answer("knew")
        self.card.refresh_from_db()
        self.assertEqual(self.card.due_at, datetime(2026, 11, 18, 3, tzinfo=ZoneInfo("Asia/Tokyo")))
        self.assertEqual(self.card.interval_days, 1)
        self.assertEqual(self.card.introduced_at, now)
        review = CardReview.objects.get()
        self.assertEqual(review.mode, CardReview.Mode.SCHEDULED)
        self.assertFalse(review.is_retry)
        self.client.post(self.url, {"action": "undo"})
        self.card.refresh_from_db()
        self.assertIsNone(self.card.due_at)
        self.assertIsNone(self.card.introduced_at)
        self.assertEqual(self.card.interval_days, 0)
        self.assertFalse(CardReview.objects.exists())

    def test_new_card_allowance_resets_at_three_am(self):
        local_timezone = ZoneInfo("Asia/Tokyo")
        introduced = datetime(2026, 11, 17, 23, 30, tzinfo=local_timezone)
        for index in range(10):
            Card.objects.create(
                deck=self.deck, front=str(index), back="introduced",
                introduced_at=introduced, due_at=introduced + timedelta(days=1),
            )
        # Check UTC inputs too: the boundary must use the configured local timezone.
        for hour, minute in [(0, 0), (2, 59)]:
            now = datetime(2026, 11, 18, hour, minute, tzinfo=local_timezone)
            self.assertEqual(scheduled_cards(self.deck, now.astimezone(ZoneInfo("UTC")))[1], [])
        boundary = datetime(2026, 11, 18, 3, tzinfo=local_timezone)
        self.assertEqual(scheduled_cards(self.deck, boundary)[1], [self.card.pk])
        self.card.introduced_at = boundary
        self.card.due_at = boundary + timedelta(days=1)
        self.card.save()
        self.assertEqual(scheduled_cards(self.deck, boundary)[1], [])

    def test_review_schedule_uses_study_day_and_becomes_due_at_three_am(self):
        local_timezone = ZoneInfo("Asia/Tokyo")
        for hour, interval, expected_day in [(1, 0, 18), (3, 0, 19), (23, 1, 21), (1, 3, 23)]:
            with self.subTest(hour=hour, interval=interval):
                now = datetime(2026, 11, 18, hour, tzinfo=local_timezone)
                self.card.due_at = now - timedelta(days=1)
                self.card.interval_days = interval
                self.card.save()
                with patch("flashcards.study.timezone.now", return_value=now):
                    self.client.get(self.start)
                    self.answer("knew")
                self.card.refresh_from_db()
                expected = datetime(2026, 11, expected_day, 3, tzinfo=local_timezone)
                self.assertEqual(self.card.due_at, expected)
                self.assertEqual(scheduled_cards(self.deck, expected - timedelta(microseconds=1))[0], [])
                self.assertEqual(scheduled_cards(self.deck, expected)[0], [self.card.pk])

    def test_existing_review_dates_and_undo_schedules_align_to_three_am(self):
        from django.apps import apps
        from django.db import connection

        due = datetime(2026, 11, 18, 1, 30, tzinfo=ZoneInfo("Asia/Tokyo"))
        self.card.due_at = due
        self.card.save()
        review = CardReview.objects.create(
            card=self.card, knew_it=True,
            previous_schedule={"due_at": due.isoformat(), "interval_days": 1, "introduced_at": None},
        )
        migration = import_module("flashcards.migrations.0005_align_review_day_start")
        migration.align_review_day_start(apps, connection.schema_editor(atomic=False))
        self.card.refresh_from_db()
        review.refresh_from_db()
        expected = due.replace(hour=3, minute=0)
        self.assertEqual(self.card.due_at, expected)
        self.assertEqual(datetime.fromisoformat(review.previous_schedule["due_at"]), expected)

    def test_success_grows_existing_interval_and_undo_restores_due_date(self):
        for old_interval, expected in [(1, 3), (3, 6), (200, 365)]:
            with self.subTest(interval=old_interval):
                due = timezone.now() - timedelta(days=1)
                self.card.due_at = due
                self.card.interval_days = old_interval
                self.card.save()
                self.client.get(self.start)
                self.answer("knew")
                self.card.refresh_from_db()
                self.assertEqual(self.card.interval_days, expected)
                self.client.post(self.url, {"action": "undo"})
                self.card.refresh_from_db()
                self.assertEqual(self.card.due_at, due)
                self.assertEqual(self.card.interval_days, old_interval)

    def test_miss_resets_interval_and_retry_success_does_not_extend_it(self):
        self.card.due_at = timezone.now() - timedelta(days=1)
        self.card.interval_days = 14
        self.card.save()
        self.client.get(self.start)
        self.answer("missed")
        self.card.refresh_from_db()
        due = self.card.due_at
        self.assertEqual(self.card.interval_days, 1)
        response = self.answer("knew")
        self.assertTrue(response.context["complete"])
        self.card.refresh_from_db()
        self.assertEqual(self.card.due_at, due)
        retry = CardReview.objects.latest("pk")
        self.assertTrue(retry.is_retry)
        self.assertIsNone(retry.previous_schedule)
        self.client.post(self.url, {"action": "undo"})
        self.card.refresh_from_db()
        self.assertEqual(self.card.due_at, due)
        self.assertEqual(CardReview.objects.count(), 1)

    def test_free_study_records_answers_without_changing_schedule(self):
        due = timezone.now() - timedelta(days=2)
        introduced = due - timedelta(days=10)
        self.card.due_at = due
        self.card.introduced_at = introduced
        self.card.interval_days = 6
        self.card.save()
        response = self.client.post(self.free, {"count": 15, "selection": "random"})
        self.assertRedirects(response, self.url)
        self.answer("missed")
        self.answer("knew")
        self.card.refresh_from_db()
        self.assertEqual((self.card.due_at, self.card.interval_days, self.card.introduced_at), (due, 6, introduced))
        self.assertEqual(set(CardReview.objects.values_list("mode", flat=True)), {"free"})
        self.client.post(self.url, {"action": "undo"})
        self.card.refresh_from_db()
        self.assertEqual(self.card.due_at, due)
        self.client.get(self.start)
        self.assertEqual(self.client.session[f"study_{self.deck.pk}"]["card_ids"], [self.card.pk])

    def test_free_new_cards_do_not_consume_allowance_and_are_no_longer_unstudied(self):
        self.client.post(self.free, {"count": 15, "selection": "new"})
        self.answer("knew")
        self.card.refresh_from_db()
        self.assertIsNone(self.card.due_at)
        self.assertIsNone(self.card.introduced_at)
        self.assertEqual(scheduled_cards(self.deck)[1], [self.card.pk])
        response = self.client.post(self.free, {"count": 15, "selection": "new"})
        self.assertContains(response, "No cards match this selection.")

    def test_free_picker_remembers_settings_and_limits_cards(self):
        for index in range(20):
            Card.objects.create(deck=self.deck, front=str(index), back="word")
        response = self.client.get(self.free)
        self.assertEqual(response.context["form"]["count"].value(), 15)
        self.assertEqual(response.context["form"]["selection"].value(), "struggling")
        self.client.post(self.free, {"count": 7, "selection": "random"})
        self.assertEqual(len(self.client.session[f"study_{self.deck.pk}"]["card_ids"]), 7)
        response = self.client.get(self.free)
        self.assertEqual(response.context["form"]["count"].value(), 7)
        self.assertEqual(response.context["form"]["selection"].value(), "random")

    def test_invalid_free_selection_does_not_start_or_replace_session(self):
        for count, selection in [(0, "random"), (1001, "new"), ("bad", "random"), (15, "other")]:
            response = self.client.post(self.free, {"count": count, "selection": selection})
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.context["form"].errors)
            self.assertNotIn(f"study_{self.deck.pk}", self.client.session)

    def test_no_matching_struggling_cards_keeps_picker_open(self):
        self.client.get(self.start)
        state = self.client.session[f"study_{self.deck.pk}"]
        response = self.client.post(self.free, {"count": 15, "selection": "struggling"})
        self.assertContains(response, "No cards match this selection.")
        self.assertEqual(self.client.session[f"study_{self.deck.pk}"], state)

    def test_caught_up_state_keeps_free_study_available_everywhere(self):
        self.card.due_at = timezone.now() + timedelta(days=3)
        self.card.save()
        for name, args in [("deck_list", []), ("deck_detail", [self.deck.pk]), ("deck_cards", [self.deck.pk]), ("study_start", [self.deck.pk])]:
            response = self.client.get(reverse(name, args=args), follow=True)
            self.assertContains(response, "You're caught up")
            self.assertContains(response, self.free)
        self.assertFalse(CardReview.objects.exists())

    def test_old_session_is_replaced_safely(self):
        session = self.client.session
        session[f"study_{self.deck.pk}"] = {"version": 2}
        session.save()
        response = self.client.get(self.url)
        self.assertRedirects(response, self.start, fetch_redirect_response=False)

    def test_other_users_decks_are_not_accessible(self):
        other = Deck.objects.create(user=get_user_model().objects.create(username="other"), name="Other")
        for name in ["study_start", "free_study", "study_session"]:
            self.assertEqual(self.client.get(reverse(name, args=[other.pk])).status_code, 404)

    def test_struggling_selection_uses_first_answer_and_separate_sessions(self):
        steady = Card.objects.create(deck=self.deck, front="犬", back="dog")
        session_id = uuid.uuid4()
        CardReview.objects.create(card=self.card, knew_it=False, session_id=session_id)
        for index in range(10):
            CardReview.objects.create(card=self.card, knew_it=True, session_id=session_id)
        CardReview.objects.create(card=steady, knew_it=True)
        self.assertEqual(struggling_card_ids(self.deck), [self.card.pk])
        self.client.post(self.free, {"count": 15, "selection": "struggling"})
        self.assertEqual(self.client.session[f"study_{self.deck.pk}"]["card_ids"], [self.card.pk])
        for index in range(10):
            CardReview.objects.create(card=self.card, knew_it=True)
        self.assertEqual(struggling_card_ids(self.deck), [])

    def test_recent_and_repeated_misses_rank_higher(self):
        recovered = Card.objects.create(deck=self.deck, front="犬", back="dog")
        CardReview.objects.create(card=self.card, knew_it=True, mode="scheduled")
        CardReview.objects.create(card=self.card, knew_it=False, mode="scheduled")
        CardReview.objects.create(card=recovered, knew_it=False, mode="scheduled")
        CardReview.objects.create(card=recovered, knew_it=True, mode="scheduled")
        self.assertEqual(struggling_card_ids(self.deck)[0], self.card.pk)

    def test_free_results_have_less_weight_in_struggling_selection(self):
        other = Card.objects.create(deck=self.deck, front="犬", back="dog")
        for card in [self.card, other]:
            CardReview.objects.create(card=card, knew_it=True, mode="scheduled")
        CardReview.objects.create(card=self.card, knew_it=False, mode="scheduled")
        CardReview.objects.create(card=other, knew_it=False, mode="free")
        self.assertEqual(struggling_card_ids(self.deck), [self.card.pk, other.pk])

    def test_stale_session_does_not_reschedule_future_card(self):
        self.client.get(self.start)
        due = timezone.now() + timedelta(days=3)
        self.card.due_at = due
        self.card.interval_days = 3
        self.card.save()
        self.answer("knew")
        self.card.refresh_from_db()
        self.assertEqual(self.card.due_at, due)
        self.assertIsNone(CardReview.objects.get().previous_schedule)

    def test_undo_does_not_overwrite_newer_scheduling_decision(self):
        self.client.get(self.start)
        self.answer("knew")
        self.card.due_at = timezone.now() - timedelta(days=1)
        self.card.save()
        record_answer(self.card, True, {"session_id": str(uuid.uuid4()), "mode": "scheduled"})
        self.card.refresh_from_db()
        due = self.card.due_at
        response = self.client.post(self.url, {"action": "undo"}, follow=True)
        self.assertContains(response, "This answer cannot be undone")
        self.card.refresh_from_db()
        self.assertEqual(self.card.due_at, due)
        self.assertEqual(CardReview.objects.count(), 2)

    def test_japanese_picker_and_counts_are_translated(self):
        with override("ja"):
            # LocaleMiddleware reads the language cookie on each request.
            self.client.cookies["django_language"] = "ja"
            self.assertContains(self.client.get(self.free), "自由学習")
            response = self.client.get(reverse("deck_detail", args=[self.deck.pk]))
            self.assertContains(response, "新規：1枚")
