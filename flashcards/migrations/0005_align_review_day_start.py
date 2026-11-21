from datetime import datetime, time
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import migrations


def align_review_day_start(apps, schema_editor):
    local_timezone = ZoneInfo(settings.TIME_ZONE)
    database = schema_editor.connection.alias

    def at_day_start(value):
        local_date = value.astimezone(local_timezone).date()
        return datetime.combine(local_date, time(3), tzinfo=local_timezone)

    Card = apps.get_model("flashcards", "Card")
    for card in Card.objects.using(database).filter(due_at__isnull=False).iterator():
        card.due_at = at_day_start(card.due_at)
        card.save(using=database, update_fields=["due_at"])

    # Undo must also restore a schedule that follows the new day boundary.
    CardReview = apps.get_model("flashcards", "CardReview")
    for review in CardReview.objects.using(database).filter(previous_schedule__isnull=False).iterator():
        previous = review.previous_schedule
        if previous.get("due_at"):
            previous["due_at"] = at_day_start(datetime.fromisoformat(previous["due_at"])).isoformat()
            review.save(using=database, update_fields=["previous_schedule"])


class Migration(migrations.Migration):
    dependencies = [
        ("flashcards", "0004_card_due_at_card_interval_days_card_introduced_at_and_more"),
    ]

    operations = [
        migrations.RunPython(align_review_day_start, migrations.RunPython.noop),
    ]
