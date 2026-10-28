from django import forms
from .models import Card, Deck
class DeckForm(forms.ModelForm):
    class Meta:
        model = Deck
        fields = ["name", "description"]
class CardForm(forms.ModelForm):
    class Meta:
        model = Card
        fields = ["front", "front_furigana", "back"]
        labels = {
            "front": "Japanese",
            "front_furigana": "Furigana",
            "back": "Answer / definition",
        }
        help_texts = {
            "front": "The original Japanese text.",
            "front_furigana": "Generated text uses [reading]word notation. You can edit it before saving.",
        }
        widgets = {
            "front": forms.Textarea(attrs={"rows": 3}),
            "front_furigana": forms.Textarea(attrs={"rows": 3}),
            "back": forms.Textarea(attrs={"rows": 4}),
        }
