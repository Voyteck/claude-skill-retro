# Signals and metrics: what they mean and what they do not say

`scripts/sygnaly.py` reads Claude Code transcripts from the retro window, git and (when `gh` is available)
GitHub. Reports (`podsumowanie.md`, timelines) are written in the configured language (`jezyk`: `pl` in Polish,
anything else in English); metric names and CSV columns are the same in every language.

## Window

The window starts at the **time of the commit** that gave the previous retro its completed status (`**Status:**
zakończone` / `completed`; also accepted: `zakonczone`, `done`, `closed`). The script looks for that commit in the
working directory's git when `--od` is the day that retro was completed. Messages, questions and errors from that
retro's own session before the commit therefore do not inflate the new window (without this, a retro session can
easily double the question count of the next window). The same window applies to commits, PRs, CI and tokens.
`--od YYYY-MM-DDTHH:MM` gives the time explicitly, `--od-poczatku-dnia` counts from midnight. A retro that is not
committed or lives outside git: window from midnight (the summary says where the start came from).

## Answer classes for questions (AskUserQuestion)

| class | meaning |
|---|---|
| `rekomendowana` | the option marked as recommended was chosen; the mark is recognized in many languages (rekomendowane, zalecane, recommended, recomendado, recommandé, empfohlen, raccomandato, aanbevolen, …) unless negated |
| `inna` | another option from the list was chosen |
| `wlasna` | the user typed their own answer outside the options: often a change of direction, read it in the timeline |
| `odlozone` | the question was closed without an answer ("[User dismissed …]") |
| `bez_wyboru` | the answer "[No preference]" |
| `fakt` | a question starting with `[fact]` or `[fakt]` (leading spaces allowed): about a fact only the user knows (e.g. "which network are you on?"); the answer, even as own text, is not a correction. Since 0.2.1 the marker counts only at the start: a decision that quotes "[fakt]" in its text is an ordinary question |
| `bez_rekomendacji` | the question had no option marked as recommended (fact questions excluded since 0.1.3) |

The share of `rekomendowana` shows how well Claude predicts the user's decisions. `wlasna` and `odlozone` are the
most interesting places to read in the timeline.

## Metrics (`metryki.json`, `metryki.csv` columns)

| metric | source | note |
|---|---|---|
| `wiad_wlasciciela` | messages typed by the user | without `/…` commands, notifications and messages between sessions; including those sent while Claude was working (`queued_command` records, marked as such in the timeline); since 0.2.2 also those the app prefixes with a `<system-reminder>` block (the block is stripped first), so the count is higher than in earlier retros in sessions with side sessions |
| `wiad_mozliwa_korekta` | words like "no", "why", "again" (Polish and English lists) | a heuristic with a lot of noise; trend only. Marked `[K?]` (pl) / `[C?]` (en) in timelines |
| `wiad_po_20` | messages outside working hours (`godziny_pracy`) | |
| `pytania`, `pyt_*` | answers to AskUserQuestion | see the classes above |
| `przerwania` | "Request interrupted by user" | counted only when the transcript recorded this marker |
| `blokady_klasyfikatora` | refusals by the auto mode classifier (sessions and subagents) | |
| `odmowy_wlasciciela` | rejected requests for tool permission | |
| `bledy_narzedzi` | tool results with an error | the most frequent ones in the project timeline |
| `kompakty` | context compactions | |
| `podagenci` | Agent/Task calls | separately: requested and actual model (from the subagent's transcript) |
| `wiad_miedzy_sesjami` | SendMessage | |
| `commity`, `pr_*`, `ci_*` | git (all branches) and `gh` | commits/PRs counted from the 40 most recently merged PRs (GraphQL limit) |
| `claude_md_linie` | total lines of rules files: `~/.claude/CLAUDE.md`, tracked `CLAUDE.md` at any depth of the repo, `CLAUDE.local.md`, `pliki_regul_dodatkowe`; without directories from `katalogi_regul_osobno` | growing = rules bloat; counted from disk, so out of date when the checkout is behind its remote (column "behind remote") |
| `pamiec_pliki` | project memory files | |

Columns since 0.1.3 (in `metryki.csv` at the end, after `zobowiazania_aktywne`; older rows have them empty):

| metric | source | note |
|---|---|---|
| `okno_od_godzina` | window start (see "Window") | `00:00` = from midnight |
| `pyt_fakt`, `pyt_bez_wyboru` | answer classes | `pyt_bez_wyboru` was in `metryki.json` since 0.1.0, in the CSV since 0.1.3 |
| `wywolania_api` | unique `message.id` in the window, sessions and subagents | see "Tokens and cost" |
| `koszt_api_usd` | tokens × API prices from `references/cennik.json` | relative measure, lower bound |
| `koszt_na_wiadomosc_usd` | `koszt_api_usd` / `wiad_wlasciciela` | comparable between retros when the price list is the same |
| `znaki_do_wlasciciela_na_wiadomosc` (since 0.7.2) | median characters of main-session text (without tool calls) between consecutive user messages; replies with tools only are skipped | direct measure of the communication style; output tokens are mostly tool calls and thinking |
| `znaki_promptu_agenta` (since 0.7.2) | median length of `prompt` of `Agent`/`Task` calls in the main session | measure of the style of messages to agents |
| `tokeny_wyjscia_na_wiadomosc` | output tokens of the window (main session and subagents) / `wiad_wlasciciela` | measure of the communication style (since 0.7.1); depends on the kind of work, so compare within one machine and over several retros |
| `kontekst_mediana` | median context (input + cache write + cache read) of main-session calls | context size × number of calls is the main cost |
| `kontekst_ponad_200k_proc` | share of main-session calls with context > 200k | |
| `kontekst_startowy_mediana` | median context of the first call of sessions started in the window | fixed overhead: system prompt, tools, skills, MCP, CLAUDE.md, memory; a session with copies of another session's calls (fork) is excluded |
| `podagenci_koszt_proc` | subagents' share of the cost | |
| `podagenci_opus_koszt_proc` | Opus's share of the subagents' cost | counting subagents by number misleads: Opus is often a minority of subagent calls and the majority of their cost |
| `wybudzenia`, `wybudzenia_koszt_usd` | main-session calls with a cache write > 50k after a break > 1 h since its previous call; cost of the write alone | a closing question ("can I archive?") to a long session, or a background task finishing hours later; listed in the summary with the cause |
| `commity_bez_sesji`, `pr_bez_sesji` | commits (committer time) and opened PRs without a local transcript of a session in that repo within ±30 min | work in a sandbox, cloud, another machine, merges on GitHub; the summary warns when it is ≥ 20% (and ≥ 3 commits or ≥ 2 PRs) |
| `claude_md_linie_osobno` | lines of rules files in `katalogi_regul_osobno` | e.g. copies of `CLAUDE.md` kept in one repo for future repositories |
| `wybudzenia_wlasciciel`, `wybudzenia_tlo`, `wybudzenia_sesja`, `wybudzenia_inne` (since 0.2.1) | `wybudzenia` split by the first input after the break: the user's message; a background task or subagent (`<task-notification>`, `queue-operation`, "[Subagent hand-back]"); another session (`peer`, `<agent-message>`, `<cross-session-message>`, `<side-sessions-event>`, a system reminder about sessions); anything else (e.g. a tool result after a long foreground wait or API retries) | a hook on the user's message (`UserPromptSubmit`) can only act on the first kind; system reminders the app prepends to a message are skipped when classifying |
| `wybudzenia_odpowiedz` (since 0.7.2) | wake-ups by the user's answer to `AskUserQuestion` (a tool result of that tool), earlier counted as `wybudzenia_inne` | a question asked right before a long break costs a full cache write when answered: ask before the break is likely, or end the turn without a question |
| `pr_analizowane`, `pr_z_poprawka_proc`, `rundy_na_pr` (since 0.3.0) | PRs merged in the window on GitHub (repos of the window with a remote), the share with at least one fix round, mean rounds per PR | see "Tokens and writing efficiency"; empty without `gh` |
| `pr_wg_modelu`, `pr_z_poprawka_proc_wg_modelu` (since 0.3.0) | the same by author model, as text `Opus:71;Fable:27` (share of PRs, % with a fix) | `bez stopki` = no `Co-Authored-By: Claude` trailer |
| `powroty_przeglad`, `powroty_ci` (since 0.3.0) | returns of an implementer to the same PR after a negative review or red CI, local transcripts plus remote agent events | the main session fixing its own PR is not a return |
| `koszt_implementacji_proc_wg_modelu` (since 0.3.0) | model families' share of implementation subagents' cost in the window, `Opus:90;Sonnet:10` | role by `role_agentow` |
| `pr_powiazane`, `koszt_na_pr_usd` (since 0.4.0) | PRs merged in the window with an implementation subagent found in transcripts; their mean agent cost (implementation, review, CI, fix rounds included) | the expected cost of an accepted PR; main-session cost excluded |
| `koszt_na_pr_wg_konfiguracji` (since 0.4.0) | the same by implementer configuration, `Opus/high:6.68;Sonnet/medium:1.20` | compare configurations within one PR size in the summary table, not in this sum |
| `koszt_wg_poziomu` (since 0.4.0) | reasoning efforts' share of the window cost, `high:80;xhigh:18;?:2` | `?` = calls without a recorded effort |
| `narzedzia_wywolania`, `odrzucenia`, `odrzucenia_na_100` (since 0.5.0) | `tool_use` blocks in the window (main session and subagents); tool results the harness refused; refusals per 100 tool calls | above 2 per 100 the summary prints a signal |
| `odrzucenia_wg_przyczyny`, `niepowodzenia_wg_przyczyny` (since 0.5.0) | refusals and failures by cause, `klasyfikator:3;worktree:2` | causes in "Tool calls: refused and failed" |
| `chmura_koszt_usd`, `chmura_sesje`, `chmura_nowe` (since 0.5.0) | cloud sessions' cost in the window from `--chmura`, how many sessions, how many read for the first time | empty without `--chmura`; first readings may include cost from before the window |
| `plan_uzyty_proc`, `koszt_na_10proc_planu`, `wiad_na_10proc_planu`, `pr_scalone_na_10proc_planu` (since 0.5.0) | the share of the plan the window used (`--plan-uzyty`) and cost (local + cloud), owner messages and merged PRs per 10% of the plan | the only totals that compare between windows of different lengths |
| `agenci_zdefiniowani`, `agenci_nieuzywani` (since 0.6.0) | agent definitions in `.claude/agents` of the window's repositories and `~/.claude/agents`; those without a run in the window | an unused agent: description too narrow, role not needed or work on another machine |
| `agenci_zmiany_od_retro` (since 0.6.0) | agent files that differ from the last snapshot in `agenci.csv` | changes made outside the retro (or waiting in a PR at the last snapshot) |
| `pr_bez_agenta_proc` (since 0.6.0) | share of PRs merged in the window without an implementation subagent | main session or work outside the visible transcripts; empty without `gh` |
| `pliki_kontekstu`, `pliki_kontekstu_tokeny` (since 0.6.0) | context files (rules, agents, memory, `nauki.md`, custom skills and commands) and their size in characters / 4 | plugin files excluded; compared with previous retros (more = worse) |
| `caveman_do_kompresji`, `caveman_do_kompresji_tokeny` (since 0.6.0) | those not compressed at the configured level (never, changed after compression, another level) | empty with `caveman`: `wyl` |
| `ops_koszt_usd`, `ops_glowna_koszt_usd`, `ci_glowna_koszt_usd` (since 0.8.0) | cost of CI and deploy/ops calls in the window (main session and subagents), of those in main sessions, of CI calls in main sessions | see "CI and deploy steps" |
| `ops_glowna_proc` (since 0.8.0) | `ops_glowna_koszt_usd` / `koszt_api_usd` | rule Z-012 headline; compared with previous retros (more = worse) |
| `ops_podagenci_proc` (since 0.8.0) | subagents' share of the ops cost | more = better (not in the comparison, which assumes more = worse) |
| `ops_glowna_wg_projektu` (since 0.8.0) | main-session ops share of each project's cost, `minos:33;blog:29` (projects with ≥ $0.50 main-session ops) | trend per project across retros |
| `ops_kandydaci_audytu` (since 0.8.0) | projects flagged for a project-agents audit (operator role) | criteria in "CI and deploy steps" |
| `kohorta_od`, `kohorta_do`, `kohorta_pr` (since 0.9.0) | the cohort of the outcome measures: first and last merge day, PRs | see "Outcome measures"; empty without `gh` |
| `akceptacja_proc`, `akceptacja_proc_wg_impl`, `pr_przerobione_30d` (since 0.9.0) | % of the cohort accepted (no fix round, no rework within 30 days), the same by implementer configuration `Opus/high:80;sesja główna:50`, reworked PRs | more = better (not in the comparison, which assumes more = worse) |
| `koszt_na_zaakceptowany_usd`, `wiad_na_zaakceptowany`, `uwaga_h_na_zaakceptowany` (since 0.9.0) | cohort window cost (all sources) per accepted PR; owner messages and attention hours (estimate) per accepted PR | the first two are compared with previous retros (more = worse) |
| `szczelnosc_proc`, `bledy_zlapane_agenci`, `bledy_po_akceptacji`, `bledy_produkcja`, `szczelnosc_proc_wg_recenzenta` (since 0.9.0) | verification tightness of the cohort and its parts; by reviewer configuration `Sonnet/high:75` | a heuristic, a hint not evidence |
| `zadania_na_sesje_mediana`, `sesje_ponad_150_zadan` (since 0.8.0) | median API calls of a main session (the whole session, also before the window, for sessions with main-session calls in the window); sessions over 150 | rule Z-012: handoff after ~150 requests; the median is compared with previous retros |

## CI and deploy steps: main session vs subagents (since 0.8.0)

`scripts/operacje.py`, summary section „Kroki CI i deploy: sesja główna a podagenci”, `operacje.json` in the output
directory (rows per project).

- **Classifier.** Each `tool_use` of `Bash` or `PowerShell` (main session and subagents) is matched on its `command`:
  CI = `\bgh (run|workflow|pr checks)\b`; deploy/ops =
  `\b(ssh|scp|rsync|docker|compose|systemctl|journalctl|ansible|kubectl|deploy\w*|wrangler|terraform|certbot|nginx|caddy|apt(-get)?|ufw|sftp)\b`
  (case-insensitive). A command
  matching both is CI. An API call (unique `message.id`, deduplicated like "Tokens and cost") is an ops call when any
  of its commands matches; with both kinds it is deploy. The **whole** cost of the call counts: that is what a main
  session with a large context pays when it watches CI or logs into a server itself.
- **Heuristic.** `grep deploy`, `cat nginx.conf` or a path with `docker` also match. Compare projects and retros, not
  the absolute amount.
- **Per project:** cost, CI / deploy cost in main sessions and in subagents, main-session ops share of the project's
  cost, sessions, median and count of sessions over 150 calls, ops agents of the project.
- **Ops agent** = an agent definition in the project's `.claude/agents` whose `name` or file name contains
  `operator`, `obserwator`, `ci-watch`, or a `ci` / `ops` / `deploy…` segment (Z-012 roles `obserwator-ci`,
  `operator`). Agents in `~/.claude/agents` are listed separately and do not clear a project.
- **Audit candidate** (project-agents skill, operator role), only for projects with a repo and an ops cost from
  `ops_prog_usd` (default $1): main-session ops share > `ops_prog_proc` (default 10%), no ops agent in the project,
  or no ops agent on Haiku.

## Tool calls, cloud sessions and the plan (since 0.5.0)

Taken over from the `claude-usage-report` skill, which retro replaces.

- **Refused and failed tool calls.** Every `tool_result` with `is_error` (and every classifier or rejection message)
  is classified; the first matching cause wins. Refusals: worktree guard ("isolated in the worktree", "too complex to
  verify"), auto mode classifier, user rejected, blocked foreground sleep, hook, permission rule, other "Blocked".
  Failures: Edit/Write without a prior Read ("has not been read yet", "modified since read"), command exit code, tool
  input error (`<tool_use_error>`), file not found, other. Main session and subagents are counted separately;
  questions (AskUserQuestion) are not tool errors. The older columns `blokady_klasyfikatora`, `odmowy_wlasciciela`
  and `bledy_narzedzi` stay as before.
- **Cloud sessions.** `--chmura FILE` takes `[{"id", "title", "cost_usd"}]` with each session's lifetime cost from the
  Remote MCP `get_session` (`external_metadata.usage.cost_usd`). `dane/chmura-archiwum.json` keeps every reading with
  its time; the window cost of a session is its cost now minus its last reading before the window start, so rerunning
  the script for the same window gives the same result. A session without an earlier reading counts whole and is
  marked "first reading".
- **Plan.** `--plan-uzyty PCT` (the share of the plan the user says the window used) scales cost (local + cloud),
  owner messages and merged PRs to 10% of the plan.

## Tokens and writing efficiency

The summary section "Tokens and writing efficiency" („Tokeny i efektywność pisania”) is data for the mandatory
section 2a of the retro document.

- **Results against previous retros (since 0.7.0):** the table for the closing message (`SKILL.md`, step 6). The last 3
  rows of `metryki.csv` give only the windows (start, end, cloud cost); each window ends at the latest where the next
  starts, so a retro day does not count twice. Everything else is recomputed now by one definition: cost and tokens
  from the trend archives of all sources (current model prices of the family, like the week columns; cloud is a separate
  row), PRs from the fix-round data, merged in the window. So the numbers can differ from old `metryki.csv` rows. Cost
  per merged PR = the window's whole cost / merged PRs, unlike `koszt_na_pr_usd` (agent cost of PRs with attributed
  agents). A window older than the start of the tables (`efektywnosc_tygodnie`) has "—" for PR rows. `*` = fewer than 5
  PRs; such samples have no direction and do not enter the median.
- **Normalised rows (since 0.8.3):** windows differ in length and in intensity, so the table adds rows that compare
  across them. "Per working day": cost and merged PRs divided by the window's working days (calendar from the
  configuration, at least 1, so an evening or weekend window counts as one day). "At a fixed size mix": % of PRs with a
  fix and rounds per PR with each size's (S/M/L) result weighted by one mix, the sum of all PRs of the table's windows
  (stated under the table); "—" when a window has no PR of a size in the mix. A shift towards large PRs raises the raw
  % with a fix without any change in quality (R08: raw 42.2% "worse", 41.7% at R07's mix against R07's 50%); the
  direction of the fixed-mix rows is the one to report. Totals (cost, tokens, merged PRs) stay as context.
- **The retro window (since 0.7.0):** the window row of fix rounds, the window column of the cost table, the window table
  of cost and quality per PR, and `metryki.csv` use one filter (`w_oknie`: merged in `[start, end)`) over the same
  records as the weeks. The window and the weeks are different cuts of the same PRs: a week starts on Monday, so a
  weekend PR falls into the previous week; when the window spans weeks the summary gives the split.
- **Possible move to another repo (since 0.7.0):** a note for a week touching the window whose cost across sources is at least
  `ostrzezenie_koszt_tygodnia_usd`, with no merged PRs in tracked repos or a cost per PR at least 3 times the median of
  the other weeks. It is a question to check, not a finding: a week of really expensive PRs fires it too.
- **Reading date of agent events (since 0.7.0):** for each remote source with events, a note gives the reading time, the
  last event (local time) and how many of the window's PRs have no implementer, how many of them merged after the last
  event. Events end at the moment of reading, so a stale reading raises `pr_bez_agenta_proc` by itself.
- **Against previous retros:** `koszt_na_wiadomosc_usd`, `kontekst_mediana`, `kontekst_ponad_200k_proc`,
  `kontekst_startowy_mediana`, `podagenci_opus_koszt_proc`, `wybudzenia_koszt_usd`, `pr_z_poprawka_proc`,
  `rundy_na_pr`, `powroty_przeglad`, `powroty_ci`, `koszt_na_pr_usd` from the last 3 rows of `metryki.csv` (a row of the same window,
  when the script is rerun after `dopisz_metryki.py`, is skipped) and now; the arrow compares now with the median of
  the previous ones (more than 20% = arrow; more = worse for every indicator). Retros from before a metric existed
  show "—".
- **Cost by role and model:** from the trend archives (local and every remote source), week by week for
  `efektywnosc_tygodnie` weeks, at the prices of the current models of each family (like `koszt_api_usd_ceny_55`).
  The role comes from the subagent type: remote archives (`zbierz_liczby.py`) have it since 0.1.5, the local archive
  since 0.3.0; older local subagent calls whose transcripts are gone count as "other subagents". Since 0.4.0 rows
  also carry the reasoning effort (`effort` of each assistant record: low, medium, high, xhigh, max); the local
  archive and `zbierz_liczby.py` store it as `eff`, calls without it (older transcripts, remote reads made with an
  older `zbierz_liczby.py`) have no effort in the label.
- **Fix rounds in merged PRs:** `gh api graphql` (search, 40 PRs per page, at most 25 pages per repo, since 0.9.0 (10 before): the search limit of 1000; `gh pr list
  --json commits` exceeds the GraphQL node limit). Commits sorted by author date (robust to rebase), without merge
  commits; a batch after a break longer than `pr_przerwa_rundy_min` is a round. The author model is the most frequent
  model of the first batch. A commit's model: with an `Agent: <name>` trailer (optional convention, since 0.7.2) the
  `model` of that agent's definition on the commit date (`agenci.csv` snapshots and current definitions; the first
  snapshot from that day unless the file changed later, otherwise the last earlier one); without the trailer, or for
  an unknown or `inherit` agent, the `Co-Authored-By: Claude <Model>` trailers. An agent copying the trailer from a
  template signs with the session's model, so the `Agent:` trailer is recommended; the summary lists PRs where both
  trailers disagree. Skipped: branches with prefixes from
  `pr_pomin_galezie`, PRs with more than `pr_max_commitow` commits. "Who wrote the fix commits" pairs the author model
  with the model of each fix commit.
- **Returns in transcripts:** `scripts/zdarzenia_agentow.py` reads subagent starts (`Agent`/`Task`: type, resolved
  model, PR numbers from the description or prompt), continuations (`SendMessage` to an agent id) and reports
  (synchronous result or "[Subagent hand-back]"). From a report of a review agent it reads the verdict (PL/EN
  patterns such as "Verdict: GO/MERGE/NO-GO/FIX", „Można scalić: tak/nie”, „nie blokuje”), from a CI agent the result
  per PR. Only numbers and labels leave the script. A return = an implementation agent started or continued on the
  same PR in the same session after a negative review or red CI. Remote machines: `zdarzenia_polecenie` /
  `zdarzenia_plik` in an entry of `zrodla_zdalne` (one attempt, no retries, like the token sources), e.g.
  `cmd /c 'ssh -T <host> python3 - < <skill>/scripts/zdarzenia_agentow.py > <working dir>/dane/<name>-zdarzenia.json'`.
- **Cost and quality per PR by implementer configuration (since 0.4.0):** each subagent's cost is computed from the
  token sums of its transcript (current model prices of the family, without the long-context surcharge) and split
  evenly over the PRs it worked on (PR numbers from its task and from continuations). A PR is matched by (repo, number):
  local sessions get the repo from their working directory; sessions of a remote source have no repo, so their PRs
  match by number only when the number is unique among the merged PRs read from GitHub. The configuration is the
  model and effort of the PR's first implementation agent (effort: the most frequent one in its transcript, else the
  `effort` requested in the call). Size = additions + deletions from GitHub, buckets `pr_progi_rozmiaru` (S ≤ 50,
  M ≤ 300, L > 300 lines). Cost per PR = the mean of the agents' cost over the PRs in the cell: it already contains
  the fix rounds with their frequency, so it is the expected cost of an accepted PR. A PR implemented by the main
  session ("main session" row) has quality and control cost only. The section also lists the current agent
  definitions from `.claude/agents/*.md` of the window's repositories and `~/.claude/agents` (`name`, `model`,
  `effort` from the header) with their role, so a proposed rule can name the file to change.
- **Agents between retros (since 0.6.0):** `agenci.py`. The current definitions (header `name`, `model`, `effort`,
  `description`; a hash of the description and of the body; the date of the file's last commit, without git its
  modification) are compared with the snapshot `agenci.csv`, which `dopisz_metryki.py` writes at the end of every
  retro: the state after the retro's changes (`RNN`) and, when it differs from the last row (or, for an agent without
  rows, from the state after the retro), the state at its start (`RNN-start`, from `agenci.json` of the signals). A
  difference between consecutive rows of an agent is a change; a difference between the last row and the file now is
  a change "since the last retro". Effect: the PRs the agent worked on (by subagent type = agent name, also
  `plugin:name`), split by the date of the agent's first work on the PR into before and after the change; the day of
  the change is skipped. Only changes newer than the start of the tables (`efektywnosc_tygodnie`) have the effect.
  Task routing: the first implementer of each merged PR (else "main session") by size, and runs by subagent type in
  the window (custom definition, built-in, not here).
- **Limits:** a round is not always a return from the tester (rebase, conflicts of integration batches, the owner's
  remarks); a missing trailer makes the author "no trailer"; verdicts and CI results are a heuristic on free text and
  the role of an agent depends on its type name; a main session that implements and fixes by itself has no returns
  and no cost per PR; PRs whose task never mentions their number get no cost; with fewer than 5 PRs in a cell the
  comparison between configurations is a hint only.

## Outcome measures (since 0.9.0)

The summary section "Outcome measures" („Miary wyniku”, `scripts/wynik.py`) and three rows of "Results against previous
retros". Until 0.8.x the retro measured the process before merge (fix rounds, returns from review and CI); these
measures look at what happened to the code after merge. No new data from the user: GitHub, the local clone,
agent events and owner message times.

- **Cohort:** PRs merged in `[end − 2·wynik_dni, end − wynik_dni)` (default 30–60 days before the end of the window),
  because only after `wynik_dni` days is it known whether a change came back. Each window of the results table has its
  own cohort (rolling cohorts, neighbours overlap). PR data is fetched from the start of the oldest cohort; the weekly
  and window tables still use only `efektywnosc_tygodnie`. The GraphQL query also reads the title, the body (only PR
  numbers are kept), the files (first 100) and the merge commit.
- **1. Acceptance:** % of the cohort's PRs with no fix round and not reworked within `wynik_dni` days. Reworked = a later
  PR in the same repo that (a) refers to it as fixed: "fix/fixes/hotfix/revert/follow-up/popraw…/napraw… #N" (also
  "follow-up to #N", "poprawka do #N", a `/pull/N` link), or (b) is a fix-type PR (title starting `fix`, `hotfix`,
  `bugfix`, `revert`, `popraw`, `napraw`, also `fix(scope):`) that mentions `#N` or changes its lines: `git diff -U0`
  of the fix's merge commit against its first parent, then `git blame -L` on that parent hits one of the PR's commits
  or its merge commit (squash and merge commits are found; a rebase merge with new hashes is not). Blame needs the
  merge commits in the local clone; the section counts fixes checked, without a clone and without the commit (`git
  fetch`, then rerun). A fix whose blame hits lines of more than `wynik_zamiatanie_pr` (default 3) different PRs is a
  sweep (dependency bump, code removal, a move: R08 smoke, ops#209 removed 17k lines of 8 PRs): its blame is ignored,
  its references count. Paths in `wynik_pomin_sciezki` (default `CLAUDE.md`, `AGENTS.md`, `docs/`: rule copies synced
  across repos) are skipped. By implementer configuration (model · effort of the first implementation agent, as in the
  cost table) and PR size.
- **2. Cost per accepted change:** the cost of the cohort window from the trend archives of all sources (abandoned
  PRs and sessions without a PR included) / accepted PRs; next to it the cost per merged PR. Owner messages in the
  cohort window (local transcripts, the same count as `wiad_wlasciciela`) per accepted change, and the attention time:
  the sum of gaps between consecutive owner messages (all sessions together) up to `wynik_uwaga_przerwa_min` minutes,
  labelled an estimate.
- **3. Verification tightness:** caught by agent review / (caught by agent review + caught after review approval +
  production). Caught by review = an implementer started or continued on the PR after a negative review verdict (the
  returns already counted). After approval = an implementer started or continued after a positive verdict with no red
  CI in between (usually the owner's request after the review passed; sometimes a conflict or rebase). Production = a
  rework from measure 1 (reference or blame) merged within `wynik_hotfix_h` hours after the merge; the merge stands in
  for the deploy. (A first draft counted any fix-type PR on the same files: on ops 27 catches for 33 PRs, noise from
  shared files.) By reviewer configuration (model · effort of the last review agent with a verdict;
  PRs without one form their own row). Returns from red CI are neither.
- **Results table:** rows "acceptance (30–60 day cohort)", "cost per accepted change (cohort)", "verification tightness
  (cohort)"; acceptance and tightness: more = better (↑ better), cost: more = worse. `*` = cohort under 5 PRs, no
  direction.
- **Limits:** see "Limitations" below.

## Tokens and cost

- **API call** = a unique `message.id`. Claude Code writes one call in several records (one per content block),
  with partial `usage` while streaming: the record with the largest `output_tokens` and the earliest time is
  counted. The same `message.id` in two sessions (a copy after a fork) is counted once, in the older session.
  Subagent transcripts (`<session>/subagents/agent-*.jsonl`) count towards the cost of the session that started
  them.
- **Cost at API prices** from `references/cennik.json` (input, output, cache write 5 min and 1 h, cache read;
  Haiku 5.5 more expensive above 100k context; fast mode × 2; web search per query). The model is matched by the
  longest identifier prefix, `[1m]` is ignored. A new model or a price change: the `cennik` field in
  `konfiguracja.json` (same shape) or an update of the file in the plugin repo. Models without a price are not
  included in the cost; the summary lists them.
- **A relative measure, not a bill.** On a subscription the real limit is the usage limit (5-hour and weekly),
  not an amount. Compare amounts between retros, not with an invoice. A price list change (e.g. a cheaper new
  model) changes the cost without any change in how you work: when comparing with a retro on another model, check
  "cost by model" in the summary.
- **Lower bound.** Calls that are not in the transcripts (auto mode classifier, session titles, summaries) are
  not counted; in tests the difference against Claude Code's `cost-state` was up to ~15%.
- **Local only.** Sandbox, cloud and other machines have no transcripts here: cost per commit or PR in a repo
  with a large `commity_bez_sesji` makes no sense.
- **A wake-up** counts the break between main-session calls; a long subagent (> 1 h) creates one too.

## Weekly trend (`tokeny-tydzien.csv`)

On every run (without `--projekt` and `--bez-trendu`) `sygnaly.py` reads the whole transcript history in the
retro's scope, appends numbers only to the archive `dane/tokeny-archiwum.json` (calls with `usage`, times of the
user's messages and compactions, `cost-state`; no conversation content) and computes from the archive one row per
week (Monday, local time) in `tokeny-tydzien.csv` in the working directory. The archive protects the history
against `cleanupPeriodDays`: a transcript deleted after 30 days stays in the archive if the script read it in
time.

- **Row key:** (`tydzien`, `zrodlo`). The script writes `zrodlo=lokalne` (local) and rows of remote sources from
  the configuration (`zrodlo=<name>`, below). Rows of other sources (e.g. manual measurements, also several per
  week) stay verbatim, and unknown columns and notes added by hand in `pokrycie` stay in the script's rows too. A
  row without `zrodlo` is treated as local.
- **No duplicates:** a week is overwritten on every run (also an incomplete one, marked "period not finished"),
  unless the row in the file saw more calls; then the old one stays with a note in `pokrycie` (data from before
  the archive, deleted by retention).
- **Remote sources** (`zrodla_zdalne` in the configuration, none by default): a second machine that also runs
  Claude Code (sandbox, server). For each source the script makes **one** read attempt, without retrying:
  - `polecenie`: a list of arguments (or a string), e.g. `["ssh", "-T", "host", "python3 -"]` or with
    `docker exec -i <container> python3 -` inside the ssh string. The script feeds `scripts/zbierz_liczby.py` on
    stdin; on that machine it reads `~/.claude/projects` and prints numbers only (no conversation content); it
    writes nothing there.
  - `plik`: the output of `zbierz_liczby.py` saved earlier (path relative to the working directory or absolute),
    when the user makes the connection themselves:
    `ssh -T <host> python3 - < <skill>/scripts/zbierz_liczby.py > <working dir>/dane/<name>-liczby.json`
    (in PowerShell, which has no `<`: `cmd /c 'ssh -T <host> python3 - < <script> > <output>'`).
  - `wlaczone: false` disables the source, `limit_s` changes the time limit (300 s by default); `--bez-zdalnych`
    skips all of them for one run.

  A read goes into a separate archive `dane/tokeny-archiwum-<name>.json` (same format, plus a list `odczyty` with
  metadata of each read) and into rows `zrodlo=<name>`. When a read fails, the summary says why ("not read"), and
  the source's trend is computed from the archive without new data. Times of remote events come in UTC and are
  converted to this machine's local time.
- **Columns** as in the window metrics, but per week: `koszt_api_usd`, `koszt_api_usd_ceny_55` (Opus/Sonnet/Haiku
  at the prices of the models in the price list's `rodziny_biezace`, so that a price list change does not pose as
  a change in how you work), `koszt_na_wiad`, `wywolania_na_wiad`, `kontekst_mediana`, `kontekst_p90`,
  `proc_wywolan_ponad_200k`, shares of cache read and write in the cost, `wybudzenia` with their cost, share of
  subagents and Opus, `kontekst_startowy_mediana` (without `claude -p` sessions), `kompakty`, the check
  `koszt_cost_state_usd` against `koszt_policzony_tych_sesji` (sessions assigned to the week of their last call).
  The columns `*_sygnaly` and `pokrycie_wiad_proc` are for comparison with earlier extracts; the script neither
  computes nor changes them.
- **Trend in the summary:** the last 4 completed weeks with activity against the median of the 8 earlier ones,
  separately for each source. The recent median higher by more than 20% = **↑ worse** („↑ pogorszenie”), lower =
  ↓ better; with fewer than 3 earlier weeks "not enough data". Weeks with 1–2 sessions are noisy: the arrow is a
  hint, the evidence is that week's sessions. Since 0.2.1 the current, unfinished week (when it has activity) is
  shown in an extra last column ("not finished" / „niezakończony”) with an arrow against the recent median, so that
  a fresh fix or deterioration is visible at once; it stays outside the comparison. Weekly sums (`koszt_api_usd`,
  `wybudzenia_koszt_usd`) still grow during the week, so there they only get ↑.
- **User's messages** in the trend are counted as in the timelines (without `/…` commands, notifications, messages
  and briefs from other sessions, `claude -p` prompts; a screenshot alone is a message).

## Limitations

- **Local transcripts only.** Cloud sessions (claude.ai/code) and other computers are not visible.
- **Retention.** Claude Code deletes transcripts of terminal and VS Code sessions older than `cleanupPeriodDays`
  (30 days by default); desktop app sessions are not subject to this cleanup. The summary warns when the window
  reaches further. `dane/` in the working directory is an archive of extracts: after a month it is the only trace
  of older sessions. For a longer history set `cleanupPeriodDays` in `~/.claude/settings.json`.
- **Sessions in a scratchpad** (working directory `…/claude/…/scratchpad`, usually `claude -p` tests) are skipped;
  their number is in the summary.
- **Masking secrets is a heuristic.** Before reports are written, these disappear: the value after
  `gh secret set … --body`, the value after a name containing key/token/secret/pass/hasło/klucz (when it has
  letters and digits), `Bearer …`, keys with known prefixes (`sk-`, `ghp_`, `AKIA`, `AIza`, `hf_`, JWT), private key
  blocks and strings of ≥ 32 letters and digits. Full commit hashes (40 hex characters) and `sha256:` digests stay.
  A password made of ordinary words or a short code passes unmasked; the source transcripts are not changed.
- **Projects without local sessions in the window** (cloud work or another machine) have no timeline, and their
  repo and rules are not counted. The summary lists those that have memory; add the repo in
  `repozytoria_dodatkowe`. When a repo has sessions but most commits were made without them
  (`commity_bez_sesji`), the summary warns. Transcripts copied from another machine (a `projects` directory) are
  added with `transkrypcje_dodatkowe`; `cwd` paths from another machine usually do not exist locally, so fix
  project names in `nazwy_projektow`.
- **Commits and time.** git selects commits for the window by committer date (`--since`), and stops walking a
  branch at the first commit older than the window start: after a rebase with out-of-order dates some commits may
  drop out.
- **Outcome measures (since 0.9.0).** Rebase and squash change line history: blame sees the merge commit of a squash
  or merge, not PR commits rewritten by a rebase merge. A fix-type title is a convention; a fix PR named `feat: …`
  without a reference is not seen. "After approval" also catches a return for a conflict or rebase; the owner's PR
  comments are not read. The merge stands in for the deploy. Attention time covers only messages in local
  transcripts, not work outside Claude Code. With the default `cleanupPeriodDays` (30) the cohort's transcripts are
  gone: no implementer, reviewer or owner messages, so set it higher (see Retention).
- **The transcript format** is not a public Claude Code API and may change. When numbers suddenly drop to zero,
  check the script against a fresh transcript.
- **GitHub** only through `gh` logged in to an account with access to the repo (or a per-repo token from
  `gh_token_z_credential`); a repo the token cannot see is labelled "token has no access" instead of a GraphQL error.
  A repo without a remote is counted from git only.
