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
| `kontekst_mediana` | median context (input + cache write + cache read) of main-session calls | context size × number of calls is the main cost |
| `kontekst_ponad_200k_proc` | share of main-session calls with context > 200k | |
| `kontekst_startowy_mediana` | median context of the first call of sessions started in the window | fixed overhead: system prompt, tools, skills, MCP, CLAUDE.md, memory; a session with copies of another session's calls (fork) is excluded |
| `podagenci_koszt_proc` | subagents' share of the cost | |
| `podagenci_opus_koszt_proc` | Opus's share of the subagents' cost | counting subagents by number misleads: Opus is often a minority of subagent calls and the majority of their cost |
| `wybudzenia`, `wybudzenia_koszt_usd` | main-session calls with a cache write > 50k after a break > 1 h since its previous call; cost of the write alone | a closing question ("can I archive?") to a long session, or a background task finishing hours later; listed in the summary with the cause |
| `commity_bez_sesji`, `pr_bez_sesji` | commits (committer time) and opened PRs without a local transcript of a session in that repo within ±30 min | work in a sandbox, cloud, another machine, merges on GitHub; the summary warns when it is ≥ 20% (and ≥ 3 commits or ≥ 2 PRs) |
| `claude_md_linie_osobno` | lines of rules files in `katalogi_regul_osobno` | e.g. copies of `CLAUDE.md` kept in one repo for future repositories |
| `wybudzenia_wlasciciel`, `wybudzenia_tlo`, `wybudzenia_sesja`, `wybudzenia_inne` (since 0.2.1) | `wybudzenia` split by the first input after the break: the user's message; a background task or subagent (`<task-notification>`, `queue-operation`, "[Subagent hand-back]"); another session (`peer`, `<agent-message>`, `<cross-session-message>`, `<side-sessions-event>`, a system reminder about sessions); anything else (e.g. a tool result after a long foreground wait or API retries) | a hook on the user's message (`UserPromptSubmit`) can only act on the first kind; system reminders the app prepends to a message are skipped when classifying |
| `pr_analizowane`, `pr_z_poprawka_proc`, `rundy_na_pr` (since 0.3.0) | PRs merged in the window on GitHub (repos of the window with a remote), the share with at least one fix round, mean rounds per PR | see "Tokens and writing efficiency"; empty without `gh` |
| `pr_wg_modelu`, `pr_z_poprawka_proc_wg_modelu` (since 0.3.0) | the same by author model, as text `Opus:71;Fable:27` (share of PRs, % with a fix) | `bez stopki` = no `Co-Authored-By: Claude` trailer |
| `powroty_przeglad`, `powroty_ci` (since 0.3.0) | returns of an implementer to the same PR after a negative review or red CI, local transcripts plus remote agent events | the main session fixing its own PR is not a return |
| `koszt_implementacji_proc_wg_modelu` (since 0.3.0) | model families' share of implementation subagents' cost in the window, `Opus:90;Sonnet:10` | role by `role_agentow` |
| `pr_powiazane`, `koszt_na_pr_usd` (since 0.4.0) | PRs merged in the window with an implementation subagent found in transcripts; their mean agent cost (implementation, review, CI, fix rounds included) | the expected cost of an accepted PR; main-session cost excluded |
| `koszt_na_pr_wg_konfiguracji` (since 0.4.0) | the same by implementer configuration, `Opus/high:6.68;Sonnet/medium:1.20` | compare configurations within one PR size in the summary table, not in this sum |
| `koszt_wg_poziomu` (since 0.4.0) | reasoning efforts' share of the window cost, `high:80;xhigh:18;?:2` | `?` = calls without a recorded effort |

## Tokens and writing efficiency

The summary section "Tokens and writing efficiency" („Tokeny i efektywność pisania”) is data for the mandatory
section 2a of the retro document.

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
- **Fix rounds in merged PRs:** `gh api graphql` (search, 40 PRs per page, at most 10 pages per repo; `gh pr list
  --json commits` exceeds the GraphQL node limit). Commits sorted by author date (robust to rebase), without merge
  commits; a batch after a break longer than `pr_przerwa_rundy_min` is a round. The author model is the most frequent
  `Co-Authored-By: Claude <Model>` trailer in the first batch. Skipped: branches with prefixes from
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
- **Limits:** a round is not always a return from the tester (rebase, conflicts of integration batches, the owner's
  remarks); a missing trailer makes the author "no trailer"; verdicts and CI results are a heuristic on free text and
  the role of an agent depends on its type name; a main session that implements and fixes by itself has no returns
  and no cost per PR; PRs whose task never mentions their number get no cost; with fewer than 5 PRs in a cell the
  comparison between configurations is a hint only.

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
- **The transcript format** is not a public Claude Code API and may change. When numbers suddenly drop to zero,
  check the script against a fresh transcript.
- **GitHub** only through `gh` logged in to an account with access to the repo; a repo without a remote is counted
  from git only.
