# Bulk Rename for Omarchy

Rename a pile of files at once — with a preview first and an undo after. A port of
[PowerToys PowerRename](https://learn.microsoft.com/windows/powertoys/powerrename) to
[Omarchy](https://omarchy.org), using Omarchy's own menu and Nautilus' right-click.

*[Leia em português](README.pt-BR.md)*

```bash
omarchy-bulk-rename                       # the menu, on the files you copied
omarchy-bulk-rename replace " " _ *.jpg   # one rule, straight away
omarchy-bulk-rename undo                  # put the last batch back
```

## The rules

| Rule | What it does |
|---|---|
| `replace <find> <with>` | plain search and replace |
| `regex <pattern> <with>` | a regular expression, with `\1` in the replacement |
| `prefix <text>` / `suffix <text>` | before the name / after it, before the extension |
| `number [start]` | `photo-01`, `photo-02`, … — `--template "{name}-{n}"`, `--pad 3` |
| `case <lower\|upper\|title\|sentence>` | the four everyone actually wants |
| `unaccent` | `ação` → `acao` |
| `slug` | `Relatório Final (2026)` → `relatorio-final-2026` |
| `trim` | collapse runs of spaces, strip the ends |
| `date [format]` | the file's own date in front of the name |
| `extension <new>` | for all of them at once |

Options: `--dry-run` shows the plan and changes nothing, `--ignore-case` and `--first` for
`replace`, `--target extension|full` to point a rule at the other half of the filename.

## Where the files come from

1. The paths you give it, or
2. **what you copied in the file manager** — select files in Nautilus, Ctrl+C, run it, or
3. the directory you are standing in.

After `omarchy-bulk-rename setup`, Nautilus gets a right-click entry: select files →
**Scripts → Bulk rename**.

## It will not lose a file

That is the whole design, and it is where the tests are:

- **The plan is built and checked in full before anything moves.** Two files that would end
  up with the same name, a name already taken by a file that is not part of the batch, a
  slash in a new name, a name left empty or longer than the filesystem allows — any one of
  them and *nothing* is renamed, with the reason printed per file.
- **Renames go through temporary names.** Swapping two names, or shifting a numbered series
  up by one (`01→02`, `02→03`), destroys files halfway through if you do it the obvious way.
  Here every file is moved aside first and into place second; if the filesystem fails
  mid-way, what was moved aside is put back.
- **The extension is left alone** unless you ask for it, and a dotfile is a name, not an
  extension — `.bashrc` stays `.bashrc`.
- **Every batch is journalled**, so `omarchy-bulk-rename undo` puts it back. Undo is checked
  the same way as any other plan, and refuses if the files have moved on since.

## Install

### Arch / Omarchy

```bash
sudo pacman -U omarchy-bulk-rename-*-any.pkg.tar.zst   # from Releases
omarchy-bulk-rename setup                              # the Nautilus right-click entry
```

A keybinding, if you want one, in `~/.config/hypr/bindings.lua`:

```lua
o.bind("SUPER + ALT + R", "Bulk rename", "omarchy-bulk-rename")
```

### Elsewhere

```bash
pipx install git+https://github.com/andrebbruno/omarchy-bulk-rename
```

Python 3.11+, and `wl-clipboard` if you want it to pick up the files you copied. Outside
Omarchy the menu falls back to `gum`, then to a plain numbered prompt.

## Development

```bash
python -m pytest tests -q     # 70 tests
```

`obulkrename/rules.py` is a rule per class, each a pure `transform(text, index, path)`, and
`obulkrename/plan.py` turns rules plus files into a plan that is validated before it runs.
The preview in the menu is built from the same plan that is executed — there is no second
code path that could disagree with it.

## License

MIT © Andre Bruno
