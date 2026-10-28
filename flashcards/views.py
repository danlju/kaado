import json
import uuid

from django.db.models import Count, Max, Q
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from .forms import CardForm, DeckForm
from .models import Card, CardReview, Deck
from .japanese import furigana_html, generate_furigana_markup
from .seed_default_user import ensure_default_user
def deck_list(request):
    user = ensure_default_user()
    if request.method == "POST":
        form = DeckForm(request.POST)
        if form.is_valid():
            deck = form.save(commit=False)
            deck.user = user
            deck.save()
            return redirect("deck_detail", pk=deck.pk)
    else:
        form = DeckForm()
    return render(request, "flashcards/deck_list.html", {
        "decks": user.decks.all(),
        "form": form,
        "show_create_form": request.method == "POST",
    })
def deck_detail(request, pk):
    deck = get_object_or_404(Deck, pk=pk, user=ensure_default_user())
    if request.method == "POST":
        form = CardForm(request.POST)
        if form.is_valid():
            card = form.save(commit=False)
            card.deck = deck
            card.save()
            return redirect("deck_detail", pk=deck.pk)
    else:
        form = CardForm()
    return render(request, "flashcards/deck_detail.html", {
        "deck": deck, "card_count": deck.cards.count(), "form": form,
    })

def deck_cards(request, pk):
    deck = get_object_or_404(Deck, pk=pk, user=ensure_default_user())
    cards = deck.cards.annotate(
        review_count=Count("reviews"),
        correct_count=Count("reviews", filter=Q(reviews__knew_it=True)),
        last_reviewed=Max("reviews__reviewed_at"),
    )
    search_query = request.GET.get("q", "").strip()
    if search_query:
        cards = cards.filter(
            Q(front__icontains=search_query)
            | Q(front_furigana__icontains=search_query)
            | Q(back__icontains=search_query)
        )
    page_obj = Paginator(cards, 20).get_page(request.GET.get("page"))
    for card in page_obj.object_list:
        card.front_furigana_html = furigana_html(card.front_furigana or card.front)
        card.recall_accuracy = round(card.correct_count * 100 / card.review_count) if card.review_count else None
    return render(request, "flashcards/card_list.html", {
        "deck": deck,
        "page_obj": page_obj,
        "search_query": search_query,
    })

def study_start(request, pk):
    deck = get_object_or_404(Deck, pk=pk, user=ensure_default_user())
    card_ids = list(deck.cards.values_list("id", flat=True))
    request.session[f"study_{deck.pk}"] = {
        "card_ids": card_ids,
        "index": 0,
        "revealed": False,
        "session_id": str(uuid.uuid4()),
    }
    return redirect("study_session", pk=deck.pk)

def study_session(request, pk):
    deck = get_object_or_404(Deck, pk=pk, user=ensure_default_user())
    session_key = f"study_{deck.pk}"
    study = request.session.get(session_key)
    if study is None:
        return redirect("study_start", pk=deck.pk)
    study.setdefault("session_id", str(uuid.uuid4()))

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "show" and study["index"] < len(study["card_ids"]):
            study["revealed"] = True
        elif action in {"knew", "missed"} and study["revealed"]:
            card_id = study["card_ids"][study["index"]]
            card = Card.objects.filter(pk=card_id, deck=deck).first()
            if card is not None:
                CardReview.objects.create(
                    card=card,
                    knew_it=(action == "knew"),
                    session_id=study["session_id"],
                )
            study["index"] += 1
            study["revealed"] = False
        request.session[session_key] = study
        return redirect("study_session", pk=deck.pk)

    card = None
    while study["index"] < len(study["card_ids"]):
        card = Card.objects.filter(pk=study["card_ids"][study["index"]], deck=deck).first()
        if card is not None:
            break
        study["index"] += 1
    request.session[session_key] = study
    complete = study["index"] >= len(study["card_ids"])
    summary = {"reviewed": 0, "knew": 0, "missed": 0}
    if complete:
        results = CardReview.objects.filter(session_id=study["session_id"]).aggregate(
            reviewed=Count("pk"), knew=Count("pk", filter=Q(knew_it=True)),
        )
        summary = {
            "reviewed": results["reviewed"],
            "knew": results["knew"],
            "missed": results["reviewed"] - results["knew"],
        }
    if not complete:
        card.front_furigana_html = furigana_html(card.front_furigana or card.front)
    return render(request, "flashcards/study.html", {
        "deck": deck,
        "study": study,
        "card": card,
        "complete": complete,
        "summary": summary,
        "position": study["index"] + 1,
        "progress_percent": round((study["index"] + 1) * 100 / len(study["card_ids"])) if study["card_ids"] else 100,
    })

@require_POST
def generate_furigana(request):
    try:
        payload = json.loads(request.body)
        text = payload.get("text", "")
    except (json.JSONDecodeError, UnicodeDecodeError, AttributeError):
        return JsonResponse({"error": "Please provide valid Japanese text."}, status=400)
    if not isinstance(text, str) or not text.strip():
        return JsonResponse({"error": "Enter Japanese text first."}, status=400)
    return JsonResponse({"furigana": generate_furigana_markup(text)})

def deck_edit(request, pk):
    deck = get_object_or_404(Deck, pk=pk, user=ensure_default_user())
    form = DeckForm(request.POST or None, instance=deck)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("deck_detail", pk=deck.pk)
    return render(request, "flashcards/deck_form.html", {"deck": deck, "form": form, "title": "Edit deck"})

def deck_delete(request, pk):
    deck = get_object_or_404(Deck, pk=pk, user=ensure_default_user())
    if request.method == "POST":
        deck.delete()
        return redirect("deck_list")
    return render(request, "flashcards/confirm_delete.html", {
        "item": deck, "item_type": "deck", "cancel_url": "deck_detail", "cancel_pk": deck.pk,
    })

def card_edit(request, pk):
    card = get_object_or_404(Card, pk=pk, deck__user=ensure_default_user())
    form = CardForm(request.POST or None, instance=card)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("deck_cards", pk=card.deck_id)
    return render(request, "flashcards/card_form.html", {"card": card, "form": form})

def card_delete(request, pk):
    card = get_object_or_404(Card, pk=pk, deck__user=ensure_default_user())
    deck_pk = card.deck_id
    if request.method == "POST":
        card.delete()
        return redirect("deck_cards", pk=deck_pk)
    return render(request, "flashcards/confirm_delete.html", {
        "item": card, "item_type": "card", "cancel_url": "deck_cards", "cancel_pk": deck_pk,
    })
