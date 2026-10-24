---
name: retro
description: Agile-style retrospective of how the user works with Claude Code (user + Claude + subagents), usually every 2 working days. Reviews commitments from previous retros (were they kept, were they worth it), gathers evidence from Claude Code transcripts, git and GitHub, assesses what worked and what did not (including on the user's side), proposes at most 5 changes for the user to decide and implements the accepted ones. On first use it sets up a working directory (whole account or one project) and asks for the language. Use when the user asks for a retro, retrospective, retrospektywa, lessons learned, a review of lessons, "what are we doing well and what badly" („co robimy dobrze, a co źle”), "are we sticking to our agreements" („czy trzymamy się ustaleń”), continuous improvement, or when a reminder about an overdue retro got the user's consent.
---

# Retro

Goal: a closed loop **commitment → compliance → effect → decision**, not a list of observations. Every retro
starts by reviewing what was agreed before.

## Places

- **Skill:** `${CLAUDE_SKILL_DIR}` (`scripts/`, `assets/`, `references/`). Run scripts with
  `python "${CLAUDE_SKILL_DIR}/scripts/<script>.py"` (or `python3`; Python ≥ 3.8, standard library only).
  On Windows `python` and `python3` are often Microsoft Store stubs ("Python was not found"): use `py` then.
- **Working directory** (state between retros, always outside the skill):
  - **account** mode: all projects from the transcripts on this account; the directory is pointed to by
    `~/.claude/retro.json`;
  - **project** mode: one repo; directory `<repo>/.retro/`, committed with the project, shared by the team.

  Contents: `konfiguracja.json`, `retro/RNN-YYYY-MM-DD.md`, `zobowiazania.md` (register), `metryki.csv`,
  `nauki.md` (account mode), `dane/` (transcript extracts, outside git). File names, configuration keys and CSV
  columns are Polish identifiers; glossary: `references/konfiguracja.md`.
- Scripts: `wspolne.py` (state detection), `zaloz.py` (directory setup), `sygnaly.py` (evidence from the window),
  `tokeny.py` (price list, token archive and trend; used by `sygnaly.py`), `zbierz_liczby.py` (numbers from
  another machine's transcripts for the trend), `dopisz_metryki.py` (a `metryki.csv` row),
  `przypomnienie.py` (reminder hook), `teksty.py` (script messages per language and language-independent
  recognition). Configuration fields: `references/konfiguracja.md`. Meaning and limits of
  the metrics: `references/sygnaly.md`; prices for cost metrics: `references/cennik.json`.
- Templates: `assets/<jezyk>/` (`pl`, `en`). For a language without its own templates use `assets/en/` and
  translate headings and labels while filling them in.

## Standing rules

1. **Evidence or nothing.** Every "good", "bad" and compliance assessment points to evidence: `MM-DD HH:MM` + the
   first 8 characters of the session id (from the timeline in `dane/sygnaly-*/<project>.md`), a PR number, a
   commit hash or a file.
2. **You assess yourself too, so no flattery.** Look for broken commitments first, confirmations second. For
   "kept", give the number of opportunities and breaches, not an adjective.
3. **The user's side honestly**, when `ocena_wlasciciela` in the configuration is on: assess their decisions and
   habits like Claude's work, in terms of cost and effect (time, interrupted work, correction rounds), not the
   person.
4. **Fewer rules, not more.** At most 5 new commitments per retro. With more than 10 active, the retro must
   propose at least one establishing or dropping. Every recommendation says what it replaces or shortens.
5. **Mechanism over text.** Rules with a mechanism (test, hook, branch protection, template, pinned agent model)
   are kept; text-only rules that need a habit usually die. When proposing a change, look for a mechanism first;
   propose a text-only rule only when there is no mechanism.
6. **The user decides.** Proposals become commitments only after the user accepts them. Ask with the
   AskUserQuestion tool (if available; otherwise a numbered list in the message), recommended option first,
   marked as recommended in the user's language ("(Recommended)", „(rekomendowane)”). **One question = one
   independent decision.** Put the proposal and any step to perform into the question itself, because the text
   above the widget is sometimes not visible.
7. **The retro does not change product code** and does not run heavy tests. It changes rules (CLAUDE.md, memory,
   register, `nauki.md`), and only after the user decides.
8. **Language.** Everything meant for the user (chat, questions and options, the retro file, the register,
   rules, briefs for sessions) is in the language from `jezyk` in the configuration (`pl` when the field is
   missing), plain, without jargon where an ordinary word exists. These instructions are in English; that does
   not change the output language.

## Step 0. Detection and first run

1. `python "${CLAUDE_SKILL_DIR}/scripts/wspolne.py"` prints JSON: working directory, mode, configuration, last
   completed retro, next number.
2. **No directory** (`katalog_roboczy: null`) = first run. Ask separate questions, the language first:
   - language: the language the user is writing in (recommended) / English / another;
   - mode: "Whole account (recommended when one person works in many projects)" / "This project (retro in the
     repo, shared by the team)";
   - in account mode, the directory: `~/retro` (recommended) / other;
   - assessing the user's side: "Yes, honestly (recommended)" / "Only the work of Claude and agents";
   - working-day calendar, recommended by the user's country: Polish public holidays (`PL`) or weekends only
     (`brak`).

   Then `python "${CLAUDE_SKILL_DIR}/scripts/zaloz.py" --tryb konto --katalog <dir> --jezyk <code>
   [--kalendarz brak] [--bez-oceny-wlasciciela]` or `--tryb projekt --repo <repo> --jezyk <code>`. Show what was
   created. If the skill is not installed as a plugin, the reminder does not work by itself: propose a hook as in
   `references/konfiguracja.md`, section "Reminder without the plugin".
3. Account mode: the session should work in the working directory (move it with a change-directory tool if there
   is one; otherwise use absolute paths). Project mode: the session works in the project repo.
4. Number `N` = `nastepny_numer`. File `retro/RNN-YYYY-MM-DD.md` from `assets/<jezyk>/szablon-retro.md`, with the
   draft status (`**Status:** szkic` / `draft`). If an unfinished draft exists, ask: finish it or replace it.
5. Window: from the day of the last **completed** retro (inclusive) to today. `sygnaly.py` itself starts it at the
   time of the commit that completed that retro, so events before it do not count towards the review. Skill
   arguments ("only project X", "since 2026-10-06") narrow the window or the scope.

**Retro zero** (no completed retros, empty register): window from the oldest transcript. Instead of reviewing the
register, take stock of the existing lessons: `feedback` entries in project memory
(`~/.claude/projects/*/memory/`), the global `~/.claude/CLAUDE.md` and sections about working with Claude in
repositories' CLAUDE.md. Treat them as implicit commitments: kept? effective? duplicated across projects?
contradictory? dead? The result is the first register (at most 10 active) for the user to accept.

## Step 1. Data

```
python "${CLAUDE_SKILL_DIR}/scripts/sygnaly.py" --od YYYY-MM-DD
```

Output in `<working dir>/dane/sygnaly-<from>_<to>/`: `podsumowanie.md`, `metryki.json`, `<project>.md`
(timeline). Reports are in the configured language (English for languages other than `pl`). Read the summary and
the metrics, compare with `metryki.csv`. Answer classes and the limits of the numbers: `references/sygnaly.md`.
The heuristic correction marker (`[C?]`, in Polish reports `[K?]`) is a hint, not evidence.

Tokens and cost of local sessions are computed by the script (the summary section "Tokens and cost" („Tokeny
i koszt”): cost at API prices as a relative measure, cost per message, context, subagents, wake-ups, startup
context); do not analyse tokens by hand. For the trend take `koszt_na_wiadomosc_usd`, `kontekst_mediana`,
`kontekst_ponad_200k_proc`, `podagenci_opus_koszt_proc`, `wybudzenia` and `kontekst_startowy_mediana`; the most
expensive sessions and wake-ups listed in the summary are evidence for the "what did not work" section. Each wake-up
has its cause (the user's message, a background task or subagent, another session, other): propose a remedy that
fits the cause, e.g. a hook on the user's message does not help against wake-ups by background tasks. Local
tokens do not cover work in a sandbox or in the cloud: when the repo has usage records from those environments
(e.g. an export from another tool), take the cost per merged PR from them.

Also read the "Token trend" („Trend tokenów”) section: week by week from `tokeny-tydzien.csv` (the script appends
new weeks and overwrites the incomplete one), the last 4 weeks against the median of the 8 earlier ones. Put an
indicator marked **↑ worse** („↑ pogorszenie”) into "what did not work" with the numbers from the table and look
for the cause in the window's most expensive sessions; "not enough data" („za mało danych”) is not a signal. Before
reporting an arrow, check the last column (the current, unfinished week): when a fix made this week already shows
there, say the arrow describes the state before the fix. Rows
from other sources (e.g. `zrodlo=sandbox`) have their own table; do not add them to the local ones. A remote
source from the configuration (`zrodla_zdalne`) is read once by the script; when the summary shows "not read"
(„brak odczytu”), do not retry the connection or probe the machine. Give the user a ready command to run
themselves (`references/sygnaly.md`, "Remote sources": output to a file and the `plik` field) and compute the
trend from what is in the archive.

The summary contains notes about the data (paragraphs starting **Note:** / **Uwaga:**); take them into account
before quoting numbers:
a window longer than transcript retention, a repo checkout behind its remote branch (rules on disk out of date),
projects with memory but no sessions in the window, repos with commits but no local sessions (sandbox, cloud: the
per-message and per-session numbers do not see that work), directories with copies of `CLAUDE.md` (candidates for
`katalogi_regul_osobno`; adding them is the user's decision), models without a price in the price list. Secrets in
timelines are masked (`[redacted]`, in Polish reports `[zamazane]`), but that is a heuristic: if you still see a
key or password, do not copy it into the retro file or into subagent tasks, only report it in section 8a as
something to rotate.

## Step 2. Analysis

- **Small window** (up to ~40 user messages in total): analyse it yourself.
- **Larger:** `general-purpose` subagents with the explicit model `model_podagentow` from the configuration, in
  parallel, one per project with activity plus one cross-cutting (collaboration, the user's side, contradictions
  between projects). Each gets the project timeline path, `zobowiazania.md`, the project's rules files, the
  "Standing rules" section, the output language and the task:
  1. for each active commitment: opportunities, breaches, evidence, whether it had an effect;
  2. what worked / what did not, with evidence and cause;
  3. observations about the user's side (if assessment is on);
  4. contradictory and dead rules;
  5. at most 3 candidate recommendations, each with a compliance signal and a mechanism, if there is one.

  The subagent writes its analysis to `dane/sygnaly-…/analiza-<scope>.md` and returns ≤300 words. It may search
  the full transcript (`~/.claude/projects/*/<session>.jsonl`) with `grep` by session id and time, without
  loading it whole. Subagents' questions come back in their reports; you ask the user.

## Step 3. Synthesis

Fill in the retro file according to the template. Commitments review:

| field | values |
|---|---|
| kept | yes / partly (x of y opportunities) / no / no opportunity |
| worth it | yes / no / too early (too few opportunities) |
| verdict | keep / change / establish / drop |

- **establish** = kept without breaches in 3 consecutive retros → stays in the rules file, the register stops
  tracking it (spot check once every 5 retros);
- **drop** = no effect or cost greater than gain → also remove it from the rules files;
- **change** = good idea, the form does not work → a new commitment replaces the old one.

Before you call something dead or propose "drop" (a rule, directory, script, hook, page), ask the user whether
anyone uses it: no trace in transcripts does not mean nobody uses it (cloud work, other people, rare use; e.g. a
directory with a website generated outside sessions). Ask in step 4 together with the verdict, or earlier when the
analysis depends on the answer.

**Waiting for the user** (template section 8a). Collect, with evidence and a "since" date:
- questions deferred in the window (class `odlozone` in the timelines) that did not come back;
- PRs open for more than 2 working days (`gh pr list` in the repositories from the summary) and unpushed branches
  (`git log --branches --not --remotes`);
- handoff notes (`HANDOFF*`, "to do" memory entries) with no session in the project for more than 10 working days;
- open questions from the `rejestry_pytan` files in the configuration, older than 30 days;
- items from section 8a of the previous retro that were not closed.

The retro does not do these things itself; you ask about each item in step 4.

**Convention to offer:** a question about a fact only the user knows ("which network are you on?") has no
recommended option by nature. Starting the question with `[fact]` (or `[fakt]`) makes the signals count it
in its own class, not as a missing recommendation or a correction. If unmarked fact questions distort the numbers,
propose the convention as a rule for the user's rules file.

## Step 4. User decisions

Up to 4 questions per call, one question = one independent decision (combine only proposals that depend on each
other). Order: recommendations and status changes, then rule clean-up, finally "waiting for the user". Labels
below are in English; write them in the user's language.
- keeping a commitment without a status change: `Keep (recommended)` / `Change: …` / `Drop`;
- a verdict that changes the status, a new recommendation, a removal from the rules: `Accept (recommended)` /
  `Change: …` / `Reject`;
- a "waiting for the user" item: `Do it now (in a project session)` / `Close` / `Postpone to <date>`.
  "Do it now" = a task for a project session with full context, not retro work. When there is a tool for starting
  sessions (e.g. `start_session`, `spawn_task`), propose it right away as a card (a proposal the user starts with
  one click), do not wait for separate consent to start: in a turn triggered by an automated event (a subagent
  notification, a message from another session) the app only allows proposing a card, and a card cannot point to
  another folder. So the brief starts with "Go to `<full project path>` (change-directory tool or absolute paths)
  before you begin" and carries all the needed context (evidence, files, what "done" means). Without such a tool,
  write the brief in section 10 of the retro for copying.
  When there are more than 8 items (usually retro zero), combine into one question the items of the same project
  that would go into one task; always ask about security matters (rotations, keys, passwords) separately.

Record the answers in section 9 of the retro, the user's own answers verbatim.

## Step 5. Implementation

1. `zobowiazania.md`: new `Z-NNN` entries (format in the file header), an assessment row in the table of each
   reviewed one, status changes.
2. Rules:
   - **account mode:** general ones (all projects) → `~/.claude/CLAUDE.md`, briefly, with the `Z-NNN` number;
     cross-cutting knowledge (pitfalls of the computer and tools) → `nauki.md`; with the first entry, propose one
     line in `~/.claude/CLAUDE.md` pointing to `nauki.md`, because project memory loads only in its folder;
   - **project rules:** the repo's CLAUDE.md according to its rules (if changes go through PRs: branch
     `retro/rNN-<topic>` in a separate worktree and a PR);
   - project memory (`~/.claude/projects/*/memory/`) → a `feedback` entry with a `Z-NNN` reference, without
     duplicating content from `nauki.md`.
3. `metryki.csv`: `python "${CLAUDE_SKILL_DIR}/scripts/dopisz_metryki.py" --retro RNN --zobowiazania <active>`
   (a row from the latest `metryki.json`; it appends columns missing from a newer plugin version at the end of the
   header).
4. In the retro: section 10 (what, where, commit or PR), status completed (`**Status:** zakończone` /
   `completed`; this resets the reminder counter).
5. Commit: account mode in the working directory; project mode in the repo (according to its rules),
   `retro(RNN): <most important change>`. The commit also includes `tokeny-tydzien.csv` (trend); the archive
   `dane/tokeny-archiwum.json` stays outside git.

## Step 6. Closing

In the chat, 5–8 sentences: the most important conclusion, what was accepted, what changes from tomorrow, a link
to the retro file.

## Maintenance

The installed copy of the plugin is overwritten on update: do not change the skill there, only in the plugin repo
(test: `python -m unittest discover -s testy` in the repo). A change the retro finds necessary goes into section
10 of the retro as a proposal for the plugin repo. Write scripts and content with backslashes using the Write
tool, not a bash heredoc.
