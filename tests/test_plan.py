import os

import pytest

from obulkrename import plan as planning
from obulkrename.plan import Rename, build, execute, split_name, undo
from obulkrename.rules import Affix, Case, Extension, Number, Replace, RuleError, Slug


def make(tmp_path, *names):
    paths = []
    for n in names:
        p = tmp_path / n
        p.write_text(n, encoding="utf-8")
        paths.append(str(p))
    return paths


def names(tmp_path):
    return sorted(os.listdir(tmp_path))


# ---------------------------------------------------------------- splitting

def test_the_rule_sees_the_name_without_the_extension():
    assert split_name("/a/b/photo.jpg", "name")[1:] == ("photo", ".jpg")


def test_a_file_with_no_extension():
    assert split_name("/a/README", "name")[1:] == ("README", "")


def test_a_dotfile_is_a_name_not_an_extension():
    """Otherwise a bulk rename quietly turns .bashrc into bashrc."""
    assert split_name("/a/.bashrc", "name")[1:] == (".bashrc", "")


def test_only_the_last_dot_separates():
    assert split_name("/a/archive.tar.gz", "name")[1:] == ("archive.tar", ".gz")


def test_targeting_the_extension():
    directory, part, rest = split_name("/a/photo.jpeg", "extension")
    assert part == "jpeg" and rest == "photo"


def test_targeting_the_whole_filename():
    assert split_name("/a/photo.jpg", "full")[1:] == ("photo.jpg", "")


# ---------------------------------------------------------------- building

def test_a_plain_plan(tmp_path):
    paths = make(tmp_path, "my photo.jpg", "my note.txt")
    plan = build(paths, Replace(" ", "_"))
    assert plan.ok
    assert {os.path.basename(r.dst) for r in plan.changes} == {"my_photo.jpg", "my_note.txt"}


def test_the_extension_is_left_alone_by_default(tmp_path):
    paths = make(tmp_path, "Photo.JPG")
    plan = build(paths, Case("lower"))
    assert os.path.basename(plan.changes[0].dst) == "photo.JPG"


def test_the_extension_can_be_the_target(tmp_path):
    paths = make(tmp_path, "photo.jpeg")
    plan = build(paths, Extension("jpg"), target="extension")
    assert os.path.basename(plan.changes[0].dst) == "photo.jpg"


def test_files_that_do_not_change_are_not_renamed(tmp_path):
    paths = make(tmp_path, "already_fine.txt", "not fine.txt")
    plan = build(paths, Replace(" ", "_"))
    assert len(plan.changes) == 1


def test_two_files_that_would_collide_are_refused(tmp_path):
    paths = make(tmp_path, "a b.txt", "a_b.txt")
    plan = build(paths, Replace(" ", "_"))
    assert not plan.ok
    assert "would both become" in plan.problems[0]


def test_an_existing_file_in_the_way_is_refused(tmp_path):
    make(tmp_path, "taken.txt")
    paths = make(tmp_path, "free.txt")
    plan = build(paths, Replace("free", "taken"))
    assert not plan.ok
    assert "already exists" in plan.problems[0]


def test_a_slash_in_the_new_name_is_refused(tmp_path):
    paths = make(tmp_path, "report.txt")
    plan = build(paths, Replace("report", "sub/report"))
    assert not plan.ok
    assert "contains" in plan.problems[0]


def test_an_empty_new_name_is_refused(tmp_path):
    paths = make(tmp_path, "gone.txt")
    plan = build(paths, Replace("gone", ""))
    assert not plan.ok


def test_a_name_that_is_too_long_is_refused(tmp_path):
    paths = make(tmp_path, "x.txt")
    plan = build(paths, Affix(prefix="ção" * 100))
    assert not plan.ok
    assert "too long" in plan.problems[0]


def test_a_rule_that_fails_on_one_file_names_that_file(tmp_path):
    from obulkrename.rules import DateStamp
    paths = make(tmp_path, "here.txt")
    paths.append(str(tmp_path / "gone.txt"))           # never created
    plan = build(paths, DateStamp())
    assert not plan.ok
    assert "gone.txt" in plan.problems[0]


def test_an_unknown_target_is_refused(tmp_path):
    with pytest.raises(RuleError):
        build(make(tmp_path, "a.txt"), Case("lower"), target="middle")


# ---------------------------------------------------------------- executing

def test_executing_renames_the_files(tmp_path):
    paths = make(tmp_path, "my photo.jpg", "my note.txt")
    execute(build(paths, Replace(" ", "_")))
    assert names(tmp_path) == ["my_note.txt", "my_photo.jpg"]


def test_a_swap_does_not_lose_a_file(tmp_path):
    """a→b and b→a at once: without temporary names, one of them is overwritten."""
    paths = make(tmp_path, "a.txt", "b.txt")
    plan = build(paths, Replace("a", "TMP"))          # not a swap yet; build one by hand
    plan.renames = [Rename(paths[0], paths[1]), Rename(paths[1], paths[0])]
    execute(plan)
    assert names(tmp_path) == ["a.txt", "b.txt"]
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "b.txt"
    assert (tmp_path / "b.txt").read_text(encoding="utf-8") == "a.txt"


def test_shifting_a_numbered_series_keeps_every_file(tmp_path):
    paths = make(tmp_path, "01.txt", "02.txt", "03.txt")
    plan = planning.Plan(renames=[
        Rename(paths[2], str(tmp_path / "02.txt")),
        Rename(paths[1], str(tmp_path / "01.txt")),
        Rename(paths[0], str(tmp_path / "00.txt")),
    ])
    execute(plan)
    assert names(tmp_path) == ["00.txt", "01.txt", "02.txt"]


def test_a_plan_with_problems_is_never_executed(tmp_path):
    paths = make(tmp_path, "a b.txt", "a_b.txt")
    plan = build(paths, Replace(" ", "_"))
    with pytest.raises(RuleError):
        execute(plan)
    assert names(tmp_path) == ["a b.txt", "a_b.txt"]


def test_nothing_to_do_is_not_an_error(tmp_path):
    paths = make(tmp_path, "fine.txt")
    assert execute(build(paths, Replace("zzz", "x"))) == []


def test_no_temporary_files_are_left_behind(tmp_path):
    paths = make(tmp_path, "a.txt", "b.txt")
    execute(build(paths, Affix(prefix="x")))
    assert not [n for n in os.listdir(tmp_path) if n.startswith(".obulkrename")]


# ---------------------------------------------------------------- journal and undo

def test_the_journal_survives_a_round_trip(tmp_path):
    paths = make(tmp_path, "ação.txt")
    journal = str(tmp_path / "state" / "last.json")
    execute(build(paths, Slug()), journal)
    back = planning.read_journal(journal)
    assert len(back) == 1
    assert back[0].dst.endswith("acao.txt")


def test_undo_puts_the_files_back(tmp_path):
    paths = make(tmp_path, "my photo.jpg", "my note.txt")
    journal = str(tmp_path / "state" / "last.json")
    execute(build(paths, Replace(" ", "_")), journal)
    assert names(tmp_path) == ["my_note.txt", "my_photo.jpg", "state"]

    execute(undo(planning.read_journal(journal)))
    assert names(tmp_path) == ["my note.txt", "my photo.jpg", "state"]


def test_undo_refuses_when_a_file_moved_on(tmp_path):
    paths = make(tmp_path, "one.txt")
    journal = str(tmp_path / "state" / "last.json")
    execute(build(paths, Affix(prefix="new-")), journal)
    os.rename(tmp_path / "new-one.txt", tmp_path / "somewhere-else.txt")
    plan = undo(planning.read_journal(journal))
    assert not plan.ok


def test_a_missing_journal_is_not_an_error(tmp_path):
    assert planning.read_journal(str(tmp_path / "nothing.json")) == []


def test_a_corrupt_journal_is_not_an_error(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{not json", encoding="utf-8")
    assert planning.read_journal(str(p)) == []


# ---------------------------------------------------------------- numbering end to end

def test_numbering_follows_the_order_the_files_were_given(tmp_path):
    paths = make(tmp_path, "c.jpg", "a.jpg", "b.jpg")
    plan = build(sorted(paths), Number(template="photo-{n}"))
    assert [os.path.basename(r.dst) for r in plan.changes] == \
        ["photo-01.jpg", "photo-02.jpg", "photo-03.jpg"]
