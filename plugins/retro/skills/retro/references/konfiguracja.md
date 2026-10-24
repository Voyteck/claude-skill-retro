# Retro configuration

The file `konfiguracja.json` in the working directory. Created by `scripts/zaloz.py`; missing fields take their
defaults from `scripts/wspolne.py` (`DOMYSLNA_KONFIGURACJA`). Change it by hand or through Claude during a retro.

| field | default | meaning |
|---|---|---|
| `jezyk` | `pl` when the field is missing (configurations from before 0.2.0); `zaloz.py --jezyk` defaults to `en` | language of the retro: chat, retro files, script reports and the reminder. `pl` and `en` have their own templates and script messages; any other code (e.g. `de`) uses English templates and messages, and Claude writes in that language |
| `tryb` | `konto` | `konto` (account): all projects from the transcripts on this account; `projekt` (project): only the repo containing `.retro/` |
| `kalendarz` | `PL` | `PL`: Polish public holidays (with Christmas Eve from 2025); `brak` (none): only weekends are days off |
| `dni_wolne_dodatkowe` | `[]` | extra days off, e.g. `["2026-12-31"]` |
| `prog_przypomnienia_dni_roboczych` | `5` | after this many working days without a completed retro the hook reminds |
| `rytm_dni_roboczych` | `2` | recommended retro rhythm (informational, for Claude) |
| `ocena_wlasciciela` | `true` | whether the retro also assesses the user's decisions and habits (section 6) |
| `model_podagentow` | `opus` | model passed explicitly to analysis subagents |
| `godziny_pracy` | `07:30–17:00`, evening until `20:00` | boundaries of the times of day in the message statistics |
| `nazwy_projektow` | `[]` | detection fixes: `[["path substring", "name"]]`, the first match wins (e.g. deleted worktrees next to the repo) |
| `pomin_projekty` | `[]` | names of projects excluded from the retro |
| `repozytoria_dodatkowe` | `{}` | `{"name": "path"}`: repos counted in git/GitHub even without sessions in the window |
| `pliki_regul_dodatkowe` | `[]` | extra rules files for the statistics (e.g. `docs/claude/*.md`) |
| `katalogi_regul_osobno` | `[]` | directories relative to the repo root (e.g. `["repo-roots/"]`) whose `CLAUDE.md` files are copies for other repositories: counted separately (`claude_md_linie_osobno`), not in `claude_md_linie`. The summary suggests candidates (a directory with ≥ 3 nested `CLAUDE.md`) |
| `transkrypcje_dodatkowe` | `[]` | directories with transcripts from other machines (a `projects` directory or a directory containing one) |
| `cennik` | `{}` | overrides of `references/cennik.json`, same shape: `{"modele": {"claude-x": {"wejscie": 1, "wyjscie": 5, "zapis_5m": 1.25, "zapis_1h": 2, "odczyt": 0.1}}}`, also `mnoznik_fast` and `web_search_za_zapytanie` |
| `zrodla_zdalne` | `[]` | remote sources for the token trend: `[{"nazwa": "sandbox", "polecenie": ["ssh", "-T", "host", "python3 -"]}]` or `{"nazwa": …, "plik": "dane/sandbox-liczby.json"}`; optionally `wlaczone`, `limit_s`; since 0.3.0 also agent events for the efficiency section: `zdarzenia_polecenie` (gets `scripts/zdarzenia_agentow.py` on stdin) or `zdarzenia_plik`. Details: `references/sygnaly.md`, "Weekly trend" and "Tokens and writing efficiency" |
| `rejestry_pytan` | `[]` | files with open questions to people outside the team (section 8a) |
| `gh` | `null` | path to `gh` when it is not in PATH |
| `role_agentow` | `{}` (= built-in) | agent roles by subagent type, regular expressions, first match wins: `{"implementacja": ["programista", "implement", "developer", "coder", "engineer"], "przeglad": ["przeglad", "przegląd", "review", "tester", "qa", "audit"], "ci": ["obserwator", "\\bci\\b", "watch"], "architekt": ["architekt", "architect"]}`; the main session is `sesja`, an unmatched subagent `inne`. A custom role name is shown as is |
| `efektywnosc_tygodnie` | `6` | weeks back in the cost-by-role and fix-round tables |
| `pr_przerwa_rundy_min` | `20` | a break between commit batches in a PR longer than this starts a new fix round |
| `pr_max_commitow` | `40` | PRs with more commits are skipped (branch merges, batches) |
| `pr_pomin_galezie` | `["integration/", "batch/"]` | head branch prefixes skipped in fix rounds (integration batches) |
| `pr_progi_rozmiaru` | `[50, 300]` | PR size buckets in lines (additions + deletions): S up to the first, M up to the second, L above (since 0.4.0) |

## Glossary of identifiers

File names, configuration keys, CSV columns, script arguments and script names are Polish and stay so in every
language (backward compatibility of existing working directories). Text inside the files follows `jezyk`.

| identifier | meaning |
|---|---|
| `konfiguracja.json` | configuration |
| `zobowiazania.md`, `Z-NNN` | commitments register, commitment number |
| `nauki.md` | cross-project lessons |
| `metryki.csv`, `metryki.json` | trend metrics (per retro), metrics of one window |
| `tokeny-tydzien.csv`, `dane/tokeny-archiwum*.json` | weekly token trend, numbers-only archive |
| `dane/`, `dane/sygnaly-<from>_<to>/` | transcript extracts (outside git), output of one `sygnaly.py` run |
| `podsumowanie.md`, `analiza-<scope>.md` | summary of the signals, subagent analysis |
| `retro/RNN-YYYY-MM-DD.md` | one retro; `**Status:** szkic`/`draft` → `zakończone`/`completed` (also accepted: `zakonczone`, `done`, `closed`) |
| `tryb` `konto` / `projekt` | mode: account / project |
| `kalendarz` `PL` / `brak` | calendar: Polish holidays / none |
| `wlasciciel`, `wiad_wlasciciela` | owner (the user), user's messages |
| `pyt_*` | answers to AskUserQuestion: `rekomendowana` recommended, `inna` other option, `wlasna` own text, `odlozone` dismissed, `bez_wyboru` no preference, `fakt` fact question, `bez_rekomendacji` without a recommended option |
| `koszt`, `kontekst`, `podagenci`, `wybudzenia`, `kompakty` | cost, context, subagents, wake-ups, compactions |
| `commity_bez_sesji`, `pr_bez_sesji` | commits / PRs without a local session |
| `zrodlo`, `zrodla_zdalne`, `polecenie`, `plik` | source, remote sources, command, file |
| `--od`, `--do`, `--projekt`, `--katalog`, `--jezyk` | from, to, project, directory, language |

## How projects and repositories are detected

Every session has a working directory (`cwd` in the transcript). The script asks git for the main checkout of
that directory (`git rev-parse --git-common-dir`), so a worktree lands in its repo. Project name = name of the repo
directory. When the directory no longer exists (deleted worktree), the script looks for the nearest existing
parent; if that does not help either, the name is the last path component. `nazwy_projektow` helps then. Sessions
from the desktop app's temporary folders (`scratch-workspaces`) go to the project `bez-folderu` (no folder).

## Claude Code directory

`~/.claude` by default; the `CLAUDE_CONFIG_DIR` variable changes it (the scripts respect it). Transcripts:
`<dir>/projects/<encoded path>/<session id>.jsonl`, memory: `<…>/memory/`.

## Reminder without the plugin

When the skill is copied by hand to `~/.claude/skills/retro/` (without the plugin), the hook has to be added to
`~/.claude/settings.json` (merge it with existing hooks, do not replace them):

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup",
        "hooks": [
          {"type": "command", "command": "<full path to python>",
           "args": ["<full path to ~/.claude/skills/retro/scripts/przypomnienie.py>"], "timeout": 15}
        ]
      }
    ]
  }
}
```

On Windows `command` must point to a real `python.exe` (not the Microsoft Store shortcut).
