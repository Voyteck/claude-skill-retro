# Caveman: compressing context files

Files that Claude Code loads into every session or subagent are paid for in every call: the global and project
`CLAUDE.md`, agent definitions, memory, `nauki.md`, the user's own skills and commands. Written for a human reader,
they carry articles, filler, hedging and polite connectives that the model does not need. Caveman style keeps
the substance and drops the rest. The retro does it itself, with the rules below; the `caveman` plugin is not needed
and is not installed.

**Not compressed:** files of the retro plugin and of any installed plugin (`<Claude Code dir>/plugins/`, overwritten
on update anyway), files outside the context (README, docs for people, the retro files, the register), and patterns
from `caveman_pomin` in the configuration. The retro document, the register and everything written for the user stay
in plain language (standing rule 8).

## Levels (`caveman` in the configuration)

| level | what goes | example (en) | example (pl) |
|---|---|---|---|
| `lekki` (lite) | filler, hedging, pleasantries, repetitions; full sentences stay | "Run tests before every commit." | „Uruchamiaj testy przed każdym commitem.” |
| `standard` (default) | also articles, copulas, connectives; fragments, imperatives, short synonyms, `→` for cause and effect | "Tests before every commit." | „Testy przed każdym commitem.” |
| `ultra` | also conjunctions; common abbreviations (cfg, repo, fn, PR, CI), `→`, `=`, `≠`, `+` instead of words; one line per rule | "Commit → tests first." | „Commit → najpierw testy.” |
| `wyl` (off) | nothing; the summary only shows sizes | | |

Starting sentence for all examples: "You should always remember that it is important to run the tests before every
single commit." / „Należy zawsze pamiętać o tym, że testy warto uruchamiać przed każdym commitem.”

## What always stays (the script checks it)

`caveman.py sprawdz` compares the file with its backup and refuses to record the compression when anything here
was lost:

- the YAML header (`---` … `---`) byte for byte: `name`, `description`, `model`, `effort`, `tools`. An agent's
  `description` decides routing; it changes only by an agent-selection decision (section 2a), never by compression;
- fenced code blocks byte for byte; inline code (`` `…` ``) as a set;
- URLs, file paths, numbers and dates, identifiers (`Z-012`, `R07`, `PR-12`), words in capitals (`NEVER`, `NIGDY`,
  `MUST`, `IMPORTANT`);
- headings (level and text: other files link to them) and the number of rows of every table (cells may be shortened).

A drop in the number of negations ("not", "never", „nie”, „bez”, „żaden”) is a **warning**: read every changed rule
and make sure no prohibition turned into permission.

## What also stays (the script cannot check it: you do)

- every condition, exception and threshold ("only when", "unless", „chyba że”, „tylko gdy”);
- the order of steps in a procedure;
- the one-clause reason of a rule ("why"), shortened, not removed: a rule without a reason gets applied where it does
  not fit;
- `Z-NNN` references and links to other files;
- quotes the user wrote verbatim (their wording is the rule);
- the language of the file: a Polish file stays Polish, an English one English.

## How to compress

- English: drop articles (a, an, the), "you should", "please", "make sure to", "it is important that", "in order
  to" → "to", "basically", "just", "really", "actually", "note that". Imperative or noun phrase instead of a sentence.
- Polish: drop „należy”, „warto”, „pamiętaj, że”, „trzeba”, „jest to”, „w celu” → „by”, „w przypadku gdy” → „gdy”,
  „aby” → „by” where it reads well, „ten/ta/to” used as an article. Bare infinitive or noun phrase: „Testy przed
  commitem.” „Bez pushowania na `main`.”
- Merge repeated rules into one; a list item that only repeats a heading goes.
- Keep markdown structure: headings, lists, tables. A long paragraph → a list of short items.
- Compressing does not change meaning: no new rules, no dropped rules, no reordering of priorities. A rule that looks
  dead or wrong is a proposal for the retro (section 7), not something to fix while compressing.

## Procedure (step 5 of the retro)

1. `python "${CLAUDE_SKILL_DIR}/scripts/caveman.py" lista` → the files accepted by the user (list from the latest
   signals; states: not compressed, changed after compression, another level).
2. `caveman.py kopia --retro RNN <files>` → backup in `dane/caveman/RNN/` (outside git). An existing backup is kept:
   it is the original. Never write a backup next to the file: a `.md` in `.claude/agents/` or `memory/` would load as
   an agent or memory.
3. Rewrite each file at the configured level (Edit/Write). Many or large files: one `general-purpose` subagent per
   batch with the explicit model `model_podagentow`, this file and the list of paths.
4. `caveman.py sprawdz --retro RNN <files>` → for each file: `ok`, errors, warnings, tokens before and after. Exit
   code 1 = a file has errors: fix it (restore the lost part) and run again. Only a file without errors is recorded
   in `caveman.csv` (working directory, committed).
5. Rollback: `caveman.py przywroc --retro RNN <files>` (from the backup, row removed from the register).
6. Files in repositories with their own rules (PRs, branch protection): as other rule changes, branch
   `retro/rNN-caveman` and a PR; the check runs before the commit.

## Measure

- `pliki_kontekstu_tokeny` (sum of context files, characters / 4) and `caveman_do_kompresji_tokeny` in `metryki.csv`;
- `kontekst_startowy_mediana`: the fixed overhead of a session start should fall by roughly the tokens saved in the
  global files;
- quality: compliance with the compressed rules in the next retros (the commitments review) and
  `wiad_mozliwa_korekta`. A rule broken after compression and not before → restore its fuller form (`przywroc` or a
  manual edit) and note the exception in `caveman_pomin` when the whole file needs it.
