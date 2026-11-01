# Retro RNN · YYYY-MM-DD

**Status:** draft
**Window:** YYYY-MM-DD … YYYY-MM-DD (N working days) · **Sessions:** N · **Projects:** …
**Data:** `dane/sygnaly-…/` (local, outside git)

## 1. In short

3–5 sentences: the most important conclusion and the most important change.

## 2. Trend metrics

| metric | R(N-2) | R(N-1) | RN | direction |
|---|---|---|---|---|

## 2a. Tokens and writing efficiency

Source: the "Tokens and writing efficiency" section of the signals summary (mandatory in every retro).

| indicator | R(N-3) | R(N-2) | R(N-1) | RN | better / worse |
|---|---|---|---|---|---|

- **Better:** … (numbers, cause, evidence)
- **Worse:** … (numbers, cause, evidence)
- **Efficiency by implementer configuration** (model · reasoning effort, within one PR size): share of PRs with a
  fix, rounds, returns from review and CI, **cost per PR** (expected cost of an accepted PR); with < 5 PRs in a cell
  only a hint.

**Agent selection rules** (who does which task, on which model and effort):

| task (role · size) | now (agent · model · effort) | proposed | data (PRs, % with a fix, cost per PR) | measure in the next retros |
|---|---|---|---|---|

- A move to a cheaper configuration makes sense when the cost per PR falls and the share of PRs with a fix does not
  grow by more than 10 percentage points; to a more expensive one when fewer fixes lower the cost per PR or the time
  to merge.
- With too few PRs propose an experiment instead of a rule (e.g. "every other size-S PR to `programista-prosty`",
  for two retros).
- **Suggestions (2–3):** change · expected effect · measure (e.g. "implement size-S PRs on Sonnet · medium as long as
  the share of PRs with a fix does not grow by more than 10 percentage points and the cost per PR stays below Opus").

**Agent changes: before and after** (from "Agent configuration changes and their effect"; the review of commitments
of kind "agent configuration"):

| agent · change (Z-NNN, retro) | baseline | after the change (PRs, % with a fix, cost per PR) | rollback condition | conclusion |
|---|---|---|---|---|

- Changes "since the last retro" (outside the retro): do they stay? If so, a new commitment with a baseline.

**Task routing and agent descriptions** (from "Task routing"): who does PRs of which size, agents without runs,
a built-in agent doing a custom agent's role. Change a `description` only with evidence of misrouting; one change per
agent per retro.

## 2b. Context files (caveman)

Source: the "Context files (caveman)" section of the summary; rules: the plugin's `references/caveman.md`.

| indicator | R(N-2) | R(N-1) | RN |
|---|---|---|---|
| `pliki_kontekstu_tokeny` | | | |
| `caveman_do_kompresji_tokeny` | | | |
| `kontekst_startowy_mediana` | | | |

- **To compress (proposal):** groups of files (global, repo, memory) · ~tokens · level.
- **After compression in earlier retros:** are the compressed rules kept as before (evidence), what to restore.

## 3. Commitments review

| ID | commitment | kept | worth it | evidence | proposed verdict |
|---|---|---|---|---|---|

## 4. What worked: keep doing

- **…** · evidence: `MM-DD HH:MM` `session` …

## 5. What did not work: change

- **…** · cause: … · evidence: …

## 6. The user's side

Cost and effect, with evidence. (Skip this section when `ocena_wlasciciela` is off.)

## 7. Contradictions and dead rules

## 8. Recommendations

At most 5 new commitments; each one says what it replaces or shortens.

### P1 · …

- **Content:** …
- **Applies to:** …
- **Mechanism:** … (or “none: text-only rule”, with the reason)
- **Compliance signal:** …
- **Measure of value:** …
- **Where to record:** …
- **Replaces / shortens:** …

## 8a. Waiting for the user

| item | since | evidence | decision |
|---|---|---|---|

## 9. User decisions

| proposal | decision | user's notes |
|---|---|---|

## 10. Implementation

- `zobowiazania.md`: …
- rules: … (file, commit / PR)
- agents: … (file, field, Z-NNN)
- caveman: … (files, ~tokens before → after, `caveman.csv`)
- proposed changes to the retro skill: …
