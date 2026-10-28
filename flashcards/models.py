from django.conf import settings
from django.db import models
import uuid
class Deck(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="decks")
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ["name"]
    def __str__(self):
        return self.name
class Card(models.Model):
    deck = models.ForeignKey(Deck, on_delete=models.CASCADE, related_name="cards")
    front = models.TextField()
    front_furigana = models.TextField(blank=True)
    back = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ["id"]
    def __str__(self):
        return f"{self.deck}: {self.front[:50]}"

class CardReview(models.Model):
    card = models.ForeignKey(Card, on_delete=models.CASCADE, related_name="reviews")
    reviewed_at = models.DateTimeField(auto_now_add=True, db_index=True)
    knew_it = models.BooleanField()
    session_id = models.UUIDField(default=uuid.uuid4, db_index=True)

    class Meta:
        ordering = ["-reviewed_at"]

    def __str__(self):
        result = "knew" if self.knew_it else "missed"
        return f"{self.card} · {result} · {self.reviewed_at:%Y-%m-%d %H:%M}"
