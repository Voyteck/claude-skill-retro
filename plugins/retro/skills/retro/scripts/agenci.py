"""Agenci między retro: definicje z `.claude/agents`, migawka `agenci.csv`, zmiany konfiguracji i ich efekt
(PR przed i po zmianie), przydział zadań (kto robi PR jakiego rozmiaru, które agenty nie pracują).

Używają go `sygnaly.py` (sekcje w „Tokeny i efektywność pisania”) i `dopisz_metryki.py` (migawka na koniec retro).
Migawka zapisuje stan po zmianach retro; wiersze `RNN-start` to stan sprzed retro, gdy różni się od poprzedniego
zapisu (zmiana poza retro) albo od stanu po retro (pierwsza migawka agenta). Ograniczenia: `references/sygnaly.md`.
"""
import collections
import csv
import datetime as dt
import hashlib
import pathlib
import re
import statistics
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import tokeny  # noqa: E402
from teksty import t  # noqa: E402

PLIK_MIGAWKI = "agenci.csv"
POLA_MIGAWKI = ["retro", "data", "zrodlo", "agent", "model", "effort", "opis_sha", "tresc_sha", "zmieniony", "plik",
                "opis"]
STAN = ("model", "effort", "opis_sha", "tresc_sha")
PRZYROSTEK_STARTU = "-start"
MIN_PR = 5
WBUDOWANE = {"general-purpose", "explore", "plan", "statusline-setup", "claude-code-guide", "claude", "fork"}


# ---------------------------------------------------------------- definicje

def _sha(tekst: str) -> str:
    return hashlib.sha1(tekst.encode("utf-8")).hexdigest()[:10]


def frontmatter(tekst: str):
    """(pola nagłówka YAML jako napisy, treść po nagłówku) albo (None, tekst) bez nagłówka. Prosty YAML: `klucz: wartość`
    i wartości blokowe (`|`, `>`) z wcięciem."""
    linie = tekst.splitlines()
    if not linie or linie[0].strip() != "---":
        return None, tekst
    pola, klucz, koniec = {}, None, None
    for i, linia in enumerate(linie[1:], 1):
        if linia.strip() == "---":
            koniec = i
            break
        m = re.match(r"([A-Za-z_][\w-]*)\s*:\s*(.*)$", linia)
        if m and not linia[:1].isspace():
            klucz, wartosc = m.group(1), m.group(2).strip()
            pola[klucz] = "" if wartosc in ("|", ">", "|-", ">-") else wartosc.strip("'\"")
        elif klucz and linia.strip():
            pola[klucz] = (pola[klucz] + " " + linia.strip()).strip()
    if koniec is None:
        return None, tekst
    return pola, "\n".join(linie[koniec + 1:])


def data_zmiany(plik: pathlib.Path) -> str:
    """Data ostatniego commita pliku (git), a bez niego data modyfikacji. Checkout ustawia czas modyfikacji na dziś,
    dlatego git ma pierwszeństwo."""
    try:
        r = subprocess.run(["git", "-C", str(plik.parent), "log", "-1", "--format=%cs", "--", plik.name],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15)
        if r.returncode == 0 and re.fullmatch(r"\d{4}-\d{2}-\d{2}", r.stdout.strip()):
            zmiany = subprocess.run(["git", "-C", str(plik.parent), "status", "--porcelain", "--", plik.name],
                                    capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15)
            if not zmiany.stdout.strip():          # niezatwierdzona zmiana: liczy się czas modyfikacji
                return r.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    try:
        return dt.date.fromtimestamp(plik.stat().st_mtime).isoformat()
    except OSError:
        return ""


def wczytaj_definicje(katalogi: list) -> list:
    """[{agent, zrodlo, plik, model, effort, opis, opis_sha, tresc_sha, zmieniony, tokeny}] z `*.md` z nagłówkiem
    w katalogach [(źródło, katalog)]. Pliki bez nagłówka YAML pomijane (to nie definicje agentów)."""
    wynik = []
    for zrodlo, katalog in katalogi:
        for plik in sorted(pathlib.Path(katalog).glob("*.md")):
            try:
                tekst = plik.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            pola, tresc = frontmatter(tekst)
            if pola is None:
                continue
            opis = pola.get("description") or ""
            wynik.append({"agent": pola.get("name") or plik.stem, "zrodlo": zrodlo, "plik": str(plik),
                          "model": pola.get("model") or "inherit", "effort": pola.get("effort") or "",
                          "opis": opis, "opis_sha": _sha(opis), "tresc_sha": _sha(tresc.strip()),
                          "zmieniony": data_zmiany(plik), "tokeny": round(len(tekst) / 4)})
    return wynik


# ---------------------------------------------------------------- migawka agenci.csv

def wczytaj_migawki(plik: pathlib.Path) -> list:
    try:
        with plik.open(encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))
    except OSError:
        return []


def _wiersz(retro: str, data: str, d: dict) -> dict:
    w = {k: d.get(k) or "" for k in POLA_MIGAWKI}
    w.update({"retro": retro, "data": data, "opis": (d.get("opis") or "")[:160]})
    return w


def model_w_dniu(migawki: list, definicje: list):
    """Funkcja (agent, data) -> model agenta (pole `model` definicji) w dniu `data` albo None (agent nieznany albo
    `inherit`).
    Stan w dniu = pierwsza migawka od tego dnia (albo obecna definicja), jeśli plik nie zmienił się później
    (`zmieniony` ≤ data); inaczej ostatnia migawka sprzed tego dnia."""
    stany = collections.defaultdict(list)
    dzis = dt.date.today()
    for w in migawki:
        stany[w.get("agent")].append((_data(w.get("data")) or dt.date.min, _data(w.get("zmieniony")), w.get("model")))
    for d in definicje:
        stany[d.get("agent")].append((dzis, _data(d.get("zmieniony")), d.get("model")))
    for lista in stany.values():
        lista.sort(key=lambda x: x[0])

    def model(agent, data):
        lista = stany.get(agent) or []
        nast = next((x for x in lista if x[0] >= data), None)
        if nast and nast[1] and nast[1] > data:
            nast = None
        stan = nast or next((x for x in reversed(lista) if x[0] < data), None)
        if not stan or not stan[2] or stan[2] == "inherit":
            return None
        return stan[2]
    return model


def _ostatnie(wiersze: list) -> dict:
    ost = {}
    for w in wiersze:
        ost[(w["zrodlo"], w["agent"])] = w
    return ost


def zapisz_migawke(plik: pathlib.Path, retro: str, data: str, po: list, przed: list = None) -> dict:
    """Dopisuje stan agentów po retro `retro` (`po`, definicje) i, gdzie trzeba, stan sprzed retro (`przed`, z
    `agenci.json` wyniku `sygnaly.py`) jako `RNN-start`: gdy różni się od ostatniego zapisu agenta, a bez zapisu,
    gdy różni się od stanu po retro. Ponowne uruchomienie dla tego samego retro zastępuje jego wiersze."""
    stare = [w for w in wczytaj_migawki(plik) if w.get("retro") not in (retro, retro + PRZYROSTEK_STARTU)]
    ost = _ostatnie(stare)
    po_klucz = {(d["zrodlo"], d["agent"]): d for d in po}
    nowe_start = []
    for d in przed or []:
        klucz = (d["zrodlo"], d["agent"])
        wzor = ost.get(klucz) or po_klucz.get(klucz)
        if wzor is None or any((wzor.get(k) or "") != (d.get(k) or "") for k in STAN):
            nowe_start.append(_wiersz(retro + PRZYROSTEK_STARTU, data, d))
    nowe = [_wiersz(retro, data, d) for d in po]
    with plik.open("w", encoding="utf-8", newline="") as f:
        pisarz = csv.DictWriter(f, fieldnames=POLA_MIGAWKI, extrasaction="ignore", lineterminator="\n")
        pisarz.writeheader()
        pisarz.writerows(stare + nowe_start + nowe)
    return {"plik": str(plik), "agenci": len(nowe), "stan_przed_retro": len(nowe_start)}


def _opis_zmiany(a: dict, b: dict) -> list:
    co = []
    for k in ("model", "effort"):
        if (a.get(k) or "") != (b.get(k) or ""):
            co.append(f"{k} {a.get(k) or '—'} → {b.get(k) or '—'}")
    if a.get("opis_sha") != b.get("opis_sha"):
        co.append(t("ag_zm_opis"))
    if a.get("tresc_sha") != b.get("tresc_sha"):
        co.append(t("ag_zm_tresc"))
    return co


def _data(napis):
    try:
        return dt.date.fromisoformat((napis or "")[:10])
    except ValueError:
        return None


def zmiany(wiersze: list, obecne: list) -> list:
    """Zmiany konfiguracji agentów z historii migawek i stanu obecnego: [{agent, zrodlo, kiedy, data, co}].
    `kiedy`: numer retro, „przed RNN” (zmiana poza retro, zauważona na starcie RNN) albo „od ostatniego retro”."""
    wynik, historia = [], collections.defaultdict(list)
    for w in wiersze:
        historia[(w["zrodlo"], w["agent"])].append(w)
    pelne = [w["retro"] for w in wiersze if not w["retro"].endswith(PRZYROSTEK_STARTU)]
    pierwsza = pelne[0] if pelne else None

    def kiedy(retro):
        return t("ag_przed_retro", retro=retro[:-len(PRZYROSTEK_STARTU)]) if retro.endswith(PRZYROSTEK_STARTU) else retro

    for (zrodlo, agent), lista in historia.items():
        if lista[0]["retro"] not in (pierwsza, (pierwsza or "") + PRZYROSTEK_STARTU) and pierwsza:
            wynik.append({"agent": agent, "zrodlo": zrodlo, "kiedy": kiedy(lista[0]["retro"]),
                          "data": _data(lista[0]["zmieniony"]), "co": [t("ag_zm_nowy")]})
        for a, b in zip(lista, lista[1:]):
            co = _opis_zmiany(a, b)
            if co:
                wynik.append({"agent": agent, "zrodlo": zrodlo, "kiedy": kiedy(b["retro"]),
                              "data": _data(b["zmieniony"]) or _data(b["data"]), "co": co})
    if wiersze:
        ost = _ostatnie(wiersze)
        teraz = {(d["zrodlo"], d["agent"]): d for d in obecne}
        for klucz, d in teraz.items():
            if klucz not in ost:
                wynik.append({"agent": d["agent"], "zrodlo": d["zrodlo"], "kiedy": t("ag_od_retro"),
                              "data": _data(d["zmieniony"]), "co": [t("ag_zm_nowy")], "biezaca": True})
            else:
                co = _opis_zmiany(ost[klucz], d)
                if co:
                    wynik.append({"agent": d["agent"], "zrodlo": d["zrodlo"], "kiedy": t("ag_od_retro"),
                                  "data": _data(d["zmieniony"]), "co": co, "biezaca": True})
        ostatnia = pelne[-1] if pelne else None
        for klucz, w in ost.items():
            if klucz not in teraz and w["retro"] == ostatnia:
                wynik.append({"agent": w["agent"], "zrodlo": w["zrodlo"], "kiedy": t("ag_od_retro"), "data": None,
                              "co": [t("ag_zm_usuniety")], "biezaca": True})
    return sorted(wynik, key=lambda z: (z["data"] or dt.date.min, z["agent"]))


# ---------------------------------------------------------------- efekt zmian (PR przed i po)

def typ_pasuje(typ: str, agent: str) -> bool:
    typ = typ or ""
    return typ == agent or typ.endswith(":" + agent)


def udzial_agenta(r: dict, agent: str):
    """(koszt agenta na tym PR, czas jego pierwszej pracy) albo None."""
    for typ, (koszt, ts) in (r.get("pr_typy") or {}).items():
        if typ_pasuje(typ, agent):
            return koszt, ts
    return None


def opis_strony(lista: list, agent: str, progi=None) -> dict:
    import efektywnosc
    if not lista:
        return {"pr": 0}
    rozm = collections.Counter(efektywnosc.rozmiar(r["linie"], progi) for r in lista)
    return {"pr": len(lista), "z_poprawka": round(100 * sum(r["rundy"] > 0 for r in lista) / len(lista)),
            "agent": statistics.mean(udzial_agenta(r, agent)[0] for r in lista),
            "na_pr": statistics.mean(sum(r["pr_koszt"].values()) for r in lista),
            "rozmiary": " ".join(f"{k}{rozm[k]}" for k in ("S", "M", "L", "?") if rozm[k])}


def efekt_zmian(lista_zmian: list, polaczone: list, od_tabel: dt.date, progi=None) -> list:
    """[(zmiana, przed, po)] dla zmian z datą od `od_tabel` (zakres tabel). PR przypisany po dacie pierwszej pracy
    agenta na nim; dzień zmiany pominięty (nie wiadomo, przed czy po)."""
    wynik = []
    for z in lista_zmian:
        if not z["data"] or z["data"] < od_tabel or t("ag_zm_usuniety") in z["co"]:
            continue
        przed, po = [], []
        for r in polaczone or []:
            u = udzial_agenta(r, z["agent"]) if r.get("pr_koszt") is not None else None
            czas = tokeny.czas_lokalny(u[1]) if u else None
            if not czas:
                continue
            (przed if czas.date() < z["data"] else po if czas.date() > z["data"] else []).append(r)
        wynik.append((z, opis_strony(przed, z["agent"], progi), opis_strony(po, z["agent"], progi)))
    return wynik


# ---------------------------------------------------------------- przydział zadań

def starty(zrodla: list, od, do) -> dict:
    """{typ: {"starty": n, "z_pr": n, "konf": Counter("Model · poziom")}} ze startów podagentów w oknie."""
    import efektywnosc
    wynik = collections.defaultdict(lambda: {"starty": 0, "z_pr": 0, "konf": collections.Counter()})
    for dane in zrodla:
        agenci = dane.get("agenci") or {}
        for e in dane.get("zdarzenia") or []:
            czas = tokeny.czas_lokalny(e.get("ts") or "")
            if e.get("rodzaj") != "start" or not czas or not (od <= czas < do):
                continue
            a = agenci.get(e.get("agent") or "", {})
            w = wynik[e.get("typ") or "?"]
            w["starty"] += 1
            w["z_pr"] += bool(e.get("pr"))
            poziom = (a.get("tokeny") or {}).get("eff") or e.get("effort_zadany")
            w["konf"][efektywnosc.konfiguracja(e.get("model") or a.get("model"), poziom)] += 1
    return dict(wynik)


def wykonawca(r: dict) -> str:
    import efektywnosc
    if r.get("pr_koszt") is None or not r.get("pr_impl"):
        return t("ag_sesja_glowna")
    typ, model, poziom, _ = r["pr_impl"]
    return f"{typ} · {efektywnosc.konfiguracja(model, poziom)}"


def przydzial_pr(polaczone: list, progi=None) -> dict:
    """{(rozmiar, wykonawca): [PR]} dla scalonych PR z tabel (kilka tygodni)."""
    import efektywnosc
    grupy = collections.defaultdict(list)
    for r in polaczone or []:
        grupy[(efektywnosc.rozmiar(r["linie"], progi), wykonawca(r))].append(r)
    return grupy


# ---------------------------------------------------------------- raport i metryki

def _usd(v):
    return "—" if v is None else f"${v:.2f}"


def _strona(o: dict) -> str:
    if not o["pr"]:
        return "—"
    gw = "" if o["pr"] >= MIN_PR else "*"
    return (f"{o['pr']}{gw} PR · {o['z_poprawka']}% · {_usd(o['agent'])} / {_usd(o['na_pr'])} · {o['rozmiary']}")


def raport(definicje: list, wzorce: list, lista_zmian: list, efekty: list, przydzial: dict, starty_okna: dict,
           migawki: bool) -> list:
    """Sekcje: obecna konfiguracja agentów (z opisem), zmiany konfiguracji i efekt, przydział zadań."""
    import efektywnosc
    l = []
    if definicje:
        l += ["", t("ef_agenci_tytul"), "", t("ag_kolumny"), "|---|---|---|---|---|---|---|---|"]
        for d in definicje:
            s = starty_okna.get(d["agent"]) or next((v for k, v in starty_okna.items() if typ_pasuje(k, d["agent"])), None)
            opis = (d["opis"] or "—").replace("|", "/")
            opis = opis if len(opis) <= 90 else opis[:89] + "…"
            l.append(f"| {d['agent']} | {efektywnosc.etykieta_roli(efektywnosc.rola(True, d['agent'], wzorce))} | "
                     f"{d['model']} | {d['effort'] or '—'} | {d['zrodlo']} | {s['starty'] if s else 0} | "
                     f"{d['zmieniony'] or '—'} | {opis} |")
    l += ["", t("ag_zmiany_tytul"), ""]
    if not migawki:
        l.append(t("ag_zmiany_pierwsza"))
    elif not lista_zmian:
        l.append(t("ag_zmiany_brak"))
    else:
        l += [t("ag_zmiany_opis", min_pr=MIN_PR), "", t("ag_zmiany_kolumny"), "|---|---|---|---|---|---|"]
        efekt = {id(z): (p, q) for z, p, q in efekty}
        for z in lista_zmian:
            p, q = efekt.get(id(z), ({"pr": 0}, {"pr": 0}))
            poza = id(z) not in efekt and t("ag_zm_usuniety") not in z["co"]
            l.append(f"| {z['agent']} ({z['zrodlo']}) | {z['kiedy']} | {z['data'] or '—'} | {', '.join(z['co'])} | "
                     f"{t('ag_poza_tabelami') if poza else _strona(p)} | {'' if poza else _strona(q)} |")
    l += ["", t("ag_przydzial_tytul"), "", t("ag_przydzial_opis"), ""]
    if przydzial:
        l += [t("ag_przydzial_kolumny"), "|---|---|---|---|"]
        kolejnosc = {"S": 0, "M": 1, "L": 2, "?": 3}
        for (rozm, kto), lista in sorted(przydzial.items(), key=lambda x: (kolejnosc[x[0][0]], -len(x[1]), x[0][1])):
            o = efektywnosc.opis_pr(lista)
            l.append(f"| {rozm} | {kto} | {o['pr']} | {o['z_poprawka']:g}% |")
    else:
        l.append(t("ag_przydzial_brak"))
    if starty_okna:
        l += ["", t("ag_starty_kolumny"), "|---|---|---|---|---|---|"]
        zdefiniowane = {d["agent"] for d in definicje}
        for typ, s in sorted(starty_okna.items(), key=lambda x: -x[1]["starty"]):
            if any(typ_pasuje(typ, a) for a in zdefiniowane):
                zrodlo = t("ag_def_wlasny")
            elif typ.lower() in WBUDOWANE:
                zrodlo = t("ag_def_wbudowany")
            else:
                zrodlo = t("ag_def_inny")
            konf = ", ".join(f"{k} {n}" for k, n in s["konf"].most_common(3))
            l.append(f"| {typ} | {efektywnosc.etykieta_roli(efektywnosc.rola(True, typ, wzorce))} | {zrodlo} | "
                     f"{s['starty']} | {s['z_pr']} | {konf} |")
    nieuzywane = nieuzywani(definicje, starty_okna)
    if nieuzywane:
        l += ["", t("ag_nieuzywane", lista=", ".join(f"`{a}`" for a in nieuzywane))]
    l += ["", t("ag_ograniczenia")]
    return l


def nieuzywani(definicje: list, starty_okna: dict) -> list:
    return sorted({d["agent"] for d in definicje if not any(typ_pasuje(k, d["agent"]) for k in starty_okna)})


def metryki_okna(definicje: list, lista_zmian: list, starty_okna: dict, polaczone, od, do) -> dict:
    """Kolumny `metryki.csv` od 0.6.0."""
    w_oknie = [r for r in polaczone or [] if od <= r["scalony"] < do]
    sesja = sum(1 for r in w_oknie if wykonawca(r) == t("ag_sesja_glowna"))
    return {"agenci_zdefiniowani": len(definicje),
            "agenci_nieuzywani": len(nieuzywani(definicje, starty_okna)),
            "agenci_zmiany_od_retro": sum(1 for z in lista_zmian if z.get("biezaca")),
            "pr_bez_agenta_proc": round(100 * sesja / len(w_oknie), 1) if polaczone is not None and w_oknie else None}
