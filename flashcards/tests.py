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
