import json
import random
import uuid

from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.db.models import Count, Max, Q
from django.core.paginator import Paginator
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.utils.translation import gettext as _
from .forms import CardForm, DeckForm, FreeStudyForm
from .models import Card, CardReview, Deck
from .japanese import furigana_html, generate_furigana_markup
from .seed_default_user import ensure_default_user
from .study import record_answer, scheduled_cards, struggling_card_ids, undo_answer
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
    decks = list(user.decks.all())
    for deck in decks:
        due, new = scheduled_cards(deck)
        deck.due_count, deck.new_count = len(due), len(new)
    return render(request, "flashcards/deck_list.html", {
        "decks": decks,
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
    due, new = scheduled_cards(deck)
    return render(request, "flashcards/deck_detail.html", {
        "deck": deck, "card_count": deck.cards.count(), "form": form,
        "due_count": len(due), "new_count": len(new),
    })

def deck_export(request, pk):
    deck = get_object_or_404(Deck, pk=pk, user=ensure_default_user())
    payload = {
        "format": "kaado-deck",
        "version": 1,
        "deck": {
            "name": deck.name,
            "description": deck.description,
            "cards": list(deck.cards.values("front", "front_furigana", "back")),
        },
    }
    response = HttpResponse(
        json.dumps(payload, ensure_ascii=False, indent=2, cls=DjangoJSONEncoder),
        content_type="application/json; charset=utf-8",
    )
    response["Content-Disposition"] = f'attachment; filename="deck-{deck.pk}.json"'
    return response

def deck_import(request):
    error = None
    if request.method == "POST":
        uploaded_file = request.FILES.get("backup")
        if uploaded_file is None:
            error = _("Choose a Kaado deck backup file.")
        elif uploaded_file.size > 5 * 1024 * 1024:
            error = _("The backup file must be 5 MB or smaller.")
        else:
            try:
                payload = json.loads(uploaded_file.read().decode("utf-8"))
                deck_data = payload["deck"]
                name = deck_data["name"]
                description = deck_data.get("description", "")
                cards = deck_data["cards"]
                if payload.get("format") != "kaado-deck" or payload.get("version") != 1:
                    raise ValueError
                if not isinstance(name, str) or not name.strip() or len(name) > 120:
                    raise ValueError
                if not isinstance(description, str) or not isinstance(cards, list) or len(cards) > 10000:
                    raise ValueError
                cleaned_cards = []
                for card in cards:
                    if not isinstance(card, dict):
                        raise ValueError
                    front = card.get("front")
                    furigana = card.get("front_furigana", "")
                    back = card.get("back")
                    if not isinstance(front, str) or not front.strip():
                        raise ValueError
                    if not isinstance(furigana, str) or not isinstance(back, str) or not back.strip():
                        raise ValueError
                    cleaned_cards.append({"front": front, "front_furigana": furigana, "back": back})
            except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError):
                error = _("This file is not a valid Kaado deck backup.")
            else:
                with transaction.atomic():
                    deck = Deck.objects.create(
                        user=ensure_default_user(), name=name.strip(), description=description,
                    )
                    Card.objects.bulk_create([Card(deck=deck, **card) for card in cleaned_cards])
                return redirect("deck_detail", pk=deck.pk)
    return render(request, "flashcards/deck_import.html", {"error": error})

def deck_cards(request, pk):
    deck = get_object_or_404(Deck, pk=pk, user=ensure_default_user())
    cards = deck.cards.annotate(
        review_count=Count("reviews"),
        correct_count=Count("reviews", filter=Q(reviews__knew_it=True)),
        practice_count=Count("reviews", filter=Q(reviews__mode=CardReview.Mode.FREE)),
        scheduled_count=Count("reviews", filter=Q(reviews__mode=CardReview.Mode.SCHEDULED)),
        last_reviewed=Max("reviews__reviewed_at"),
    ).order_by("pk")
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
    due, new = scheduled_cards(deck)
    return render(request, "flashcards/card_list.html", {
        "deck": deck, "due_count": len(due), "new_count": len(new),
        "page_obj": page_obj,
        "search_query": search_query,
    })

def start_session(request, deck, card_ids, mode):
    request.session[f"study_{deck.pk}"] = {
        "version": 3,
        "mode": mode,
        "card_ids": card_ids,
        "total_cards": len(card_ids),
        "correct_card_ids": [],
        "index": 0,
        "revealed": False,
        "session_id": str(uuid.uuid4()),
    }
    return redirect("study_session", pk=deck.pk)


def study_start(request, pk):
    deck = get_object_or_404(Deck, pk=pk, user=ensure_default_user())
    due, new = scheduled_cards(deck)
    return start_session(request, deck, due + new, CardReview.Mode.SCHEDULED)


def free_study(request, pk):
    deck = get_object_or_404(Deck, pk=pk, user=ensure_default_user())
    form = FreeStudyForm(
        request.POST if request.method == "POST" else None,
        initial=request.session.get("free_study_preferences", {"count": 15, "selection": "struggling"}),
    )
    if request.method == "POST" and form.is_valid():
        count, selection = form.cleaned_data["count"], form.cleaned_data["selection"]
        request.session["free_study_preferences"] = form.cleaned_data
        if selection == "struggling":
            card_ids = struggling_card_ids(deck)[:count]
        else:
            cards = deck.cards.all()
            if selection == "new":
                cards = cards.filter(reviews__isnull=True, due_at__isnull=True)
            card_ids = list(cards.values_list("pk", flat=True))
            random.shuffle(card_ids)
            card_ids = card_ids[:count]
        if card_ids:
            return start_session(request, deck, card_ids, CardReview.Mode.FREE)
        form.add_error(None, _("No cards match this selection. Try another option."))
    return render(request, "flashcards/free_study.html", {"deck": deck, "form": form})


def study_session(request, pk):
    deck = get_object_or_404(Deck, pk=pk, user=ensure_default_user())
    session_key = f"study_{deck.pk}"
    study = request.session.get(session_key)
    if study is None:
        return redirect("study_start", pk=deck.pk)
    if study.get("version") != 3:
        return redirect("study_start", pk=deck.pk)
    study.setdefault("session_id", str(uuid.uuid4()))
    study.setdefault("total_cards", len(study["card_ids"]))
    study.setdefault("correct_card_ids", [])

    if request.method == "POST":
        action = request.POST.get("action")
        study.pop("undo_unavailable", None)
        if action == "undo":
            previous = study.pop("last_answer", None)
            if previous is not None:
                if undo_answer(deck, study, previous["review_id"]) is not False:
                    study.update(previous["state"])
                else:
                    study["undo_unavailable"] = True
        elif action == "show" and study["index"] < len(study["card_ids"]):
            study["revealed"] = True
        elif action in {"knew", "missed"} and study["revealed"] and study["index"] < len(study["card_ids"]):
            queue = study["card_ids"]
            index = study["index"]
            card_id = queue[index]
            card = Card.objects.filter(pk=card_id, deck=deck).first()
            if card is not None:
                previous_state = {
                    "card_ids": list(queue),
                    "correct_card_ids": list(study["correct_card_ids"]),
                    "index": index,
                    "total_cards": study["total_cards"],
                    "revealed": True,
                }
                review = record_answer(card, action == "knew", study)
                study["last_answer"] = {"review_id": review.pk, "state": previous_state}
                pending = queue[index + 1:]
                if action == "knew":
                    if card_id not in study["correct_card_ids"]:
                        study["correct_card_ids"].append(card_id)
                    study["card_ids"] = queue[:index + 1] + [pending_id for pending_id in pending if pending_id != card_id]
                elif card_id not in pending:
                    queue.append(card_id)
            else:
                study["card_ids"] = queue[:index + 1] + [pending_id for pending_id in queue[index + 1:] if pending_id != card_id]
                study["total_cards"] = max(0, study["total_cards"] - 1)
            study["index"] += 1
            study["revealed"] = False
        request.session[session_key] = study
        return redirect("study_session", pk=deck.pk)

    card = None
    while study["index"] < len(study["card_ids"]):
        card_id = study["card_ids"][study["index"]]
        card = Card.objects.filter(pk=card_id, deck=deck).first()
        if card is not None:
            break
        index = study["index"]
        study["card_ids"] = study["card_ids"][:index] + [
            pending_id for pending_id in study["card_ids"][index + 1:] if pending_id != card_id
        ]
        study["total_cards"] = max(0, study["total_cards"] - 1)
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
        "progress_percent": round(len(study["correct_card_ids"]) * 100 / study["total_cards"]) if study["total_cards"] else 100,
    })

@require_POST
def generate_furigana(request):
    try:
        payload = json.loads(request.body)
        text = payload.get("text", "")
    except (json.JSONDecodeError, UnicodeDecodeError, AttributeError):
        return JsonResponse({"error": _("Please provide valid Japanese text.")}, status=400)
    if not isinstance(text, str) or not text.strip():
        return JsonResponse({"error": _("Enter Japanese text first.")}, status=400)
    return JsonResponse({"furigana": generate_furigana_markup(text)})

def deck_edit(request, pk):
    deck = get_object_or_404(Deck, pk=pk, user=ensure_default_user())
    form = DeckForm(request.POST or None, instance=deck)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("deck_detail", pk=deck.pk)
    return render(request, "flashcards/deck_form.html", {"deck": deck, "form": form, "title": _("Edit deck")})

def deck_delete(request, pk):
    deck = get_object_or_404(Deck, pk=pk, user=ensure_default_user())
    if request.method == "POST":
        deck.delete()
        return redirect("deck_list")
    return render(request, "flashcards/confirm_delete.html", {
        "item": deck, "item_type": "deck", "item_type_label": _("deck"),
        "cancel_url": "deck_detail", "cancel_pk": deck.pk,
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
        "item": card, "item_type": "card", "item_type_label": _("card"),
        "cancel_url": "deck_cards", "cancel_pk": deck_pk,
    })
