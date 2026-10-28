from functools import lru_cache
import re

from django.utils.html import conditional_escape, format_html, mark_safe
from fugashi import Tagger


@lru_cache(maxsize=1)
def _tagger():
    return Tagger()


def _hiragana(text):
    return "".join(chr(ord(char) - 0x60) if "ァ" <= char <= "ヶ" else char for char in text)


def generate_furigana_markup(text):
    """Generate editable [reading]word notation from Japanese text."""
    annotated = []
    for word in _tagger()(text):
        surface = word.surface
        reading = getattr(word.feature, "kana", None) or getattr(word.feature, "pron", None)
        if not reading or reading == "*":
            reading = surface
        else:
            reading = _hiragana(reading)
        annotated.append(f"[{reading}]{surface}")
    return "".join(annotated)


_READING = re.compile(r"\[([^\]\r\n]+)\]")


def furigana_html(markup):
    """Render [reading]word notation as escaped HTML ruby elements."""
    matches = list(_READING.finditer(markup))
    if not matches:
        return conditional_escape(markup)

    rendered = [conditional_escape(markup[:matches[0].start()])]
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markup)
        surface = markup[match.end():end]
        reading = match.group(1)
        if surface and _hiragana(reading) != _hiragana(surface):
            rendered.append(format_html("<ruby>{}<rt>{}</rt></ruby>", surface, reading))
        else:
            rendered.append(conditional_escape(surface))
    return mark_safe("".join(rendered))
