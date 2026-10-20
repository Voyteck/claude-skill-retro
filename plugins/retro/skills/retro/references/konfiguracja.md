# Konfiguracja retro

Plik `konfiguracja.json` w katalogu roboczym. Zakłada go `scripts/zaloz.py`; brakujące pola biorą wartości
domyślne z `scripts/wspolne.py` (`DOMYSLNA_KONFIGURACJA`). Zmieniaj ręcznie albo przez Claude'a w retro.

| pole | domyślnie | znaczenie |
|---|---|---|
| `tryb` | `konto` | `konto`: wszystkie projekty z transkrypcji na tym koncie; `projekt`: tylko repo, w którym leży `.retro/` |
| `kalendarz` | `PL` | `PL`: polskie święta ustawowe (z Wigilią od 2025); `brak`: wolny tylko weekend |
| `dni_wolne_dodatkowe` | `[]` | dodatkowe dni wolne, np. `["2026-12-31"]` |
| `prog_przypomnienia_dni_roboczych` | `5` | po tylu dniach roboczych bez zakończonego retro hook przypomina |
| `rytm_dni_roboczych` | `2` | zalecany rytm retro (informacyjnie, dla Claude'a) |
| `ocena_wlasciciela` | `true` | czy retro ocenia też decyzje i nawyki użytkownika (sekcja 6) |
| `model_podagentow` | `opus` | model jawnie podawany podagentom analizy |
| `godziny_pracy` | `07:30–17:00`, wieczór do `20:00` | granice pór dnia w statystyce wiadomości |
| `nazwy_projektow` | `[]` | poprawki wykrywania: `[["podciąg ścieżki", "nazwa"]]`, pierwsze dopasowanie wygrywa (np. usunięte worktree obok repo) |
| `pomin_projekty` | `[]` | nazwy projektów wyłączonych z retro |
| `repozytoria_dodatkowe` | `{}` | `{"nazwa": "ścieżka"}`: repo liczone w git/GitHub, nawet bez sesji w oknie |
| `pliki_regul_dodatkowe` | `[]` | dodatkowe pliki reguł do statystyki (np. `docs/claude/*.md`) |
| `katalogi_regul_osobno` | `[]` | katalogi względem korzenia repo (np. `["repo-roots/"]`), których `CLAUDE.md` to kopie dla innych repozytoriów: liczone osobno (`claude_md_linie_osobno`), nie w `claude_md_linie`. Podsumowanie podpowiada kandydatów (katalog z ≥ 3 zagnieżdżonymi `CLAUDE.md`) |
| `transkrypcje_dodatkowe` | `[]` | katalogi z transkrypcjami z innych maszyn (katalog `projects` albo katalog, który go zawiera) |
| `cennik` | `{}` | nadpisania `references/cennik.json`, ten sam kształt: `{"modele": {"claude-x": {"wejscie": 1, "wyjscie": 5, "zapis_5m": 1.25, "zapis_1h": 2, "odczyt": 0.1}}}`, także `mnoznik_fast` i `web_search_za_zapytanie` |
| `rejestry_pytan` | `[]` | pliki z otwartymi pytaniami do ludzi spoza zespołu (sekcja 8a) |
| `gh` | `null` | ścieżka do `gh`, gdy nie ma go w PATH |

## Jak są wykrywane projekty i repozytoria

Każda sesja ma katalog roboczy (`cwd` w transkrypcji). Skrypt pyta git o główny checkout tego katalogu
(`git rev-parse --git-common-dir`), więc worktree trafia do swojego repo. Nazwa projektu = nazwa katalogu repo.
Gdy katalogu już nie ma (usunięty worktree), skrypt szuka najbliższego istniejącego rodzica; jeśli i to nie
pomaga, nazwą jest ostatni człon ścieżki. Wtedy pomaga `nazwy_projektow`. Sesje z folderów tymczasowych aplikacji
desktop (`scratch-workspaces`) idą do projektu `bez-folderu`.

## Katalog Claude Code

Domyślnie `~/.claude`; zmienna `CLAUDE_CONFIG_DIR` go zmienia (skrypty ją respektują). Transkrypcje:
`<katalog>/projects/<zakodowana ścieżka>/<id sesji>.jsonl`, pamięć: `<…>/memory/`.

## Przypomnienie bez pluginu

Gdy skill jest skopiowany ręcznie do `~/.claude/skills/retro/` (bez pluginu), hook trzeba dopisać do
`~/.claude/settings.json` (scal z istniejącymi hookami, nie zastępuj):

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup",
        "hooks": [
          {"type": "command", "command": "<pełna ścieżka do python>",
           "args": ["<pełna ścieżka do ~/.claude/skills/retro/scripts/przypomnienie.py>"], "timeout": 15}
        ]
      }
    ]
  }
}
```

Na Windows `command` musi wskazywać prawdziwy `python.exe` (nie skrót ze Sklepu Microsoft).
