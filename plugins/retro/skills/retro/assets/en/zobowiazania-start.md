# Commitments register

Every retro starts by reviewing this register. A commitment gets here only after the user accepts it. Status
rules and limits: skill `retro` (plugin `retro`), `SKILL.md`, sections “Step 3” and “Standing rules”.

**Statuses:** active · established (kept in 3 consecutive retros, no longer tracked) · changed → Z-NNN · dropped
**Limits:** at most 5 new per retro; with more than 10 active, the retro proposes establishing or dropping some.

## Entry format

```
### Z-NNN · short name
- **Status:** active · **Since:** RNN (YYYY-MM-DD) · **Applies to:** Claude (all sessions) | subagents | user | …
- **Content:** what we do or do not do
- **Why:** the event or number that justifies it
- **Mechanism:** what enforces it (test, hook, branch protection, template) or “none: text-only rule”
- **Compliance signal:** what in the signals, transcripts, git or GitHub shows it was kept or broken
- **Measure of value:** what effect it should have; when we decide it does not
- **Recorded in:** rules file / memory / nauki.md / `.claude/agents/<name>.md`

| retro | kept | worth it | verdict | evidence |
|---|---|---|---|---|
```

An **agent configuration** commitment (a change of an agent's model, effort, description or prompt) also has:

```
- **Kind:** agent configuration · **Agent:** <name> (`<file>`) · **Change:** <field> <before> → <after>
- **Baseline:** RNN: <PRs>, <% with a fix>, <cost per PR>, size <S/M/L>
- **Rollback condition:** e.g. “% with a fix +10 points or more with ≥ 5 PRs after the change → back to <before>”
```

## Active

_(empty until retro zero is completed)_

## Established

## Changed and dropped
