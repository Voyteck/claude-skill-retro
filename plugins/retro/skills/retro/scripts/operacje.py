"""Koszt kroków CI, deployu i ops w sesjach głównych i u podagentów, per projekt (od 0.8.0).

Wywołanie API (unikalny message.id) jest krokiem ops, gdy któreś z jego wywołań Bash/PowerShell ma polecenie
pasujące do WZOR_CI albo WZOR_DEPLOY (wzorce z analizy transkrypcji 2026-06..11, `deploy_share.py`). Polecenie
pasujące do obu to CI; wywołanie z poleceniami obu rodzajów to deploy. Cały koszt takiego wywołania (z kontekstem,
który niesie) liczy się jako koszt ops: to właśnie płaci sesja główna z dużym kontekstem, gdy sama pilnuje CI albo
loguje się na serwer, zamiast oddać to podagentowi Haiku (zasada Z-012 „Koszt sesji”).

Heurystyka: `grep deploy` albo `cat nginx.conf` też pasują. Liczy się trend i porównanie projektów, nie wartość.
"""
import collections
import pathlib
import re
import statistics
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from teksty import t  # noqa: E402

WZOR_CI = re.compile(r"\bgh (run|workflow|pr checks)\b", re.IGNORECASE)
WZOR_DEPLOY = re.compile(r"\b(ssh|scp|rsync|docker|compose|systemctl|journalctl|ansible|kubectl|deploy\w*|wrangler"
                         r"|terraform|certbot|nginx|caddy|apt(-get)?|ufw|sftp)\b", re.IGNORECASE)
POWLOKI = ("Bash", "PowerShell")
RODZAJE = ("ci", "deploy")
# Agent ops w `.claude/agents`: nazwa pliku albo `name:` (role z Z-012: `obserwator-ci`, `operator`).
WZOR_AGENTA_OPS = re.compile(r"operator|obserwator|ci-?watch|(^|[-_])(ci|ops|deploy\w*)([-_]|$)", re.IGNORECASE)
# Kandydat do audytu agentów projektu (project-agents, rola operatora): ops w sesjach głównych powyżej PROG_PROC
# kosztu projektu albo brak agenta ops przy kosztach ops od PROG_USD. Pola konfiguracji: `ops_prog_proc`,
# `ops_prog_usd`.
PROG_PROC = 10.0
PROG_USD = 1.0
# Z-012: handoff do nowej sesji po ~150 żądaniach (wywołaniach API sesji głównej).
PROG_ZADAN = 150
# Projekty bez repo (`Projekty` w sygnaly.py): nie ma gdzie dodać agenta, więc nie są kandydatami.
BEZ_REPO = ("nieznany", "bez-folderu", "?")


def rodzaj_polecenia(nazwa: str, wejscie) -> str:
    """„ci”, „deploy” albo None dla jednego wywołania narzędzia."""
    if nazwa not in POWLOKI or not isinstance(wejscie, dict):
        return None
    polecenie = wejscie.get("command")
    if not isinstance(polecenie, str):
        return None
    if WZOR_CI.search(polecenie):
        return "ci"
    if WZOR_DEPLOY.search(polecenie):
        return "deploy"
    return None


def oznacz(rodzaje: dict, mid, blok) -> None:
    """Dopisuje rodzaj bloku `tool_use` do zbioru wywołania `mid` (ten sam message.id bywa w kilku rekordach)."""
    if not mid or not isinstance(blok, dict) or blok.get("type") != "tool_use":
        return
    r = rodzaj_polecenia(blok.get("name"), blok.get("input"))
    if r:
        rodzaje.setdefault(mid, set()).add(r)


def rodzaj_wywolania(zbior) -> str:
    """Rodzaj całego wywołania: deploy ma pierwszeństwo przed CI."""
    if not zbior:
        return None
    return "deploy" if "deploy" in zbior else "ci"


def agenci_ops(definicje: list) -> dict:
    """{źródło (repo albo ~/.claude): [nazwa · model]} definicji agentów ops."""
    wynik = collections.defaultdict(list)
    for d in definicje or []:
        nazwy = (d.get("agent") or "", pathlib.Path(d.get("plik") or "").stem)
        if any(WZOR_AGENTA_OPS.search(n) for n in nazwy if n):
            wynik[d.get("zrodlo") or "?"].append(f"{d.get('agent')} · {d.get('model') or 'inherit'}")
    return dict(wynik)


def _proc(czesc, calosc):
    return round(100 * czesc / calosc, 1) if calosc else None


def zestawienie(wywolania: list, definicje: list = (), konf: dict = None, globalne: str = "~/.claude") -> dict:
    """Projekty i metryki z wywołań okna (`metryki_tokenow`: pola `sesja`, `podagent`, `koszt`, `ops`).

    Wiersz projektu: koszt, koszt ops (CI + deploy) w sesjach głównych i u podagentów, udział ops sesji głównych
    w koszcie projektu, mediana i maksimum wywołań na sesję główną (całe sesje, także sprzed okna), agenci ops
    projektu i czy projekt jest kandydatem do audytu agentów."""
    konf = konf or {}
    prog_proc = float(konf.get("ops_prog_proc") or PROG_PROC)
    prog_usd = float(konf.get("ops_prog_usd") or PROG_USD)
    agenci = agenci_ops(definicje)
    projekty = collections.defaultdict(lambda: {"koszt": 0.0, "glowna": collections.Counter(),
                                                "pod": collections.Counter(), "sesje": {}})
    for w in wywolania:
        s = w.get("sesja")
        nazwa = s.projekt[0] if s is not None else "?"
        p = projekty[nazwa]
        koszt = w.get("koszt") or 0
        p["koszt"] += koszt
        if w.get("ops"):
            p["pod" if w["podagent"] else "glowna"][w["ops"]] += koszt
        if s is not None and not w["podagent"]:
            p["sesje"][s.sid] = s
    wiersze, zadania_wszystkie = [], []
    for nazwa, p in projekty.items():
        zadania = [sum(1 for x in s.wywolania.values() if not x["podagent"]) for s in p["sesje"].values()]
        zadania_wszystkie += zadania
        glowna, pod = sum(p["glowna"].values()), sum(p["pod"].values())
        wlasni = agenci.get(nazwa) or []
        udzial = _proc(glowna, p["koszt"])
        powody = []
        if nazwa not in BEZ_REPO:
            if udzial is not None and udzial > prog_proc and glowna >= prog_usd:
                powody.append("udzial")
            if glowna + pod >= prog_usd:
                if not wlasni:
                    powody.append("brak_agenta")
                elif not any("haiku" in a.lower() for a in wlasni):
                    powody.append("nie_haiku")
        wiersze.append({
            "projekt": nazwa, "koszt": round(p["koszt"], 2),
            "ci_glowna": round(p["glowna"]["ci"], 2), "deploy_glowna": round(p["glowna"]["deploy"], 2),
            "ci_pod": round(p["pod"]["ci"], 2), "deploy_pod": round(p["pod"]["deploy"], 2),
            "ops_glowna": round(glowna, 2), "ops_pod": round(pod, 2),
            "ops_glowna_proc": udzial, "ops_proc": _proc(glowna + pod, p["koszt"]),
            "sesje": len(zadania), "zadania_mediana": statistics.median(zadania) if zadania else None,
            "zadania_max": max(zadania) if zadania else None,
            "sesje_ponad_prog": sum(z > PROG_ZADAN for z in zadania),
            "agenci_ops": wlasni, "kandydat": powody})
    wiersze.sort(key=lambda w: (-(w["ops_glowna"] + w["ops_pod"]), w["projekt"]))
    koszt = sum(w["koszt"] for w in wiersze)
    ops_g = sum(w["ops_glowna"] for w in wiersze)
    ops_p = sum(w["ops_pod"] for w in wiersze)
    wg_projektu = ";".join(f"{w['projekt']}:{round(w['ops_glowna_proc'])}" for w in wiersze
                           if w["ops_glowna_proc"] and round(w["ops_glowna_proc"]) and w["ops_glowna"] >= 0.5)
    metryki = {
        "ops_koszt_usd": round(ops_g + ops_p, 2),
        "ops_glowna_koszt_usd": round(ops_g, 2),
        "ops_glowna_proc": _proc(ops_g, koszt),
        "ci_glowna_koszt_usd": round(sum(w["ci_glowna"] for w in wiersze), 2),
        "ops_podagenci_proc": _proc(ops_p, ops_g + ops_p),
        "ops_glowna_wg_projektu": wg_projektu or None,
        "ops_kandydaci_audytu": sum(1 for w in wiersze if w["kandydat"]),
        "zadania_na_sesje_mediana": statistics.median(zadania_wszystkie) if zadania_wszystkie else None,
        "sesje_ponad_150_zadan": sum(z > PROG_ZADAN for z in zadania_wszystkie),
    }
    return {"projekty": wiersze, "metryki": metryki, "globalni": agenci.get(globalne) or [],
            "prog_proc": prog_proc, "prog_usd": prog_usd}


def raport(z: dict) -> list:
    """Sekcja podsumowania „Kroki CI i deploy: sesja główna a podagenci”."""
    m = z["metryki"]
    proc = lambda v: "—" if v is None else f"{v}%"  # noqa: E731
    l = ["", t("op_tytul"), "", t("op_opis", prog=PROG_ZADAN, prog_proc=f"{z['prog_proc']:g}",
                                  prog_usd=f"{z['prog_usd']:g}"), "",
         t("op_suma", ops=f"{m['ops_koszt_usd']:.2f}", glowna=f"{m['ops_glowna_koszt_usd']:.2f}",
           udzial=proc(m["ops_glowna_proc"]), ci=f"{m['ci_glowna_koszt_usd']:.2f}", pod=proc(m["ops_podagenci_proc"]),
           mediana=m["zadania_na_sesje_mediana"] if m["zadania_na_sesje_mediana"] is not None else "—",
           ponad=m["sesje_ponad_150_zadan"], prog=PROG_ZADAN)]
    if z["globalni"]:
        l += ["", t("op_globalni", lista=", ".join(z["globalni"]))]
    wiersze = [w for w in z["projekty"] if w["koszt"] >= 0.01]
    if not wiersze:
        return l
    l += ["", t("op_kolumny"), "|---|---|---|---|---|---|---|---|---|---|"]
    for w in wiersze:
        kandydat = ", ".join(t("op_powod_" + p) for p in w["kandydat"]) or "—"
        mediana = "—" if w["zadania_mediana"] is None else f"{w['zadania_mediana']:g}"
        l.append(f"| {w['projekt']} | ${w['koszt']:.2f} | ${w['ci_glowna']:.2f} / ${w['deploy_glowna']:.2f} | "
                 f"${w['ci_pod']:.2f} / ${w['deploy_pod']:.2f} | {proc(w['ops_glowna_proc'])} | {w['sesje']} | "
                 f"{mediana} | {w['sesje_ponad_prog']} | {', '.join(w['agenci_ops']) or '—'} | {kandydat} |")
    kandydaci = [w["projekt"] for w in wiersze if w["kandydat"]]
    if kandydaci:
        l += ["", t("op_kandydaci", lista=", ".join(kandydaci))]
    return l
