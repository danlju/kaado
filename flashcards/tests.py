from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Card, CardReview, Deck
from .seed_default_user import ensure_default_user


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
