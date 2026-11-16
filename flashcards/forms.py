from django import forms
from django.utils.translation import gettext_lazy as _
from .models import Card, Deck


class FreeStudyForm(forms.Form):
    count = forms.IntegerField(label=_("Number of cards"), min_value=1, max_value=1000, initial=15)
    selection = forms.ChoiceField(label=_("Cards to study"), choices=[
        ("struggling", _("Struggling cards")),
        ("random", _("Random cards")),
        ("new", _("New cards")),
    ])

class DeckForm(forms.ModelForm):
    class Meta:
        model = Deck
        fields = ["name", "description"]
        labels = {"name": _("Deck name"), "description": _("Description")}
class CardForm(forms.ModelForm):
    class Meta:
        model = Card
        fields = ["front", "front_furigana", "back"]
        labels = {
            "front": _("Japanese"),
            "front_furigana": _("Furigana"),
            "back": _("Answer / definition"),
        }
        help_texts = {
            "front": _("The original Japanese text."),
            "front_furigana": _("Generated text uses [reading]word notation. You can edit it before saving."),
        }
        widgets = {
            "front": forms.Textarea(attrs={"rows": 3}),
            "front_furigana": forms.Textarea(attrs={"rows": 3}),
            "back": forms.Textarea(attrs={"rows": 4}),
        }
