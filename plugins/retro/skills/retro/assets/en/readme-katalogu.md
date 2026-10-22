# Retro: working directory

State of the retrospectives on how we work with Claude Code. The mechanism (procedure, scripts, templates) is the
`retro` plugin; this directory holds only results and the state between retros. Start a retro with `/retro` (full
name `/retro:retro`) or by asking “let's do a retro”.

File names, configuration keys and CSV columns are Polish identifiers; the glossary is in the plugin:
`references/konfiguracja.md`.

| file | role |
|---|---|
| `konfiguracja.json` | configuration: mode, language, calendar, reminder threshold, project name fixes (fields described in the plugin: `references/konfiguracja.md`) |
| `zobowiazania.md` | commitments register: the backbone of continuity between retros |
| `retro/RNN-YYYY-MM-DD.md` | successive retros; `**Status:** completed` resets the reminder counter |
| `metryki.csv` | trend metrics, one row per retro |
| `nauki.md` | (account mode) cross-project lessons |
| `dane/` | extracts from transcripts, **outside git** (session content) |
