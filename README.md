# retro: retrospectives of working with Claude Code

English · [Polski](README.pl.md)

A Claude Code plugin that brings an Agile-style continuous improvement process into working with Claude. Every few
working days (recommended: every 2) the retro:

1. **reviews commitments** from previous retros: were they kept and did they have an effect;
2. gathers **evidence** from Claude Code transcripts, git and GitHub (user messages, answers to questions,
   blocks, tool errors, subagents, PRs, CI, size of rules files, tokens and cost at API prices: context, share of
   subagents and Opus, wake-ups of long sessions);
3. assesses **what worked and what did not**, also on the user's side (optional);
4. proposes **at most 5 changes**, preferring mechanisms (tests, hooks, templates) over text-only rules;
5. **implements** the accepted changes in rules files (`CLAUDE.md`, memory, `nauki.md`) and the commitments
   register.

If there has been no retro for 5 working days, a new Claude Code session reminds you (`SessionStart` hook).

## Languages

The retro talks and writes in the language chosen on first run (`jezyk` in `konfiguracja.json`):

- `pl` and `en` have their own templates and script reports;
- any other language: Claude writes in it, templates and script reports are in English.

Recognition does not depend on the language: an option marked as recommended is recognized in many languages
("(Recommended)", „(rekomendowane)”, "(recomendado)", "(empfohlen)", …), a completed retro is `zakończone`,
`completed`, `done` or `closed`, a question about a fact is marked `[fact]` or `[fakt]`.

Identifiers stay Polish in every language: file names in the working directory (`zobowiazania.md`, `nauki.md`,
`konfiguracja.json`), configuration keys, CSV columns, script names and arguments. Code comments are in Polish
too. The glossary is in `plugins/retro/skills/retro/references/konfiguracja.md`.

## Requirements

- Claude Code (CLI or the Code tab of the desktop app), local sessions;
- Python ≥ 3.8 in `PATH` (`python3`, `python` or `py`), standard library only;
- git; optionally `gh` logged in to an account with access to the repositories (PR and CI metrics);
- bash for the reminder hook (on Windows: Git Bash, which Claude Code requires anyway).

## Installation from the GitHub repo (recommended)

1. In Claude Code, on every account and computer where it should work:

   ```
   /plugin marketplace add Voyteck/claude-skill-retro
   /plugin install retro@retro
   ```

   The same from a terminal: `claude plugin marketplace add Voyteck/claude-skill-retro` and
   `claude plugin install retro@retro`.

2. A new session (or `/reload-plugins`).

Your own copy (a fork or a new repo from this package) installs the same way, with `<account>/<repo>` instead of
`Voyteck/claude-skill-retro`. A private repo needs git credentials on that computer (an SSH key or
`gh auth login` and `gh auth setup-git`), and automatic background updates additionally need `GITHUB_TOKEN`.

## Installation without GitHub

A folder with the unpacked package can be a marketplace by itself:

```
/plugin marketplace add C:\path\to\retro-plugin
/plugin install retro@retro
```

Changes in the folder take effect after `/reload-plugins` or in a new session.

## First run

In a Claude Code session write "let's do a retro" or `/retro` (full name: `/retro:retro`). The retro asks about:

- **language** of the retro (recommended: the one you are writing in);
- **mode**: *whole account* (all projects from the transcripts on this computer; working directory e.g.
  `~/retro`, a separate git repo) or *this project* (one repo only; directory `.retro/` in the repo, shared by
  the team);
- assessing the user's side (yes/no) and the working-day calendar (Polish holidays / weekends only).

Then it sets up the working directory and runs **retro zero**: taking stock of the existing lessons (project
memory, `CLAUDE.md`) and the first commitments register for you to accept. Later retros review that register.

## What is inside

```
.claude-plugin/marketplace.json          this repo is a marketplace with one plugin
plugins/retro/.claude-plugin/plugin.json plugin manifest (version)
plugins/retro/hooks/hooks.json           reminder at session start
plugins/retro/skills/retro/SKILL.md      the retro procedure (instructions for Claude)
plugins/retro/skills/retro/scripts/      sygnaly.py, tokeny.py, zbierz_liczby.py, dopisz_metryki.py, zaloz.py, przypomnienie.py,
                                         wspolne.py, teksty.py (script messages per language)
plugins/retro/skills/retro/assets/       templates per language (pl/, en/): retro, register, lessons, directory README;
                                         metryki-naglowek.csv
plugins/retro/skills/retro/references/   konfiguracja.md, sygnaly.md (meaning of the metrics), cennik.json
testy/test_retro.py                      tests on synthetic transcripts
```

## Privacy

The scripts read only local files (`~/.claude/projects/*.jsonl`, repositories) and `gh`; they send nothing.
Transcript extracts go to `dane/` in the working directory, which is outside git. Retro documents contain short
quotes from sessions as evidence: in project mode `.retro/` is committed with the repo, so everyone with access
to the repo sees them.

## Updates

Change the files, bump `version` in `plugins/retro/.claude-plugin/plugin.json`, push. Users:
`/plugin marketplace update retro` (automatic updates are off by default). Before pushing:

```
python -m unittest discover -s testy -v
claude plugin validate . --strict
claude plugin validate plugins/retro --strict
```

## Limitations

- It sees only local sessions; cloud sessions (claude.ai/code) and other computers do not get into the retro
  unless you copy their transcripts and point to them in `transkrypcje_dodatkowe`. Cost means API prices as a
  relative measure (on a subscription the limit is what constrains you, not an amount), computed only from local
  transcripts.
- Claude Code deletes terminal and VS Code transcripts after `cleanupPeriodDays` (30 days by default). Extracts in
  `dane/` remain; for a longer history raise this value in `~/.claude/settings.json`.
- Transcript extracts (`dane/`) are outside git, and strings that look like secrets are masked in them. That is a
  heuristic, not a guarantee: a key pasted into a conversation has to be rotated anyway.
- The transcript format is not a public Claude Code API; when numbers suddenly drop to zero, check the script
  against a fresh transcript.
- The command is `/retro`, full name `/retro:retro` (plugin and skill name). Plain `/retro` works only when no
  other command uses that name: if the account also has its own `retro` skill, `/retro` runs that one and the
  plugin stays under `/retro:retro`; remove the old skill.
- The reminder hook was checked in the CLI and by hand; in the desktop app check whether the reminder appears.
