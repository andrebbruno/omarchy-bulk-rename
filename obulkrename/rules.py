"""The rules: given a name, what the new name should be.

Every rule is a small object with a `transform(text, index, path)` method. Nothing here
touches the filesystem — that is what makes the whole catalogue testable, and what lets
the preview be built from exactly the same code that does the renaming.
"""
from __future__ import annotations

import datetime
import os
import re
import unicodedata
from dataclasses import dataclass


class RuleError(ValueError):
    """Something the user asked for that cannot be done — reported, never a traceback."""


@dataclass
class Replace:
    """Search and replace, plain or regular expression."""
    search: str
    replace: str = ""
    regex: bool = False
    case_sensitive: bool = True
    first_only: bool = False

    def __post_init__(self):
        if not self.search:
            raise RuleError("nothing to search for")
        flags = 0 if self.case_sensitive else re.IGNORECASE
        pattern = self.search if self.regex else re.escape(self.search)
        try:
            self._re = re.compile(pattern, flags)
        except re.error as e:
            raise RuleError(f"that is not a valid regular expression: {e}") from e
        if self.regex:
            # A plain replacement must never be read as a backreference, but a regex
            # replacement should keep \1 and \g<name> working.
            self._replacement = self.replace
        else:
            self._replacement = self.replace.replace("\\", "\\\\")

    def transform(self, text: str, index: int, path: str) -> str:
        try:
            return self._re.sub(self._replacement, text, count=1 if self.first_only else 0)
        except re.error as e:
            raise RuleError(f"the replacement is not valid: {e}") from e


@dataclass
class Affix:
    """Put something before or after the name."""
    prefix: str = ""
    suffix: str = ""

    def transform(self, text: str, index: int, path: str) -> str:
        return f"{self.prefix}{text}{self.suffix}"


@dataclass
class Number:
    """Number the files, the way PowerRename's ${} counter does.

    The template is the whole new name: "{n}" is the number and "{name}" the original.
    Leaving "{name}" out drops the original, which is exactly what someone typing
    "photo" is asking for; leaving "{n}" out still numbers, at the end, because a
    numbering rule that does not number would rename every file to the same thing.
    """
    start: int = 1
    step: int = 1
    pad: int = 2
    template: str = "{name}-{n}"

    def transform(self, text: str, index: int, path: str) -> str:
        number = str(self.start + index * self.step).rjust(self.pad, "0")
        template = self.template if "{n}" in self.template else self.template + "{n}"
        return template.replace("{n}", number).replace("{name}", text)


@dataclass
class Case:
    """lower, UPPER, Title, Sentence — the four everyone actually wants."""
    kind: str = "lower"

    KINDS = ("lower", "upper", "title", "sentence")

    def __post_init__(self):
        if self.kind not in self.KINDS:
            raise RuleError(f"unknown case {self.kind!r} (try {', '.join(self.KINDS)})")

    def transform(self, text: str, index: int, path: str) -> str:
        if self.kind == "lower":
            return text.lower()
        if self.kind == "upper":
            return text.upper()
        if self.kind == "title":
            return re.sub(r"[^\W\d_]+(?:['’][^\W\d_]+)*",
                          lambda m: m.group(0)[0].upper() + m.group(0)[1:].lower(), text)
        lowered = text.lower()
        return lowered[:1].upper() + lowered[1:]


@dataclass
class Slug:
    """A name that survives every filesystem, URL and shell: no accents, no spaces."""
    separator: str = "-"
    keep_case: bool = False

    def transform(self, text: str, index: int, path: str) -> str:
        plain = "".join(c for c in unicodedata.normalize("NFD", text)
                        if unicodedata.category(c) != "Mn")
        if not self.keep_case:
            plain = plain.lower()
        plain = re.sub(r"[^A-Za-z0-9]+", self.separator, plain)
        return plain.strip(self.separator) or "file"


@dataclass
class Unaccent:
    def transform(self, text: str, index: int, path: str) -> str:
        return "".join(c for c in unicodedata.normalize("NFD", text)
                       if unicodedata.category(c) != "Mn")


@dataclass
class Trim:
    """Collapse runs of spaces and strip the ends — the tidy-up after everything else."""
    def transform(self, text: str, index: int, path: str) -> str:
        return re.sub(r"\s+", " ", text).strip(" .")


@dataclass
class DateStamp:
    """Prefix (or suffix) the file's own date, taken from the filesystem."""
    fmt: str = "%Y-%m-%d"
    template: str = "{date} {name}"
    source: str = "mtime"

    SOURCES = ("mtime", "ctime", "today")

    def __post_init__(self):
        if self.source not in self.SOURCES:
            raise RuleError(f"unknown date source {self.source!r}")

    def transform(self, text: str, index: int, path: str) -> str:
        if self.source == "today":
            when = datetime.datetime.now()
        else:
            try:
                stat = os.stat(path)
            except OSError as e:
                raise RuleError(f"cannot read the date of {path}: {e}") from e
            when = datetime.datetime.fromtimestamp(
                stat.st_mtime if self.source == "mtime" else stat.st_ctime)
        try:
            stamp = when.strftime(self.fmt)
        except ValueError as e:
            raise RuleError(f"that is not a valid date format: {e}") from e
        return self.template.replace("{date}", stamp).replace("{name}", text)


@dataclass
class Extension:
    """Change the extension — the one rule that is about the other half of the name."""
    new: str = ""

    def transform(self, text: str, index: int, path: str) -> str:
        return self.new.lstrip(".")


CATALOGUE = {
    "replace": Replace, "affix": Affix, "number": Number, "case": Case,
    "slug": Slug, "unaccent": Unaccent, "trim": Trim, "date": DateStamp,
    "extension": Extension,
}
