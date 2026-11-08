"""Miara podagentów (retro R08+): starty na scalony PR, udział zapisu cache w koszcie, odmowy strażnika worktree.

Czyta transkrypcje podagentów (`projects/*/<sesja>/subagents/agent-*.jsonl` z `agent-*.meta.json`) i sesji głównych,
a scalone PR-y bierze z `gh` (powtarzalne `--repo`) albo z pliku `--pr-plik`. Koszt: `tokeny.py` (cennik, `czesci_kosztu`).

Start podagenta = transkrypcja, której pierwszy zapis mieści się w oknie `--od`…`--do`. Przypisanie startu do PR:
z promptu (`org/repo#N`, `.../pull/N`, `repo#N`, `PR #N`), potem po najczęstszych odniesieniach w transkrypcji
(adres PR, nazwa gałęzi PR-a); reszta to starty nieprzypisane.

Odmowa strażnika = wynik narzędzia z błędem zawierającym „isolated in the worktree”; kształt polecenia (heredoc,
`cd X && …`, zmienna w ścieżce, `git -C`, pętla, `$()`…) wyciąga się z wywołania, które odmowę dostało.

Użycie: python podagenci.py --od 2026-11-07T01:00 --do 2026-11-08T19:00 --repo wergiliusz-hq/mitm [--json plik]
Czas bez strefy = UTC. Tylko biblioteka standardowa.
"""
import argparse
import collections
import datetime as dt
import json
import pathlib
import re
import statistics
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import tokeny  # noqa: E402
import wspolne  # noqa: E402

ZNACZNIK_ODMOWY = "isolated in the worktree"
TYPY_PRZEGLADU = "przeglad"
# Kolejność ma znaczenie: pierwszy pasujący kształt jest „główny”.
KSZTALTY = ["heredoc", "cd X && ...", "git -C", "loop", "gh --jq + pipe", "multi git", "nice", "cmd-subst",
            "shell var", "chain &&/;", "pipe"]


# ---------------------------------------------------------------- odczyt transkrypcji

def czas(napis):
    """ISO → datetime ze strefą (bez strefy = UTC) albo None."""
    try:
        d = dt.datetime.fromisoformat(str(napis).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)


def tekst(tresc) -> str:
    if isinstance(tresc, str):
        return tresc
    return " ".join(b.get("text", "") for b in tresc or [] if isinstance(b, dict) and b.get("type") == "text")


def ksztalt(polecenie: str) -> list:
    """Cechy polecenia powłoki, które strażnik worktree odrzuca."""
    c = polecenie or ""
    cechy = []
    if "<<" in c:
        cechy.append("heredoc")
    if re.search(r"\bcd\s+\S+\s*(&&|;)", c):
        cechy.append("cd X && ...")
    if re.search(r"git\s+-C\b", c):
        cechy.append("git -C")
    if re.search(r"\b(for|while)\b[^\n]*\bdo\b", c):
        cechy.append("loop")
    if re.search(r"\bgh\b.*--jq", c) and "|" in c:
        cechy.append("gh --jq + pipe")
    if len(re.findall(r"\bgit\b", c)) >= 2:
        cechy.append("multi git")
    if re.search(r"\bnice\b", c):
        cechy.append("nice")
    if "$(" in c or "`" in c:
        cechy.append("cmd-subst")
    if re.search(r"\$\{?\w+", c):
        cechy.append("shell var")
    if re.search(r"&&|;|\|\|", c):
        cechy.append("chain &&/;")
    if "|" in c.replace("||", ""):
        cechy.append("pipe")
    return cechy


def ksztalt_glowny(polecenie: str) -> str:
    cechy = ksztalt(polecenie)
    return next((k for k in KSZTALTY if k in cechy), "plain/other")


def przeczytaj(plik: pathlib.Path, podagent: bool) -> dict:
    """Jedna transkrypcja → {pierwszy, wywolania, prompt, odmowy[(czas, narzedzie, wejscie, tekst)], starty_agentow}."""
    wywolania, uzycia, odmowy, startow, pierwszy, prompt = {}, {}, [], [], None, None
    for linia in plik.open(encoding="utf-8", errors="replace"):
        try:
            d = json.loads(linia)
        except ValueError:
            continue
        if not isinstance(d, dict):
            continue
        ts = czas(d.get("timestamp")) if d.get("timestamp") else None
        if ts and pierwszy is None:
            pierwszy = ts
        wiad = d.get("message") or {}
        tresc = wiad.get("content")
        if d.get("type") == "user" and prompt is None and podagent and wiad.get("role") == "user":
            prompt = tekst(tresc)
        if d.get("type") == "assistant" and ts:
            if podagent:
                tokeny.dodaj_wywolanie(wywolania, tokeny.wywolanie_api(d, ts, True))
            for b in tresc if isinstance(tresc, list) else []:
                if isinstance(b, dict) and b.get("type") == "tool_use":
                    uzycia[b.get("id")] = (b.get("name"), b.get("input"))
                    if b.get("name") in ("Agent", "Task"):
                        startow.append(ts)
        if d.get("type") == "user" and isinstance(tresc, list):
            for b in tresc:
                if isinstance(b, dict) and b.get("type") == "tool_result" and b.get("is_error"):
                    nazwa, wejscie = uzycia.get(b.get("tool_use_id"), (None, None))
                    odmowy.append((ts, nazwa, wejscie, tekst(b.get("content"))))
    return {"pierwszy": pierwszy, "wywolania": sorted(wywolania.values(), key=lambda w: w["czas"]),
            "prompt": prompt, "odmowy": [o for o in odmowy if ZNACZNIK_ODMOWY in o[3]], "starty_agentow": startow}


def zbierz(katalogi: list, od, do, cennik: dict):
    """(podagenci, sesje główne) z transkrypcji; podagent = start w oknie, sesja główna = cokolwiek w oknie."""
    podagenci, glowne = [], []
    for katalog in katalogi:
        for plik in sorted(katalog.glob("*/*/subagents/agent-*.jsonl")):
            p = przeczytaj(plik, True)
            if not p["pierwszy"] or not (od <= p["pierwszy"] <= do):
                continue
            meta = {}
            try:
                meta = json.loads(plik.with_suffix(".meta.json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                pass
            wywolania = []
            for w in p["wywolania"]:
                c = tokeny.czesci_kosztu(w, cennik) or {}
                wywolania.append({"kontekst": w["kontekst"], "model": w["model"], "effort": w["effort"],
                                  "koszt": sum(c.values()), "wejscie": c.get("wejscie", 0),
                                  "wyjscie": c.get("wyjscie", 0), "zapis": c.get("zapis", 0),
                                  "odczyt": c.get("odczyt", 0)})
            podagenci.append({"plik": plik, "typ": meta.get("agentType") or "?", "prompt": p["prompt"] or "",
                              "pierwszy": p["pierwszy"], "wywolania": wywolania, "odmowy": p["odmowy"]})
        for plik in sorted(katalog.glob("*/*.jsonl")):
            p = przeczytaj(plik, False)
            odmowy = [o for o in p["odmowy"] if o[0] and od <= o[0] <= do]
            if odmowy:
                glowne.append({"plik": plik, "odmowy": odmowy})
    return podagenci, glowne


# ---------------------------------------------------------------- scalone PR-y i przypisanie

def scalone_pr(repo: str, od, do) -> list:
    """Scalone PR-y repo (`org/repo`) z `gh` scalone w oknie: [{repo, number, title, headRefName, mergedAt}]."""
    gh = wspolne.sciezka_gh({}) or "gh"
    szukaj = f"merged:{od.date().isoformat()}..{do.date().isoformat()}"
    r = subprocess.run([gh, "pr", "list", "-R", repo, "--state", "merged", "--limit", "200", "--search", szukaj,
                        "--json", "number,title,headRefName,mergedAt"], capture_output=True, text=True)
    if r.returncode != 0:
        print(f"podagenci: gh pr list {repo}: {r.stderr.strip()[:200]}", file=sys.stderr)
        return []
    return [dict(p, repo=repo) for p in json.loads(r.stdout or "[]")]


def w_oknie(lista: list, od, do) -> dict:
    """{(repo, numer): PR} dla PR scalonych w oknie."""
    wynik = {}
    for p in lista:
        t = czas(p.get("mergedAt"))
        if t and od <= t <= do:
            wynik[(p["repo"], p["number"])] = p
    return wynik


def kandydaci(prompt: str, repozytoria: list) -> list:
    """Odniesienia do PR w prompcie podagenta, w kolejności występowania."""
    wynik = []
    krotkie = {r.split("/")[-1]: r for r in repozytoria}
    for m in re.finditer(r"([\w.-]+/[\w.-]+)(?:#|/pull/)(\d+)", prompt):
        wynik.append((m.group(1), int(m.group(2))))
    if krotkie:
        wzor = r"\b(" + "|".join(re.escape(k) for k in krotkie) + r")#(\d+)"
        for m in re.finditer(wzor, prompt):
            wynik.append((krotkie[m.group(1)], int(m.group(2))))
    hint = re.search(r"REPO=([\w.-]+)", prompt) or re.search(r"-R ([\w.-]+/[\w.-]+)", prompt)
    domyslne = repozytoria[0] if repozytoria else ""
    if hint:
        domyslne = krotkie.get(hint.group(1), hint.group(1))
    for m in re.finditer(r"\bPR #?(\d+)", prompt):
        wynik.append((domyslne, int(m.group(1))))
    return wynik


def z_transkrypcji(plik: pathlib.Path, pr: dict) -> collections.Counter:
    """Ile razy transkrypcja wskazuje każdy scalony PR (adres PR = 1, nazwa gałęzi = 0,5)."""
    licznik = collections.Counter()
    try:
        s = plik.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return licznik
    for m in re.finditer(r"([\w.-]+/[\w.-]+)/pull/(\d+)", s):
        if (m.group(1), int(m.group(2))) in pr:
            licznik[(m.group(1), int(m.group(2)))] += 1
    for klucz, p in pr.items():
        if p.get("headRefName") and p["headRefName"] in s:
            licznik[klucz] += 0.5
    return licznik


def przypisz(podagenci: list, pr: dict, repozytoria: list):
    """Ustawia `a["pr"]` (klucz albo None) i `a["jak"]` (prompt | transkrypcja)."""
    for a in podagenci:
        a["pr"], a["jak"] = None, None
        for k in kandydaci(a["prompt"], repozytoria):
            if k in pr:
                a["pr"], a["jak"] = k, "prompt"
                break
        if a["pr"] is None and a["typ"] != "obserwator-ci":
            licznik = z_transkrypcji(a["plik"], pr)
            if licznik:
                a["pr"], a["jak"] = max(licznik, key=licznik.get), "transkrypcja"


# ---------------------------------------------------------------- miary

def koszt_agenta(a: dict) -> float:
    return sum(w["koszt"] for w in a["wywolania"])


def podzial_kosztu(lista: list) -> dict:
    """Koszt w USD: zapis pierwszego wywołania / późniejsze zapisy / odczyt / wyjście / wejście."""
    zapis_pierwszy = sum(a["wywolania"][0]["zapis"] for a in lista if a["wywolania"])
    zapis = sum(w["zapis"] for a in lista for w in a["wywolania"])
    razem = sum(koszt_agenta(a) for a in lista)
    wynik = {"razem_usd": razem, "zapis_pierwszego_usd": zapis_pierwszy, "zapisy_pozniejsze_usd": zapis - zapis_pierwszy,
             "odczyt_usd": sum(w["odczyt"] for a in lista for w in a["wywolania"]),
             "wyjscie_usd": sum(w["wyjscie"] for a in lista for w in a["wywolania"]),
             "wejscie_usd": sum(w["wejscie"] for a in lista for w in a["wywolania"])}
    wynik["proc"] = {k[:-4]: (v / razem if razem else 0.0) for k, v in wynik.items() if k.endswith("_usd") and k != "razem_usd"}
    return wynik


def po_typach(podagenci: list, glowne_odmowy: int = 0) -> dict:
    """Starty, koszt, wywołania na start i średni kontekst wywołania per typ podagenta."""
    grupy = collections.defaultdict(list)
    for a in podagenci:
        grupy[a["typ"]].append(a)
    wynik = {}
    for typ, lista in grupy.items():
        wyw = [w for a in lista for w in a["wywolania"]]
        wynik[typ] = {"starty": len(lista), "usd": sum(koszt_agenta(a) for a in lista),
                      "wywolania_na_start": len(wyw) / len(lista),
                      "kontekst_sredni": statistics.mean(w["kontekst"] for w in wyw) if wyw else 0,
                      "odmowy": sum(len(a["odmowy"]) for a in lista),
                      "podzial": podzial_kosztu(lista)}
        wynik[typ]["odmowy_na_start"] = wynik[typ]["odmowy"] / len(lista)
    return wynik


def po_pr(podagenci: list, pr: dict) -> dict:
    """Starty programisty / przeglądu / powtórnych przeglądów i koszt na scalony PR."""
    grupy = collections.defaultdict(list)
    for a in podagenci:
        if a["pr"]:
            grupy[a["pr"]].append(a)
    wiersze = []
    for klucz in sorted(pr):
        lista = grupy.get(klucz, [])
        przeglady = sum(1 for a in lista if a["typ"].startswith(TYPY_PRZEGLADU))
        wiersze.append({"pr": f"{klucz[0]}#{klucz[1]}", "tytul": pr[klucz].get("title", "")[:60],
                        "programista": sum(1 for a in lista if a["typ"] == "programista"),
                        "przeglad": przeglady, "powtorny_przeglad": max(0, przeglady - 1),
                        "usd": sum(koszt_agenta(a) for a in lista), "starty": len(lista)})
    z_agentami = [w for w in wiersze if w["starty"]]

    def ms(klucz):
        v = [w[klucz] for w in z_agentami]
        return {"srednia": statistics.mean(v), "mediana": statistics.median(v), "max": max(v)} if v else {}
    return {"scalone": len(pr), "z_podagentami": len(z_agentami), "programista_na_pr": ms("programista"),
            "przeglad_na_pr": ms("przeglad"), "powtorny_przeglad_na_pr": ms("powtorny_przeglad"),
            "usd_na_pr": ms("usd"), "wiersze": wiersze}


def odmowy_strazy(podagenci: list, glowne: list) -> dict:
    """Odmowy strażnika worktree: per typ (sesja główna = MAIN) i najczęstsze kształty poleceń."""
    wszystkie = [(a["typ"], o) for a in podagenci for o in a["odmowy"]]
    wszystkie += [("MAIN", o) for g in glowne for o in g["odmowy"]]
    ksztalty, przyklady = collections.Counter(), {}
    kazdy = collections.Counter()
    for typ, (_, _, wejscie, _) in wszystkie:
        polecenie = wejscie.get("command", "") if isinstance(wejscie, dict) else ""
        k = ksztalt_glowny(polecenie)
        ksztalty[k] += 1
        przyklady.setdefault(k, polecenie[:150].replace("\n", " "))
        for cecha in ksztalt(polecenie):
            kazdy[cecha] += 1
    razem = len(wszystkie)
    return {"razem": razem, "podagenci": sum(1 for t, _ in wszystkie if t != "MAIN"),
            "glowne": sum(1 for t, _ in wszystkie if t == "MAIN"),
            "wg_typu": dict(collections.Counter(t for t, _ in wszystkie).most_common()),
            "ksztalty_glowne": {k: {"n": n, "proc": n / razem if razem else 0.0, "przyklad": przyklady[k]}
                                for k, n in ksztalty.most_common()},
            "ksztalty_dowolne": dict(kazdy.most_common()),
            "na_start": (sum(1 for t, _ in wszystkie if t != "MAIN") / len(podagenci)) if podagenci else 0.0}


def policz(katalogi: list, od, do, repozytoria: list, pr_lista: list, cennik: dict) -> dict:
    podagenci, glowne = zbierz(katalogi, od, do, cennik)
    pr = w_oknie(pr_lista, od, do)
    przypisz(podagenci, pr, repozytoria)
    nieprzypisane = [a for a in podagenci if not a["pr"]]
    return {"okno": {"od": od.isoformat(), "do": do.isoformat()}, "starty": len(podagenci),
            "typy": po_typach(podagenci), "pr": po_pr(podagenci, pr),
            "nieprzypisane": {"starty": len(nieprzypisane), "usd": sum(koszt_agenta(a) for a in nieprzypisane),
                              "wg_typu": dict(collections.Counter(a["typ"] for a in nieprzypisane))},
            "podzial_kosztu": podzial_kosztu(podagenci), "odmowy": odmowy_strazy(podagenci, glowne)}


# ---------------------------------------------------------------- raport

def raport(w: dict) -> str:
    o = []
    o.append(f"# Miara podagentów, okno {w['okno']['od']} … {w['okno']['do']}")
    o.append(f"Starty podagentów: {w['starty']}")
    o.append("\n## Starty wg typu")
    o.append("| typ | starty | USD | wywołań/start | średni kontekst | odmowy strażnika (na start) |")
    o.append("|---|---|---|---|---|---|")
    for typ, m in sorted(w["typy"].items(), key=lambda kv: -kv[1]["usd"]):
        o.append(f"| {typ} | {m['starty']} | {m['usd']:.2f} | {m['wywolania_na_start']:.0f} | "
                 f"{m['kontekst_sredni']:.0f} | {m['odmowy']} ({m['odmowy_na_start']:.1f}) |")
    p = w["pr"]
    o.append(f"\n## Na scalony PR (scalone: {p['scalone']}, z podagentami: {p['z_podagentami']})")
    for klucz, nazwa in (("programista_na_pr", "starty programisty"), ("przeglad_na_pr", "starty przeglądu"),
                         ("powtorny_przeglad_na_pr", "powtórne przeglądy"), ("usd_na_pr", "USD podagentów")):
        m = p[klucz]
        if m:
            o.append(f"- {nazwa}/PR: średnia {m['srednia']:.2f}, mediana {m['mediana']:.2f}, max {m['max']:.2f}")
    n = w["nieprzypisane"]
    o.append(f"- starty nieprzypisane do PR: {n['starty']} ({n['usd']:.2f} USD) {n['wg_typu']}")
    z = w["podzial_kosztu"]
    o.append(f"\n## Podział kosztu podagentów (razem {z['razem_usd']:.2f} USD)")
    pr = z["proc"]
    o.append(f"zapis pierwszego wywołania {pr['zapis_pierwszego']:.0%}, późniejsze zapisy {pr['zapisy_pozniejsze']:.0%}, "
             f"odczyt {pr['odczyt']:.0%}, wyjście {pr['wyjscie']:.0%}, wejście {pr['wejscie']:.0%}")
    od = w["odmowy"]
    o.append(f"\n## Odmowy strażnika worktree: {od['razem']} (podagenci {od['podagenci']}, główne {od['glowne']}; "
             f"{od['na_start']:.1f} na start podagenta)")
    o.append("wg typu: " + ", ".join(f"{k} {v}" for k, v in od["wg_typu"].items()))
    o.append("| kształt (główny) | n | % | przykład |")
    o.append("|---|---|---|---|")
    for k, m in list(od["ksztalty_glowne"].items())[:8]:
        o.append(f"| {k} | {m['n']} | {m['proc']:.0%} | `{m['przyklad']}` |")
    return "\n".join(o)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--od", required=True, help="początek okna, ISO (bez strefy = UTC)")
    ap.add_argument("--do", help="koniec okna, ISO; domyślnie teraz")
    ap.add_argument("--repo", action="append", default=[], help="org/repo, z którego brać scalone PR-y (powtarzalne)")
    ap.add_argument("--pr-plik", help="JSON {org/repo: [PR…]} zamiast `gh` (jak z `gh pr list --json`)")
    ap.add_argument("--katalog", action="append", default=[], help="katalog `projects` transkrypcji (domyślnie Claude Code)")
    ap.add_argument("--json", help="zapisz wynik jako JSON w tym pliku")
    a = ap.parse_args(argv)
    od = czas(a.od)
    do = czas(a.do) if a.do else dt.datetime.now(dt.timezone.utc)
    if not od or not do:
        ap.error("--od/--do: oczekiwano daty ISO")
    katalogi = [pathlib.Path(k).expanduser() for k in a.katalog] or [wspolne.katalog_claude() / "projects"]
    pr_lista = []
    if a.pr_plik:
        dane = json.loads(pathlib.Path(a.pr_plik).read_text(encoding="utf-8"))
        pr_lista = [dict(p, repo=r) for r, lista in dane.items() for p in lista]
        a.repo = a.repo or list(dane)
    else:
        for r in a.repo:
            pr_lista += scalone_pr(r, od, do)
    wynik = policz(katalogi, od, do, a.repo, pr_lista, tokeny.wczytaj_cennik({}))
    print(raport(wynik))
    if a.json:
        pathlib.Path(a.json).write_text(json.dumps(wynik, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
