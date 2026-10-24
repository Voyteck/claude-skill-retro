"""Zdarzenia pracy podagentów z transkrypcji Claude Code, bez treści rozmów: do oceny efektywności pisania w retro.

Samodzielny (tylko biblioteka standardowa, Python ≥ 3.6), niczego nie zapisuje: wynik idzie na stdout. `sygnaly.py`
importuje go dla transkrypcji tej maszyny; inna maszyna (np. kontener) przez stdin, jak `zbierz_liczby.py`:
  ssh -T <host> 'docker exec -i <kontener> python3 - --od 2026-09-01' < zdarzenia_agentow.py > zdarzenia.json
Źródło zdalne w konfiguracji: pola `zdarzenia_polecenie` albo `zdarzenia_plik` wpisu `zrodla_zdalne`.

Argumenty: --od RRRR-MM-DD (UTC, domyślnie wszystko), --projekty KATALOG (domyślnie $CLAUDE_CONFIG_DIR/projects
albo ~/.claude/projects; można powtórzyć).
Wyjście: {"zdarzenia": [{ts, s, rodzaj: start|kontynuacja|raport, agent, typ, model, effort_zadany, pr, werdykt, uwagi, ci}],
"agenci": {agentId: {typ, model, s, ts, pr, effort_zadany, tokeny: {inp, out, cw, cw5, cw1h, cr, wyw, eff}}}, "sesje": {sesja: cwd}, "meta": {...}}.
Treść promptów i raportów jest czytana tylko po to, by wyciągnąć numery PR, werdykt przeglądu i wynik CI; nie trafia
do wyniku.
"""
import datetime
import glob
import json
import os
import re
import sys

# Werdykt przeglądu (PL/EN). Negatywny: trzeba poprawić przed scaleniem.
WERDYKT_NEG = re.compile(
    r"\b(?:verdict|werdykt)\b\W{0,6}(?:no[- ]?go|fix|block|reject|request|changes|popraw|nie\s+scal|do\s+poprawy)"
    r"|można\s+scalić\W{0,6}nie|nie\s+(?:można|da\s+się)\s+scalić|do\s+not\s+merge|not\s+ready\s+to\s+merge"
    r"|blokuje\s+merge|blocks?\s+the\s+merge|blocking\s+findings?\W{0,4}[1-9]|changes\s+requested", re.I)
WERDYKT_POZ = re.compile(
    r"\b(?:verdict|werdykt)\b\W{0,6}(?:go|merge|scal|approve|ok|lgtm)\b|można\s+scalić\W{0,6}tak"
    r"|nie\s+blokuje|none\s+(?:of\s+them\s+)?blocks?|no\s+blockers?|bez\s+bloker|nothing\s+to\s+fix|approved?\b"
    r"|\blgtm\b", re.I)
PRZECZENIE = re.compile(r"(?:\bnie|none(?:\s+of\s+them)?|\bno|nothing|\bnic|żadne\s+\w+)\W*$", re.I)
UWAGI = re.compile(r"(\d+)\s+(?:minor\s+|small\s+|drobn\w+\s+)?(?:findings?|uwag\w*|issues?)", re.I)
CI_OGOLNY = re.compile(r"(?:conclusion|wniosek|wynik)\W{0,8}(success|failure|failed|cancelled)|\*\*(success|failure)\*\*",
                       re.I)
CI_LINIA = re.compile(r"(success|failure|failed|cancelled|sukces|porażk\w*|czerwon\w*|zielon\w*)", re.I)
PR = re.compile(r"(?:\bPR\s*#?|#|/pull/)(\d{1,6})\b")
HANDBACK = re.compile(r'agent-message from="([0-9a-f]{8,})"')
ID_AGENTA = re.compile(r"[0-9a-f]{8,}")


def prs(tekst):
    return sorted({int(x) for x in PR.findall(tekst or "") if int(x) > 0})


def wynik_ci(slowo):
    w = slowo.lower()
    if w.startswith(("fail", "porażk", "czerwon")):
        return "porazka"
    return "anulowane" if w.startswith("cancel") else "sukces"


def ci_wyniki(tekst):
    """Lista [pr, wynik] z linii raportu obserwatora CI (linia z numerem PR i wynikiem)."""
    wynik = []
    for linia in (tekst or "").splitlines():
        slowa, numery = CI_LINIA.findall(linia), prs(linia)
        if slowa and numery:
            wynik += [[p, wynik_ci(slowa[0])] for p in numery]
    return wynik


def ci_ogolny(tekst):
    m = CI_OGOLNY.search(tekst or "")
    return wynik_ci(m.group(1) or m.group(2)) if m else None


def werdykt(tekst):
    """(negatywny | pozytywny | None, liczba uwag albo None) z raportu przeglądu."""
    tekst = (tekst or "")[:6000]
    neg = next((m for m in WERDYKT_NEG.finditer(tekst)
                if not PRZECZENIE.search(tekst[max(0, m.start() - 25):m.start()])), None)
    poz = WERDYKT_POZ.search(tekst)
    if not neg and not poz:
        return None, None
    m = neg if neg and (not poz or neg.start() <= poz.start() + 40) else poz
    u = UWAGI.search(tekst[max(0, m.start() - 200):m.start() + 400])
    return ("negatywny" if m is neg else "pozytywny"), (int(u.group(1)) if u else None)


def tekst_tresci(c):
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return " ".join(x.get("text", "") for x in c if isinstance(x, dict) and isinstance(x.get("text"), str))
    return ""


def tokeny_agenta(plik):
    """Model i sumy tokenów z transkrypcji podagenta: wejście, wyjście, zapis cache 5 min / 1 h, odczyt, liczba
    wywołań i najczęstszy poziom rozumowania (`eff`). Ten sam message.id bywa zapisany kilka razy z częściowym
    `usage`: liczy się rekord z największym `output_tokens`."""
    model, wywolania = None, {}
    try:
        f = open(plik, encoding="utf-8", errors="replace")
    except OSError:
        return None, None
    with f:
        for linia in f:
            if '"assistant"' not in linia:
                continue
            try:
                d = json.loads(linia)
            except ValueError:
                continue
            m = d.get("message") or {}
            u, mid = m.get("usage"), m.get("id")
            if not isinstance(u, dict) or not mid or m.get("model") == "<synthetic>":
                continue
            model = model or (m.get("model") or "").replace("[1m]", "") or None
            stary = wywolania.get(mid)
            if stary is None or (u.get("output_tokens") or 0) >= (stary[0].get("output_tokens") or 0):
                wywolania[mid] = (u, d.get("effort") if isinstance(d.get("effort"), str) else None)
    suma = {"inp": 0, "out": 0, "cw": 0, "cw5": 0, "cw1h": 0, "cr": 0, "wyw": len(wywolania)}
    poziomy = {}
    for u, eff in wywolania.values():
        zapis = u.get("cache_creation_input_tokens") or 0
        zapis_1h = (u.get("cache_creation") or {}).get("ephemeral_1h_input_tokens") or 0
        suma["inp"] += u.get("input_tokens") or 0
        suma["out"] += u.get("output_tokens") or 0
        suma["cw"] += zapis
        suma["cw5"] += zapis - zapis_1h
        suma["cw1h"] += zapis_1h
        suma["cr"] += u.get("cache_read_input_tokens") or 0
        if eff:
            poziomy[eff] = poziomy.get(eff, 0) + 1
    suma["eff"] = max(sorted(poziomy), key=poziomy.get) if poziomy else None
    return model, suma


def zbierz(katalogi, od="2000-01-01"):
    """Zdarzenia z sesji głównych w `katalogi` (katalogi `projects`) od daty `od` (UTC, RRRR-MM-DD)."""
    zdarzenia, agenci, pliki, katalogi_sesji = [], {}, [], {}
    for k in katalogi:
        pliki += sorted(glob.glob(os.path.join(str(k), "*", "*.jsonl")))
    try:          # plik niezmieniany od dnia przed `od` nie ma nowszych zdarzeń
        granica = datetime.datetime.strptime(od, "%Y-%m-%d").replace(tzinfo=datetime.timezone.utc).timestamp() - 86400
    except ValueError:
        granica = 0
    for plik in pliki:
        sesja = os.path.basename(plik)[:8]
        oczekujace = {}
        try:
            if os.path.getmtime(plik) < granica:
                continue
            f = open(plik, encoding="utf-8", errors="replace")
        except OSError:
            continue
        with f:
            for linia in f:
                if not any(z in linia for z in ('"Agent"', '"Task"', '"SendMessage"', "hand-back", "agentId")):
                    continue
                try:
                    d = json.loads(linia)
                except ValueError:
                    continue
                ts = d.get("timestamp") or ""
                if ts[:10] < od:
                    continue
                if d.get("cwd") and sesja not in katalogi_sesji:   # katalog sesji: przypisanie PR do repo
                    katalogi_sesji[sesja] = d["cwd"]
                tresc = (d.get("message") or {}).get("content")
                t = tekst_tresci(tresc)
                if "[Subagent hand-back]" in t:          # raport podagenta w tle
                    m = HANDBACK.search(t)
                    if m:
                        zdarzenia.append({"ts": ts, "s": sesja, "rodzaj": "raport", "agent": m.group(1)[:12],
                                          "_t": t.split("[Subagent hand-back]", 1)[1]})
                    continue
                if not isinstance(tresc, list):
                    continue
                for c in tresc:
                    if not isinstance(c, dict):
                        continue
                    if c.get("type") == "tool_use" and c.get("name") in ("Agent", "Task"):
                        we = c.get("input") or {}
                        oczekujace[c.get("id")] = {
                            "ts": ts, "s": sesja, "rodzaj": "start", "typ": we.get("subagent_type") or "general-purpose",
                            "model_zadany": we.get("model"), "effort_zadany": we.get("effort"),
                            "tlo": bool(we.get("run_in_background")),
                            "pr": prs(we.get("description") or "") or prs((we.get("prompt") or "")[:1500])}
                    elif c.get("type") == "tool_use" and c.get("name") == "SendMessage":
                        we = c.get("input") or {}
                        cel = str(we.get("to") or "")
                        if ID_AGENTA.fullmatch(cel):
                            zdarzenia.append({"ts": ts, "s": sesja, "rodzaj": "kontynuacja", "agent": cel[:12],
                                              "pr": prs(str(we.get("message") or "")[:3000])})
                    elif c.get("type") == "tool_result" and c.get("tool_use_id") in oczekujace:
                        z = oczekujace.pop(c["tool_use_id"])
                        tur = d.get("toolUseResult") if isinstance(d.get("toolUseResult"), dict) else {}
                        pelny = str(tur.get("agentId") or "")
                        aid = pelny[:12] or None
                        z["agent"] = aid
                        z["model"] = (tur.get("resolvedModel") or "").replace("[1m]", "") or None
                        zdarzenia.append(z)
                        if aid:
                            agenci[aid] = {"typ": z["typ"], "model": z["model"], "s": sesja, "ts": ts, "pr": z["pr"],
                                           "effort_zadany": z["effort_zadany"],
                                           "_plik": os.path.join(plik[:-6], "subagents", "agent-" + pelny + ".jsonl")}
                        if not tur.get("isAsync"):       # raport synchroniczny: wynik narzędzia
                            zdarzenia.append({"ts": ts, "s": sesja, "rodzaj": "raport", "agent": aid,
                                              "_t": tekst_tresci(tur.get("content")) or tekst_tresci(c.get("content"))})
    for a in agenci.values():
        model, suma = tokeny_agenta(a.pop("_plik"))
        a["model"] = a.get("model") or model
        a["tokeny"] = suma
    # raporty → PR, werdykt, wynik CI; treść odrzucana
    for z in zdarzenia:
        t = z.pop("_t", None)
        if t is None:
            continue
        a = agenci.get(z.get("agent") or "", {})
        z["typ"], z["model"] = a.get("typ"), a.get("model")
        start_pr = a.get("pr") or []
        z["pr"] = start_pr or prs(t[:4000])
        w, u = werdykt(t)
        if w:
            z["werdykt"], z["uwagi"] = w, u
        ci = ci_wyniki(t)
        if not ci:
            ogolny = ci_ogolny(t)
            ci = [[p, ogolny] for p in (z["pr"][:1] or [None])] if ogolny else []
        if ci:
            z["ci"] = ci
    zdarzenia.sort(key=lambda z: (z["s"], z["ts"]))
    return {"zdarzenia": zdarzenia, "agenci": agenci, "sesje": katalogi_sesji,
            "meta": {"format": 1, "czas": "utc", "od": od, "pliki": len(pliki),
                     "odczyt_utc": datetime.datetime.now(datetime.timezone.utc).isoformat()}}


def katalog_domyslny():
    baza = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
    return os.path.join(os.path.expanduser(baza), "projects")


def main(argv):
    od = argv[argv.index("--od") + 1] if "--od" in argv else "2000-01-01"
    katalogi = [os.path.expanduser(argv[i + 1]) for i, a in enumerate(argv[:-1]) if a == "--projekty"]
    katalogi = katalogi or [katalog_domyslny()]
    if not any(os.path.isdir(k) for k in katalogi):
        sys.stderr.write("brak katalogu transkrypcji: %s\n" % ", ".join(katalogi))
        return 1
    sys.stdout.write(json.dumps(zbierz(katalogi, od), ensure_ascii=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
