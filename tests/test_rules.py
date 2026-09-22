import pytest

from obulkrename import rules
from obulkrename.rules import (Affix, Case, DateStamp, Extension, Number, Replace, RuleError,
                               Slug, Trim, Unaccent)


def t(rule, text, index=0, path="/tmp/x"):
    return rule.transform(text, index, path)


# ---------------------------------------------------------------- replace

def test_plain_replace():
    assert t(Replace(" ", "_"), "my holiday photo") == "my_holiday_photo"


def test_replace_deletes_when_the_replacement_is_empty():
    assert t(Replace("IMG_"), "IMG_0001") == "0001"


def test_plain_replace_does_not_treat_the_search_as_a_pattern():
    assert t(Replace("a.b", "-"), "a.b and axb") == "- and axb"


def test_plain_replace_does_not_treat_a_backslash_as_a_group():
    """"\\1" in a plain replacement is two characters, not a backreference."""
    assert t(Replace("x", "\\1"), "x") == "\\1"


def test_regex_replace_with_a_group():
    rule = Replace(r"(\d{4})-(\d{2})", r"\2-\1", regex=True)
    assert t(rule, "2026-09 report") == "09-2026 report"


def test_a_broken_regex_is_reported_not_raised_raw():
    with pytest.raises(RuleError) as e:
        Replace("(unclosed", regex=True)
    assert "regular expression" in str(e.value)


def test_case_insensitive_replace():
    assert t(Replace("img", "photo", case_sensitive=False), "IMG_1 img_2") == "photo_1 photo_2"


def test_only_the_first_match():
    assert t(Replace("a", "-", first_only=True), "banana") == "b-nana"


def test_an_empty_search_is_refused():
    with pytest.raises(RuleError):
        Replace("")


# ---------------------------------------------------------------- affix, number

def test_prefix_and_suffix():
    assert t(Affix(prefix="2026-"), "report") == "2026-report"
    assert t(Affix(suffix="-final"), "report") == "report-final"


def test_numbering_counts_from_one_and_pads():
    rule = Number()
    assert [t(rule, "photo", i) for i in range(3)] == ["photo-01", "photo-02", "photo-03"]


def test_numbering_honours_start_step_and_padding():
    rule = Number(start=10, step=5, pad=4)
    assert t(rule, "x", 0) == "x-0010"
    assert t(rule, "x", 2) == "x-0020"


def test_a_number_template_can_put_the_number_first():
    assert t(Number(template="{n} - {name}"), "song", 0) == "01 - song"


def test_a_template_with_no_placeholders_is_taken_as_a_prefix():
    assert t(Number(template="photo"), "whatever", 0) == "photo01"


def test_a_template_naming_only_the_original_still_numbers():
    assert t(Number(template="{name}"), "song", 0) == "song01"


# ---------------------------------------------------------------- case and friends

def test_the_four_cases():
    assert t(Case("lower"), "My File") == "my file"
    assert t(Case("upper"), "My File") == "MY FILE"
    assert t(Case("title"), "my file") == "My File"
    assert t(Case("sentence"), "MY FILE HERE") == "My file here"


def test_title_case_does_not_mangle_apostrophes_or_accents():
    assert t(Case("title"), "don't stop") == "Don't Stop"
    assert t(Case("title"), "ação final") == "Ação Final"


def test_an_unknown_case_is_refused():
    with pytest.raises(RuleError):
        Case("sPoNgEbOb")


def test_unaccent_keeps_everything_else():
    assert t(Unaccent(), "Relatório Ação 2026") == "Relatorio Acao 2026"


def test_slug():
    assert t(Slug(), "Relatório Final (2026).v2") == "relatorio-final-2026-v2"


def test_slug_never_produces_an_empty_name():
    assert t(Slug(), "!!!") == "file"


def test_trim_collapses_spaces_and_strips_trailing_dots():
    assert t(Trim(), "  my    file . ") == "my file"


def test_extension_replaces_the_whole_part():
    assert t(Extension("jpg"), "jpeg") == "jpg"
    assert t(Extension(".png"), "jpeg") == "png"


# ---------------------------------------------------------------- date

def test_date_uses_the_files_own_time(tmp_path):
    import os
    import time
    f = tmp_path / "note.txt"
    f.write_text("x", encoding="utf-8")
    os.utime(f, (time.mktime((2026, 9, 22, 12, 0, 0, 0, 0, -1)),) * 2)
    assert t(DateStamp(), "note", path=str(f)) == "2026-09-22 note"


def test_a_missing_file_is_reported_rather_than_crashing():
    with pytest.raises(RuleError):
        t(DateStamp(), "note", path="/nowhere/at/all")


def test_a_broken_date_source_is_refused():
    with pytest.raises(RuleError):
        DateStamp(source="yesterday")


def test_every_rule_in_the_catalogue_can_be_built_with_no_arguments():
    for name, factory in rules.CATALOGUE.items():
        if name == "replace":
            continue                                  # needs something to search for
        rule = factory()
        assert hasattr(rule, "transform")
