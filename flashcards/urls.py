from django.urls import path
from . import views
urlpatterns = [
    path("", views.deck_list, name="deck_list"),
    path("decks/import/", views.deck_import, name="deck_import"),
    path("cards/generate-furigana/", views.generate_furigana, name="generate_furigana"),
    path("decks/<int:pk>/", views.deck_detail, name="deck_detail"),
    path("decks/<int:pk>/export/", views.deck_export, name="deck_export"),
    path("decks/<int:pk>/cards/", views.deck_cards, name="deck_cards"),
    path("decks/<int:pk>/study/", views.study_start, name="study_start"),
    path("decks/<int:pk>/study/session/", views.study_session, name="study_session"),
    path("decks/<int:pk>/edit/", views.deck_edit, name="deck_edit"),
    path("decks/<int:pk>/delete/", views.deck_delete, name="deck_delete"),
    path("cards/<int:pk>/edit/", views.card_edit, name="card_edit"),
    path("cards/<int:pk>/delete/", views.card_delete, name="card_delete"),
]
