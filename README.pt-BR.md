# Bulk Rename para o Omarchy

Renomeia um monte de arquivos de uma vez — com pré-visualização antes e desfazer depois. É o
[PowerToys PowerRename](https://learn.microsoft.com/windows/powertoys/powerrename) portado
para o [Omarchy](https://omarchy.org), usando o menu do próprio Omarchy e o botão direito do
Nautilus.

*[Read in English](README.md)*

```bash
omarchy-bulk-rename                       # o menu, nos arquivos que você copiou
omarchy-bulk-rename replace " " _ *.jpg   # uma regra, direto
omarchy-bulk-rename undo                  # devolve o último lote
```

## As regras

| Regra | O que faz |
|---|---|
| `replace <busca> <troca>` | busca e substituição literal |
| `regex <padrão> <troca>` | expressão regular, com `\1` na substituição |
| `prefix <texto>` / `suffix <texto>` | antes do nome / depois dele, antes da extensão |
| `number [início]` | `foto-01`, `foto-02`, … — `--template "{name}-{n}"`, `--pad 3` |
| `case <lower\|upper\|title\|sentence>` | as quatro caixas que todo mundo usa |
| `unaccent` | `ação` → `acao` |
| `slug` | `Relatório Final (2026)` → `relatorio-final-2026` |
| `trim` | junta espaços repetidos e apara as pontas |
| `date [formato]` | a data do próprio arquivo na frente do nome |
| `extension <nova>` | para todos de uma vez |

Opções: `--dry-run` mostra o plano sem mexer em nada, `--ignore-case` e `--first` para o
`replace`, `--target extension|full` para apontar a regra à outra metade do nome.

## De onde vêm os arquivos

1. Dos caminhos que você passar, ou
2. **do que você copiou no gerenciador de arquivos** — selecione no Nautilus, Ctrl+C, rode, ou
3. do diretório em que você está.

Depois de `omarchy-bulk-rename setup`, o Nautilus ganha uma entrada no botão direito:
selecione os arquivos → **Scripts → Bulk rename**.

## Ele não vai perder um arquivo

Esse é o projeto inteiro, e é onde estão os testes:

- **O plano é montado e conferido por completo antes de qualquer coisa se mover.** Dois
  arquivos que terminariam com o mesmo nome, um nome já ocupado por um arquivo que não faz
  parte do lote, uma barra no nome novo, um nome que ficaria vazio ou maior do que o sistema
  de arquivos aceita — basta um desses e **nada** é renomeado, com o motivo impresso por
  arquivo.
- **As renomeações passam por nomes temporários.** Trocar dois nomes entre si, ou empurrar uma
  série numerada para cima (`01→02`, `02→03`), destrói arquivos no meio do caminho se feito do
  jeito óbvio. Aqui cada arquivo é movido para o lado primeiro e para o lugar depois; se o
  sistema de arquivos falhar no meio, o que foi movido é devolvido.
- **A extensão fica intacta** a menos que você peça, e um arquivo oculto é nome, não extensão —
  `.bashrc` continua `.bashrc`.
- **Todo lote é registrado**, então `omarchy-bulk-rename undo` devolve tudo. O desfazer é
  conferido como qualquer outro plano e se recusa se os arquivos tiverem mudado de lugar.

## Instalação

### Arch / Omarchy

```bash
sudo pacman -U omarchy-bulk-rename-*-any.pkg.tar.zst   # dos Releases
omarchy-bulk-rename setup                              # a entrada no botão direito do Nautilus
```

Um atalho, se quiser, no `~/.config/hypr/bindings.lua`:

```lua
o.bind("SUPER + ALT + R", "Bulk rename", "omarchy-bulk-rename")
```

### Em outras distros

```bash
pipx install git+https://github.com/andrebbruno/omarchy-bulk-rename
```

Python 3.11+, e `wl-clipboard` se quiser que ele pegue os arquivos copiados. Fora do Omarchy o
menu cai para o `gum` e, sem ele, para uma lista numerada no terminal.

## Desenvolvimento

```bash
python -m pytest tests -q     # 70 testes
```

`obulkrename/rules.py` tem uma regra por classe, cada uma um `transform(text, index, path)`
puro, e `obulkrename/plan.py` transforma regras mais arquivos em um plano validado antes de
rodar. A pré-visualização do menu é montada a partir do mesmo plano que será executado — não
existe um segundo caminho de código que possa discordar dela.

## Licença

MIT © Andre Bruno
