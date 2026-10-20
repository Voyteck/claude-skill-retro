"""Liczby z transkrypcji Claude Code na tej maszynie, bez treści rozmów: do trendu tokenów retro z innej maszyny.

Samodzielny (tylko biblioteka standardowa, Python ≥ 3.6), niczego nie zapisuje: wynik idzie na stdout. Uruchamiany
zdalnie przez stdin, np. z Git Bash albo PowerShell:
  ssh -T <host> python3 - < zbierz_liczby.py > liczby.json
  ssh -T <host> 'docker exec -i <kontener> python3 -' < zbierz_liczby.py > liczby.json
`sygnaly.py` robi to sam dla źródła z polem `polecenie` (pole `zrodla_zdalne` konfiguracji); wynik zapisany ręcznie
wskazuje pole `plik`.

Argumenty (po `python3 -`): --projekty KATALOG (domyślnie $CLAUDE_CONFIG_DIR/projects albo ~/.claude/projects).
Wyjście: {"calls": {message.id: {ts, s, sub, model, ep, inp, out, cw5, cw1h, cr, speed, ws, agent, proj}},
"owner": [[czas UTC ISO, sesja]], "compacts": [[czas UTC ISO, sesja]], "cost_state": {sesja: usd},
"meta": {"format": 2, "czas": "utc", ...}}. Tekst wiadomości użytkownika jest czytany tylko po to, by odróżnić
właściciela od powiadomień i briefów innych sesji (reguły jak w `sygnaly.py`); nie trafia do wyniku.
"""
import datetime
import glob
import json
import os
import sys

NIE_WLASCICIEL = ("<local-command", "<task-notification", "[Cross-session", "<cross-session-message",
                  "<system-reminder", "Background (from the session", "<agent-message", "Caveat:")


def tekst(c):
    if isinstance(c, str):
        return c
    if isinstance(c, list):    # sam zrzut ekranu też jest wiadomością (jak w sygnaly.py)
        return " ".join(b.get("text", "") if b.get("type") == "text" else "[obraz]"
                        for b in c if isinstance(b, dict) and b.get("type") in ("text", "image"))
    return ""


def wlasciciel(r, t):
    if r.get("isMeta") or r.get("isCompactSummary") or r.get("entrypoint") == "sdk-cli":
        return False
    o = r.get("origin")
    if isinstance(o, dict) and o.get("kind") not in ("human", None):
        return False
    t = t.strip()
    return bool(t) and not t.startswith(NIE_WLASCICIEL) and not t.startswith("<command-name>")


def typ_agenta(sciezka):
    try:
        with open(sciezka[:-6] + ".meta.json", encoding="utf-8") as f:
            return str(json.load(f).get("agentType") or "?")
    except (OSError, ValueError, AttributeError):
        return "?"


def katalog_domyslny():
    baza = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
    return os.path.join(os.path.expanduser(baza), "projects")


def zbierz(root):
    calls, owner, compacts, cost_state = {}, set(), set(), {}
    pliki = glob.glob(os.path.join(root, "**", "*.jsonl"), recursive=True)
    najstarsze = None
    for p in pliki:
        czesci = os.path.relpath(p, root).split(os.sep)
        pod = "subagents" in czesci
        sid = (czesci[1] if pod else os.path.basename(p)[:-6])[:8]
        agent = typ_agenta(p) if pod else "sesja główna"
        with open(p, encoding="utf-8", errors="replace") as f:
            for linia in f:
                try:
                    r = json.loads(linia)
                except ValueError:
                    continue
                if not isinstance(r, dict) or (not r.get("timestamp") and r.get("type") != "cost-state"):
                    continue
                t = r.get("type")
                if t == "assistant":
                    m = r.get("message") or {}
                    u, mid, model = m.get("usage"), m.get("id"), m.get("model")
                    if not isinstance(u, dict) or not mid or not model or model == "<synthetic>":
                        continue
                    zapis = u.get("cache_creation_input_tokens") or 0
                    zapis_1h = (u.get("cache_creation") or {}).get("ephemeral_1h_input_tokens") or 0
                    rec = {"ts": r["timestamp"], "s": sid, "sub": pod, "model": model, "ep": r.get("entrypoint"),
                           "inp": u.get("input_tokens") or 0, "out": u.get("output_tokens") or 0,
                           "cw5": zapis - zapis_1h, "cw1h": zapis_1h, "cr": u.get("cache_read_input_tokens") or 0,
                           "speed": u.get("speed"), "ws": (u.get("server_tool_use") or {}).get("web_search_requests") or 0,
                           "agent": agent, "proj": czesci[0][:60]}
                    stary = calls.get(mid)
                    if stary is None or rec["out"] >= stary["out"]:
                        if stary is not None:
                            rec["ts"] = min(rec["ts"], stary["ts"])
                        calls[mid] = rec
                    if najstarsze is None or r["timestamp"] < najstarsze:
                        najstarsze = r["timestamp"]
                elif t == "system" and r.get("subtype") == "compact_boundary":
                    compacts.add((r["timestamp"], sid))
                elif t == "cost-state":
                    try:
                        cost_state[sid] = max(cost_state.get(sid, 0), float(r.get("totalCostUSD") or 0))
                    except (TypeError, ValueError):
                        pass
                elif t == "user" and not pod and r.get("toolUseResult") is None:
                    c = (r.get("message") or {}).get("content")
                    if isinstance(c, list) and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in c):
                        continue
                    if wlasciciel(r, tekst(c)):
                        owner.add((r["timestamp"], sid))
                elif t == "attachment" and not pod:
                    a = r.get("attachment") or {}
                    if (a.get("type") == "queued_command" and (a.get("origin") or {}).get("kind") == "human"
                            and isinstance(a.get("prompt"), str) and wlasciciel(r, a["prompt"])):
                        owner.add((r["timestamp"], sid))
    return {"calls": calls, "owner": sorted(owner), "compacts": sorted(compacts), "cost_state": cost_state,
            "meta": {"format": 2, "czas": "utc", "root": root, "pliki": len(pliki), "najstarsze_utc": najstarsze,
                     "odczyt_utc": datetime.datetime.now(datetime.timezone.utc).isoformat()}}


def main(argv):
    root = katalog_domyslny()
    if "--projekty" in argv:
        root = os.path.expanduser(argv[argv.index("--projekty") + 1])
    if not os.path.isdir(root):
        sys.stderr.write("brak katalogu transkrypcji: %s\n" % root)
        return 1
    sys.stdout.write(json.dumps(zbierz(root), ensure_ascii=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
