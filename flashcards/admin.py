from django.contrib import admin
from .models import Card, Deck
class CardInline(admin.TabularInline):
    model = Card
    extra = 0
@admin.register(Deck)
class DeckAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "created_at")
    inlines = [CardInline]
@admin.register(Card)
class CardAdmin(admin.ModelAdmin):
    list_display = ("front", "deck")
