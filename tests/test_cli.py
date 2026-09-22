import os

import pytest

from obulkrename import cli


@pytest.fixture
def files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "JOURNAL", str(tmp_path / "state" / "last.json"))
    monkeypatch.setattr(cli, "files_from_clipboard", list)      # never the real clipboard
    for n in ("my photo.jpg", "my note.txt"):
        (tmp_path / n).write_text(n, encoding="utf-8")
    return tmp_path


def here(tmp_path):
    return sorted(n for n in os.listdir(tmp_path) if not n.startswith(("state", ".")))


def test_a_rule_with_two_arguments(files):
    assert cli.main(["replace", " ", "_", "-y"]) == 0
    assert here(files) == ["my_note.txt", "my_photo.jpg"]


def test_a_rule_with_one_argument_does_not_eat_the_first_file(files):
    """`case upper photo.jpg` must rename photo.jpg, not the whole directory."""
    assert cli.main(["case", "upper", "my photo.jpg", "-y"]) == 0
    assert here(files) == ["MY PHOTO.jpg", "my note.txt"]


def test_a_rule_with_no_arguments_does_not_eat_the_first_file(files):
    assert cli.main(["slug", "my note.txt", "-y"]) == 0
    assert here(files) == ["my photo.jpg", "my-note.txt"]


def test_a_dry_run_changes_nothing(files, capsys):
    assert cli.main(["replace", " ", "_", "-n"]) == 0
    assert here(files) == ["my note.txt", "my photo.jpg"]
    assert "→" in capsys.readouterr().out


def test_a_plan_with_a_collision_is_refused_and_nothing_moves(files, capsys):
    (files / "my_photo.jpg").write_text("in the way", encoding="utf-8")
    assert cli.main(["replace", " ", "_", "-y"]) == 1
    assert "my photo.jpg" in here(files)


def test_undo_after_a_rename(files):
    assert cli.main(["replace", " ", "_", "-y"]) == 0
    assert cli.main(["undo"]) == 0
    assert here(files) == ["my note.txt", "my photo.jpg"]


def test_undo_with_nothing_to_undo(files, capsys):
    assert cli.main(["undo"]) == 1
    assert "Nothing to undo" in capsys.readouterr().out


def test_undo_cannot_be_run_twice(files):
    cli.main(["replace", " ", "_", "-y"])
    cli.main(["undo"])
    assert cli.main(["undo"]) == 1


def test_the_regex_shorthand_is_a_replace_with_patterns_on(files):
    assert cli.main(["regex", r"^my (\w+)", r"\1", "-y"]) == 0
    assert here(files) == ["note.txt", "photo.jpg"]


def test_numbering_the_current_directory(files):
    assert cli.main(["number", "--template", "file-{n}", "-y"]) == 0
    # The order is the order the files come in: "my note.txt" sorts before "my photo.jpg".
    assert here(files) == ["file-01.txt", "file-02.jpg"]


def test_changing_the_extension(files):
    assert cli.main(["extension", "jpeg", "my photo.jpg", "-y"]) == 0
    assert "my photo.jpeg" in here(files)


def test_a_bare_file_list_is_not_read_as_a_rule(files, monkeypatch):
    """`omarchy-bulk-rename *.jpg` opens the menu on those files."""
    seen = {}
    monkeypatch.setattr(cli, "cmd_menu", lambda args: seen.setdefault("files", args.files) and 0)
    cli.main(["my photo.jpg"])
    assert seen["files"] == ["my photo.jpg"]


def test_an_unreadable_regex_is_reported_not_raised(files, capsys):
    assert cli.main(["regex", "(unclosed", "x", "-y"]) == 2
    assert "regular expression" in capsys.readouterr().err


def test_the_files_come_from_the_clipboard_when_none_are_given(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "from clip.txt").write_text("x", encoding="utf-8")
    monkeypatch.setattr(cli, "files_from_clipboard",
                        lambda: [str(tmp_path / "from clip.txt")])
    monkeypatch.setattr(cli, "JOURNAL", str(tmp_path / "state" / "last.json"))
    assert cli.main(["replace", " ", "-", "-y"]) == 0
    assert (tmp_path / "from-clip.txt").exists()
