from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field


@dataclass
class PreprocessingResult:
    texts: list[str]
    changed_pages: int
    applied_rules: list[str] = field(default_factory=list)


class TextPreprocessingService:
    """Nettoyage déterministe du texte extrait, sans modifier la source."""

    RULES = {
        "symbols": "Convertir les puces et symboles PDF non standards",
        "unicode": "Normaliser les caractères Unicode et ligatures",
        "spaces": "Nettoyer espaces, tabulations et lignes vides",
        "dehyphenate": "Recoller les mots coupés en fin de ligne",
        "unwrap": "Recoller les lignes d’un même paragraphe",
        "headers": "Retirer les en-têtes et pieds de page répétés",
        "page_numbers": "Retirer les lignes contenant seulement un numéro de page",
    }
    DEFAULT_RULES = ("symbols", "unicode", "spaces", "dehyphenate", "headers", "page_numbers")

    # Glyphes de polices Symbol/Wingdings parfois exposés dans la zone privée.
    SYMBOL_REPLACEMENTS = {
        "\uf02a": "•",  # puce observée dans les PDF locaux
        "\uf0b7": "•",
        "\uf0a7": "▪",
        "\uf0d8": "➢",
    }

    def process(self, texts: list[str], rules: list[str]) -> PreprocessingResult:
        selected = [rule for rule in rules if rule in self.RULES]
        original = list(texts)
        cleaned = [text.replace("\r\n", "\n").replace("\r", "\n") for text in texts]

        if "symbols" in selected:
            cleaned = [self._replace_pdf_symbols(text) for text in cleaned]
        if "unicode" in selected:
            cleaned = [unicodedata.normalize("NFKC", text) for text in cleaned]
        if "headers" in selected:
            cleaned = self._remove_repeated_margins(cleaned)
        if "page_numbers" in selected:
            cleaned = [self._remove_page_numbers(text) for text in cleaned]
        if "dehyphenate" in selected:
            cleaned = [re.sub(r"(?<=\w)[\-‐‑]\n(?=[a-zà-öø-ÿ])", "", text) for text in cleaned]
        if "unwrap" in selected:
            cleaned = [self._unwrap_paragraphs(text) for text in cleaned]
        if "spaces" in selected:
            cleaned = [self._normalize_spaces(text) for text in cleaned]

        return PreprocessingResult(
            texts=cleaned,
            changed_pages=sum(before != after for before, after in zip(original, cleaned, strict=True)),
            applied_rules=selected,
        )

    def _replace_pdf_symbols(self, text: str) -> str:
        return "".join(self.SYMBOL_REPLACEMENTS.get(character, character) for character in text)

    @staticmethod
    def _normalize_spaces(text: str) -> str:
        text = text.replace("\u00a0", " ")
        lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
        return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()

    @staticmethod
    def _remove_page_numbers(text: str) -> str:
        pattern = re.compile(r"^\s*(?:page\s+)?\d+(?:\s*/\s*\d+|\s+sur\s+\d+)?\s*$", re.I)
        return "\n".join(line for line in text.splitlines() if not pattern.match(line))

    @staticmethod
    def _unwrap_paragraphs(text: str) -> str:
        paragraphs = re.split(r"\n\s*\n", text)
        output = []
        for paragraph in paragraphs:
            lines = [line.strip() for line in paragraph.splitlines() if line.strip()]
            if not lines:
                continue
            rebuilt = lines[0]
            for line in lines[1:]:
                if (re.match(r"^(?:[-•*]|\d+[.)]|[A-ZÀ-ÖØ-Þ][A-ZÀ-ÖØ-Þ\s]{3,}:?$)", line)
                        or rebuilt.endswith((".", "!", "?", ":", ";"))):
                    rebuilt += "\n" + line
                else:
                    rebuilt += " " + line
            output.append(rebuilt)
        return "\n\n".join(output)

    def _remove_repeated_margins(self, texts: list[str]) -> list[str]:
        if len(texts) < 2:
            return texts
        margins: list[list[tuple[int, str]]] = []
        candidates = Counter()
        for text in texts:
            lines = [(index, line) for index, line in enumerate(text.splitlines()) if line.strip()]
            page_margins = lines[:2] + lines[-2:]
            margins.append(page_margins)
            candidates.update({self._margin_key(line) for _, line in page_margins if len(line.strip()) >= 3})
        threshold = max(2, (len(texts) + 1) // 2)
        repeated = {key for key, count in candidates.items() if count >= threshold}
        output = []
        for text, page_margins in zip(texts, margins, strict=True):
            removable = {index for index, line in page_margins if self._margin_key(line) in repeated}
            output.append("\n".join(
                line for index, line in enumerate(text.splitlines()) if index not in removable
            ))
        return output

    @staticmethod
    def _margin_key(line: str) -> str:
        return re.sub(r"\d+", "#", re.sub(r"\s+", " ", line.strip().casefold()))
