from collections.abc import Callable, Iterable
from difflib import get_close_matches
from html import unescape
import re
import unicodedata

from bm25s.stopwords import STOPWORDS_RUSSIAN


WORD_PATTERN = re.compile(r"(?u)\b[^\W_]+(?:-[^\W_]+)*\b")
_DASHES = str.maketrans("‐‑‒–—−", "------")
_MEANINGFUL = frozenset("не ни нет без нельзя до после перед один два три".split())
_FILLER = frozenset("пожалуйста подскажи подскажите скажи скажите здравствуйте привет помогите какие который которая которые нужно свою свои мою мои это чтобы бы же".split())
RUSSIAN_STOPWORDS = (frozenset(STOPWORDS_RUSSIAN) | _FILLER) - _MEANINGFUL


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", unescape(text)).casefold().replace("ё", "е").translate(_DASHES)
    return re.sub(r"\s+", " ", text).strip()


def words(text: str) -> list[str]:
    return WORD_PATTERN.findall(normalize_text(text))


def _distance(left: str, right: str) -> int:
    previous = list(range(len(right) + 1))
    older = previous
    for i, first in enumerate(left, 1):
        current = [i]
        for j, second in enumerate(right, 1):
            value = min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (first != second))
            if i > 1 and j > 1 and first == right[j - 2] and left[i - 2] == second:
                value = min(value, older[j - 2] + 1)
            current.append(value)
        older, previous = previous, current
    return previous[-1]


class QueryPreprocessor:
    def __init__(self, vocabulary: Iterable[str], stem: Callable[[str], list[str]]) -> None:
        self.vocabulary = frozenset(vocabulary) - RUSSIAN_STOPWORDS
        self.stem = stem
        self.known_stems = frozenset(term for word in self.vocabulary for term in stem(word))
        self.candidates = sorted(word for word in self.vocabulary | RUSSIAN_STOPWORDS | _MEANINGFUL
                                 if re.fullmatch(r"[а-я]{4,}", word))

    def _correct(self, word: str) -> str:
        if word in self.vocabulary or word in RUSSIAN_STOPWORDS or word in _MEANINGFUL or not re.fullmatch(r"[а-я]{4,}", word):
            return word
        if any(term in self.known_stems for term in self.stem(word)):
            return word
        budget = 1 if len(word) < 9 else 2
        possible = get_close_matches(word, self.candidates, n=8, cutoff=0.75)
        distances = [(candidate, _distance(word, candidate)) for candidate in possible]
        nearest = min((distance for _, distance in distances), default=budget + 1)
        closest = [candidate for candidate, distance in distances if distance == nearest]
        return closest[0] if nearest <= budget and len(closest) == 1 else word

    def prepare(self, query: str) -> str:
        def replace(match: re.Match) -> str:
            original = match.group()
            word = normalize_text(original)
            corrected = self._correct(word)
            if corrected == word:
                return original
            if original.isupper():
                return corrected.upper()
            return corrected.capitalize() if original.istitle() else corrected

        query = unicodedata.normalize("NFKC", unescape(query)).translate(_DASHES)
        return WORD_PATTERN.sub(replace, re.sub(r"\s+", " ", query).strip())
