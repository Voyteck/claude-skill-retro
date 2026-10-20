"""Tokeny i koszt z transkrypcji Claude Code: cennik, wywołania API, archiwum liczb i trend tydzień po tygodniu.

Używa go `sygnaly.py`. Trend: `<katalog roboczy>/tokeny-tydzien.csv` (commitowany), jeden wiersz na tydzień
(poniedziałek, czas lokalny) i źródło; skrypt pisze tylko wiersze `zrodlo=lokalne`, inne źródła (np. sandbox)
i nieznane kolumny zostawia. Archiwum: `<katalog roboczy>/dane/tokeny-archiwum.json` z samymi liczbami (bez treści
rozmów), bo Claude Code kasuje transkrypcje po `cleanupPeriodDays`; każdy przebieg dopisuje to, co widzi, a trend
liczy się z sumy archiwum i transkrypcji.
"""
import csv
import collections
import datetime as dt
import json
import os
import pathlib
import statistics

PLIK_CENNIKA = pathlib.Path(__file__).resolve().parent.parent / "references" / "cennik.json"
PLIK_TRENDU = "tokeny-tydzien.csv"
PLIK_ARCHIWUM = pathlib.Path("dane") / "tokeny-archiwum.json"
ZRODLO = "lokalne"

# Wybudzenie = wywołanie sesji głównej, które po przerwie zapisuje od nowa duży cache.
PROG_WYBUDZENIA_TOKENY = 50_000
PROG_WYBUDZENIA_H = 1
PROG_DUZEGO_KONTEKSTU = 200_000

KOLUMNY_TRENDU = [
    "tydzien", "zrodlo", "dni_z_sesjami", "sesje", "sesje_headless", "wiad_wlasciciela", "wywolania_api",
    "koszt_api_usd", "koszt_api_usd_ceny_55", "koszt_na_wiad", "wywolania_na_wiad", "kontekst_mediana", "kontekst_p90",
    "proc_wywolan_ponad_200k", "proc_kosztu_odczyt_cache", "proc_kosztu_zapis_cache", "wybudzenia",
    "wybudzenia_koszt_usd", "proc_kosztu_podagentow", "proc_kosztu_podagentow_opus", "kontekst_startowy_mediana",
    "kompakty", "wiad_wlasciciela_sygnaly", "sesje_sygnaly", "pokrycie_wiad_proc", "pokrycie",
    "koszt_cost_state_usd", "koszt_policzony_tych_sesji",
]
# Wskaźniki trendu w podsumowaniu; dla każdego więcej = gorzej.
WSKAZNIKI_TRENDU = [
    ("koszt_na_wiad", "koszt na wiadomość (USD)"),
    ("wywolania_na_wiad", "wywołania API na wiadomość"),
    ("kontekst_mediana", "mediana kontekstu sesji głównej"),
    ("proc_wywolan_ponad_200k", "% wywołań sesji głównej > 200k"),
    ("wybudzenia_koszt_usd", "koszt wybudzeń (USD)"),
    ("proc_kosztu_podagentow_opus", "% kosztu podagentów na Opusie"),
    ("kontekst_startowy_mediana", "kontekst startowy sesji"),
    ("koszt_api_usd", "koszt tygodnia (USD)"),
]
OSTATNIE_TYGODNIE, WCZESNIEJSZE_TYGODNIE, PROG_ZMIANY = 4, 8, 0.2


# ---------------------------------------------------------------- cennik

def wczytaj_cennik(konf: dict) -> dict:
    """Cennik z references/cennik.json; pole `cennik` konfiguracji nadpisuje lub dodaje modele i stałe."""
    try:
        cennik = json.loads(PLIK_CENNIKA.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cennik = {"modele": {}}
    wlasny = konf.get("cennik") or {}
    modele = dict(cennik.get("modele") or {})
    modele.update(wlasny.get("modele") or {})
    cennik.update({k: v for k, v in wlasny.items() if k != "modele"})
    cennik["modele"] = modele
    return cennik


def stawki(model: str, cennik: dict):
    """Stawki modelu po najdłuższym pasującym przedrostku identyfikatora albo None."""
    model = (model or "").replace("[1m]", "")
    pasujace = [k for k in cennik.get("modele", {}) if model.startswith(k)]
    return cennik["modele"][max(pasujace, key=len)] if pasujace else None


def model_biezacy(model: str, cennik: dict) -> str:
    """Model z `rodziny_biezace` cennika dla rodziny modelu (opus, sonnet, haiku…) albo sam model."""
    for rodzina, biezacy in (cennik.get("rodziny_biezace") or {}).items():
        if rodzina in (model or ""):
            return biezacy
    return model


def czesci_kosztu(w: dict, cennik: dict, model: str = None):
    """Koszt wywołania w USD w podziale na części (None, gdy modelu nie ma w cenniku)."""
    s = stawki(model or w["model"], cennik)
    if s is None:
        return None
    mnoznik = 1.0
    prog = s.get("powyzej") or {}
    if prog and w["kontekst"] > prog.get("kontekst", float("inf")):
        mnoznik = prog.get("mnoznik", 1)
    if w["fast"]:
        mnoznik *= cennik.get("mnoznik_fast", 1)
    return {"wejscie": w["wejscie"] * s.get("wejscie", 0) * mnoznik / 1e6,
            "wyjscie": w["wyjscie"] * s.get("wyjscie", 0) * mnoznik / 1e6,
            "zapis": (w["zapis_5m"] * s.get("zapis_5m", 0) + w["zapis_1h"] * s.get("zapis_1h", 0)) * mnoznik / 1e6,
            "odczyt": w["odczyt"] * s.get("odczyt", 0) * mnoznik / 1e6,
            "web_search": w["web_search"] * cennik.get("web_search_za_zapytanie", 0)}


def koszt_wywolania(w: dict, cennik: dict, tylko_zapis=False):
    """Koszt wywołania w USD (None, gdy modelu nie ma w cenniku); tylko_zapis = sama część zapisu cache."""
    c = czesci_kosztu(w, cennik)
    if c is None:
        return None
    return c["zapis"] if tylko_zapis else sum(c.values())


def czas_lokalny(ts: str):
    try:
        return dt.datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone()
    except (ValueError, AttributeError):
        return None


def wywolanie_api(d: dict, czas, podagent: bool):
    """Rekord asystenta z `usage` i `message.id` → (id, wywołanie) albo None."""
    wiad = d.get("message") or {}
    u = wiad.get("usage")
    if not isinstance(u, dict) or not wiad.get("id") or not wiad.get("model") or wiad["model"] == "<synthetic>":
        return None
    zapis = u.get("cache_creation_input_tokens") or 0
    rozbicie = u.get("cache_creation") or {}
    zapis_1h = rozbicie.get("ephemeral_1h_input_tokens") or 0
    w = {"czas": czas, "podagent": podagent, "model": wiad["model"], "ep": d.get("entrypoint"),
         "wejscie": u.get("input_tokens") or 0, "wyjscie": u.get("output_tokens") or 0,
         "zapis_5m": zapis - zapis_1h, "zapis_1h": zapis_1h, "odczyt": u.get("cache_read_input_tokens") or 0,
         "fast": u.get("speed") == "fast", "web_search": (u.get("server_tool_use") or {}).get("web_search_requests") or 0}
    w["kontekst"] = w["wejscie"] + zapis + w["odczyt"]
    return wiad["id"], w


def dodaj_wywolanie(wywolania: dict, wynik):
    """Ten sam message.id jest zapisany raz na blok treści, z częściowym `usage` w trakcie strumienia:
    zostaje rekord z największym `output_tokens` i najwcześniejszym czasem."""
    if wynik is None:
        return
    mid, w = wynik
    stary = wywolania.get(mid)
    if stary is None:
        wywolania[mid] = w
    elif w["wyjscie"] >= stary["wyjscie"]:
        w["czas"] = min(w["czas"], stary["czas"])
        wywolania[mid] = w
    else:
        stary["czas"] = min(w["czas"], stary["czas"])


# ---------------------------------------------------------------- archiwum

def do_rekordu(w: dict, sid: str) -> dict:
    return {"ts": w["czas"].isoformat(), "s": sid[:8], "sub": w["podagent"], "model": w["model"], "ep": w.get("ep"),
            "inp": w["wejscie"], "out": w["wyjscie"], "cw5": w["zapis_5m"], "cw1h": w["zapis_1h"], "cr": w["odczyt"],
            "speed": "fast" if w["fast"] else "standard", "ws": w["web_search"]}


def z_rekordu(r: dict) -> dict:
    w = {"czas": czas_lokalny(r.get("ts") or ""), "sesja": r.get("s") or "?", "podagent": bool(r.get("sub")),
         "model": r.get("model") or "?", "ep": r.get("ep"), "wejscie": r.get("inp") or 0, "wyjscie": r.get("out") or 0,
         "zapis_5m": r.get("cw5") or 0, "zapis_1h": r.get("cw1h") or 0, "odczyt": r.get("cr") or 0,
         "fast": r.get("speed") == "fast", "web_search": r.get("ws") or 0}
    w["kontekst"] = w["wejscie"] + w["zapis_5m"] + w["zapis_1h"] + w["odczyt"]
    return w


def czas_naiwny(czas) -> str:
    """Czas lokalny bez strefy (format zdarzeń w archiwum)."""
    return czas.astimezone().replace(tzinfo=None).isoformat()


def czas_zdarzenia(t: str):
    """Czas zdarzenia z archiwum: naiwny lokalny (format archiwum) albo ze strefą (wynik `zbierz_liczby.py`)."""
    if t.endswith("Z") or "+" in t[10:] or "-" in t[10:]:
        c = czas_lokalny(t)
        return c.replace(tzinfo=None) if c else None
    try:
        return dt.datetime.fromisoformat(t)
    except ValueError:
        return None


def wczytaj_archiwum(plik: pathlib.Path) -> dict:
    arch = {"calls": {}, "owner": [], "compacts": [], "cost_state": {}}
    try:
        arch.update(json.loads(plik.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass
    return arch


def zapisz_archiwum(plik: pathlib.Path, arch: dict):
    plik.parent.mkdir(parents=True, exist_ok=True)
    tymczasowy = plik.with_name(plik.name + ".tmp")
    tymczasowy.write_text(json.dumps(arch, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    os.replace(tymczasowy, plik)


def scal_odczyt(plik: pathlib.Path, odczyt: dict) -> dict:
    """Dopisuje wynik `zbierz_liczby.py` (albo archiwum w tym samym formacie) do archiwum źródła i zwraca całość:
    wywołania po message.id, wiadomości i kompakty sumą zbiorów (czas lokalny bez strefy), cost-state maksimum."""
    arch = wczytaj_archiwum(plik)
    arch["calls"].update(odczyt.get("calls") or {})
    for klucz in ("owner", "compacts"):
        zdarzenia = {tuple(x) for x in arch[klucz]}
        for t, sid in odczyt.get(klucz) or []:
            c = czas_zdarzenia(t)
            if c:
                zdarzenia.add((c.isoformat(), sid))
        arch[klucz] = sorted(zdarzenia)
    for sid, v in (odczyt.get("cost_state") or {}).items():
        arch["cost_state"][sid] = max(arch["cost_state"].get(sid, 0), v or 0)
    if odczyt.get("meta"):
        arch.setdefault("odczyty", []).append(odczyt["meta"])
    zapisz_archiwum(plik, arch)
    return arch


def odczytaj_zrodlo(zrodlo: dict, katalog: pathlib.Path, limit_s: int = 300):
    """Odczyt źródła zdalnego z konfiguracji: (dane, opis) albo (None, opis błędu). `polecenie` (lista argumentów
    albo napis) dostaje `zbierz_liczby.py` na stdin i zwraca JSON na stdout; `plik` to taki JSON zapisany wcześniej.
    Jedna próba, bez ponawiania: brak odpowiedzi maszyny zdalnej to nie awaria retro."""
    import shlex
    import subprocess
    if zrodlo.get("polecenie"):
        polecenie = zrodlo["polecenie"]
        if isinstance(polecenie, str):
            polecenie = shlex.split(polecenie)
        skrypt = (pathlib.Path(__file__).resolve().parent / "zbierz_liczby.py").read_bytes()
        try:
            r = subprocess.run(polecenie, input=skrypt, capture_output=True, timeout=zrodlo.get("limit_s", limit_s))
        except (OSError, subprocess.TimeoutExpired) as e:
            return None, f"polecenie nie zadziałało: {e}"
        if r.returncode != 0:
            return None, f"polecenie zwróciło {r.returncode}: " + r.stderr.decode("utf-8", "replace").strip()[:200]
        try:
            return json.loads(r.stdout.decode("utf-8")), "odczyt poleceniem"
        except ValueError:
            return None, "polecenie nie zwróciło JSON-a: " + r.stdout[:120].decode("utf-8", "replace")
    if zrodlo.get("plik"):
        p = pathlib.Path(zrodlo["plik"]).expanduser()
        p = p if p.is_absolute() else katalog / p
        try:
            dane = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            return None, f"nie da się odczytać pliku `{p}`: {e}"
        kiedy = (dane.get("meta") or {}).get("odczyt_utc") or (dane.get("meta") or {}).get("read_at_utc")
        if not kiedy:
            kiedy = dt.datetime.fromtimestamp(p.stat().st_mtime).astimezone().isoformat(timespec="minutes")
        return dane, f"plik `{p.name}` z {kiedy[:16]}"
    return None, "brak pola `polecenie` ani `plik`"


def aktualizuj_archiwum(plik: pathlib.Path, sesje: list) -> dict:
    """Dopisuje do archiwum wywołania, wiadomości właściciela, kompakty i `cost-state` sesji; zwraca całość.
    Archiwum ma pierwszeństwo tylko dla tego, czego transkrypcje już nie mają."""
    arch = wczytaj_archiwum(plik)
    wlasciciel = {tuple(x) for x in arch["owner"]}
    kompakty = {tuple(x) for x in arch["compacts"]}
    for s in sesje:
        sid = s.sid[:8]
        for mid, w in s.wywolania.items():
            arch["calls"][mid] = do_rekordu(w, sid)
        for czas, rodzaj, _ in s.zdarzenia:
            if rodzaj == "wlasciciel":
                wlasciciel.add((czas_naiwny(czas), sid))
            elif rodzaj == "kompakt":
                kompakty.add((czas_naiwny(czas), sid))
        if s.cost_state:
            arch["cost_state"][sid] = max(arch["cost_state"].get(sid, 0), s.cost_state)
    arch["owner"], arch["compacts"] = sorted(wlasciciel), sorted(kompakty)
    zapisz_archiwum(plik, arch)
    return arch


# ---------------------------------------------------------------- trend tygodniowy

def poniedzialek(d) -> dt.date:
    d = d.date() if isinstance(d, dt.datetime) else d
    return d - dt.timedelta(days=d.weekday())


def kwantyl(wartosci, q):
    if not wartosci:
        return None
    v = sorted(wartosci)
    k = (len(v) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (k - lo)


def wiersze_tygodni(arch: dict, cennik: dict, dzis: dt.date = None, zrodlo: str = ZRODLO) -> list:
    """Wiersze trendu źródła od tygodnia najstarszego wywołania archiwum do bieżącego."""
    dzis = dzis or dt.date.today()
    wywolania = [w for w in (z_rekordu(r) for r in arch.get("calls", {}).values()) if w["czas"]]
    if not wywolania:
        return []
    zdarzenia = lambda klucz: [c for c in (czas_zdarzenia(t) for t, _ in arch.get(klucz, [])) if c]  # noqa: E731
    wlasciciel = collections.Counter(poniedzialek(c) for c in zdarzenia("owner"))
    kompakty = collections.Counter(poniedzialek(c) for c in zdarzenia("compacts"))
    for w in wywolania:
        w["tydzien"] = poniedzialek(w["czas"])
        c = czesci_kosztu(w, cennik)
        w["czesci"] = c or {}
        w["koszt"] = sum(c.values()) if c else 0
        c55 = czesci_kosztu(w, cennik, model_biezacy(w["model"], cennik))
        w["koszt_biezacy"] = sum(c55.values()) if c55 else 0
    tygodnie = collections.defaultdict(list)
    sesje = collections.defaultdict(list)
    for w in wywolania:
        tygodnie[w["tydzien"]].append(w)
        if not w["podagent"]:
            sesje[w["sesja"]].append(w)
    start, wybudzenia, ostatni = collections.defaultdict(list), collections.defaultdict(lambda: [0, 0.0]), {}
    for sid, lista in sesje.items():
        lista.sort(key=lambda w: w["czas"])
        if lista[0]["ep"] != "sdk-cli":                 # `claude -p` nie ma narzutu sesji interaktywnej
            start[lista[0]["tydzien"]].append(lista[0]["kontekst"])
        ostatni[sid] = lista[-1]["tydzien"]
        for a, b in zip(lista, lista[1:]):
            if (b["zapis_5m"] + b["zapis_1h"] > PROG_WYBUDZENIA_TOKENY
                    and (b["czas"] - a["czas"]).total_seconds() > PROG_WYBUDZENIA_H * 3600):
                wybudzenia[b["tydzien"]][0] += 1
                wybudzenia[b["tydzien"]][1] += b["czesci"].get("zapis", 0)
    koszt_sesji = collections.Counter()
    for w in wywolania:
        koszt_sesji[w["sesja"]] += w["koszt"]
    cost_state, policzony = collections.Counter(), collections.Counter()
    for sid, v in (arch.get("cost_state") or {}).items():
        if v and sid in ostatni:
            cost_state[ostatni[sid]] += v
            policzony[ostatni[sid]] += koszt_sesji[sid]

    def zaokr(x, n=2):
        return "" if x is None else (int(round(x)) if n == 0 else round(x, n))

    wiersze, tydzien = [], poniedzialek(min(w["czas"] for w in wywolania))
    while tydzien <= poniedzialek(dzis):
        lista = tygodnie.get(tydzien, [])
        glowne = [w for w in lista if not w["podagent"]]
        pod = [w for w in lista if w["podagent"]]
        koszt = sum(w["koszt"] for w in lista)
        koszt_pod = sum(w["koszt"] for w in pod)
        wiad = wlasciciel.get(tydzien, 0)
        kontekst = [w["kontekst"] for w in glowne]
        udzial = lambda x: round(100 * x / koszt, 1) if koszt else ""  # noqa: E731
        uwagi = []
        if tydzien + dt.timedelta(days=6) >= dzis:
            uwagi.append("okres niezakończony")
        if not lista:
            uwagi.append("brak aktywności")
        wiersze.append({
            "tydzien": tydzien.isoformat(), "zrodlo": zrodlo,
            "dni_z_sesjami": len({w["czas"].date() for w in glowne}),
            "sesje": len({w["sesja"] for w in glowne if w["ep"] != "sdk-cli"}),
            "sesje_headless": len({w["sesja"] for w in glowne if w["ep"] == "sdk-cli"}),
            "wiad_wlasciciela": wiad, "wywolania_api": len(lista),
            "koszt_api_usd": zaokr(koszt), "koszt_api_usd_ceny_55": zaokr(sum(w["koszt_biezacy"] for w in lista)),
            "koszt_na_wiad": zaokr(koszt / wiad) if wiad else "",
            "wywolania_na_wiad": zaokr(len(lista) / wiad, 1) if wiad else "",
            "kontekst_mediana": zaokr(kwantyl(kontekst, 0.5), 0), "kontekst_p90": zaokr(kwantyl(kontekst, 0.9), 0),
            "proc_wywolan_ponad_200k": zaokr(100 * sum(k > PROG_DUZEGO_KONTEKSTU for k in kontekst) / len(kontekst), 1)
            if kontekst else "",
            "proc_kosztu_odczyt_cache": udzial(sum(w["czesci"].get("odczyt", 0) for w in lista)),
            "proc_kosztu_zapis_cache": udzial(sum(w["czesci"].get("zapis", 0) for w in lista)),
            "wybudzenia": wybudzenia[tydzien][0] if tydzien in wybudzenia else 0,
            "wybudzenia_koszt_usd": zaokr(wybudzenia[tydzien][1]) if tydzien in wybudzenia else 0,
            "proc_kosztu_podagentow": udzial(koszt_pod),
            "proc_kosztu_podagentow_opus": zaokr(100 * sum(w["koszt"] for w in pod if "opus" in w["model"]) / koszt_pod, 1)
            if koszt_pod else "",
            "kontekst_startowy_mediana": zaokr(statistics.median(start[tydzien]), 0) if start.get(tydzien) else "",
            "kompakty": kompakty.get(tydzien, 0),
            "pokrycie": "; ".join(uwagi),
            "koszt_cost_state_usd": zaokr(cost_state[tydzien]) if tydzien in cost_state else "",
            "koszt_policzony_tych_sesji": zaokr(policzony[tydzien]) if tydzien in policzony else "",
        })
        tydzien += dt.timedelta(days=7)
    return wiersze


def zapisz_trend(plik: pathlib.Path, nowe: list) -> list:
    """Scala nowe wiersze z plikiem trendu i zwraca wszystkie wiersze. Wiersze źródeł obecnych w `nowe` są
    kluczowane po (tydzien, zrodlo): wiersz z pliku zostaje, gdy widział więcej wywołań (dane usunięte przez
    retencję przed archiwum), a tydzień niepełny jest nadpisywany. Wiersze innych źródeł (np. pomiary ręczne,
    także po kilka na tydzień) zostają dosłownie."""
    stare, kolumny = [], list(KOLUMNY_TRENDU)
    if plik.is_file():
        with plik.open(encoding="utf-8", newline="") as f:
            czytnik = csv.DictReader(f)
            kolumny += [k for k in (czytnik.fieldnames or []) if k not in kolumny]
            stare = list(czytnik)
    klucz = lambda w: (w.get("tydzien", ""), w.get("zrodlo") or ZRODLO)  # noqa: E731
    wlasne = {w["zrodlo"] for w in nowe}
    obce = [w for w in stare if klucz(w)[1] not in wlasne]
    wiersze = {klucz(w): w for w in stare if klucz(w)[1] in wlasne}
    for w in nowe:
        stary = wiersze.get(klucz(w))
        try:
            zostaw = stary is not None and int(stary.get("wywolania_api") or 0) > int(w["wywolania_api"] or 0)
        except ValueError:
            zostaw = False
        if zostaw:
            if "z poprzedniego przebiegu" not in (stary.get("pokrycie") or ""):
                stary["pokrycie"] = "; ".join(x for x in (stary.get("pokrycie"), "wiersz z poprzedniego przebiegu "
                                              f"(teraz {w['wywolania_api']} wywołań, reszta usunięta przez retencję)") if x)
            stary["zrodlo"] = stary.get("zrodlo") or ZRODLO
        else:
            nowy = dict(stary or {}, **w)
            # własne uwagi skryptu są liczone od nowa; cudze (np. dopisane ręcznie) zostają
            cudze = [u for u in ((stary or {}).get("pokrycie") or "").split("; ")
                     if u and not u.startswith(("okres niezakończony", "brak aktywności"))]
            nowy["pokrycie"] = "; ".join(cudze + [u for u in (w.get("pokrycie") or "").split("; ") if u and u not in cudze])
            wiersze[klucz(w)] = nowy
    wynik = sorted(list(wiersze.values()) + obce, key=lambda w: (*klucz(w), w.get("okno_od") or ""))
    with plik.open("w", encoding="utf-8", newline="") as f:
        pisarz = csv.DictWriter(f, fieldnames=kolumny, restval="", extrasaction="ignore", lineterminator="\n")
        pisarz.writeheader()
        pisarz.writerows(wynik)
    return wynik


def liczba(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def trend(wiersze: list, zrodlo: str = ZRODLO, dzis: dt.date = None) -> list:
    """[(etykieta, mediana wcześniejszych, [(tydzień, wartość)] ostatnich, mediana ostatnich, kierunek, liczba
    wcześniejszych)] dla zakończonych tygodni źródła z aktywnością: ostatnie OSTATNIE_TYGODNIE wobec mediany
    WCZESNIEJSZE_TYGODNIE wcześniejszych."""
    dzis = dzis or dt.date.today()
    aktywne = sorted((w for w in wiersze if (w.get("zrodlo") or ZRODLO) == zrodlo and w.get("tydzien")
                      and dt.date.fromisoformat(w["tydzien"]) + dt.timedelta(days=6) < dzis
                      and (liczba(w.get("wywolania_api")) or 0) > 0), key=lambda w: w["tydzien"])
    wynik = []
    for kol, etykieta in WSKAZNIKI_TRENDU:
        wartosci = [(w["tydzien"], liczba(w.get(kol))) for w in aktywne]
        wartosci = [(t, v) for t, v in wartosci if v is not None]
        ostatnie = wartosci[-OSTATNIE_TYGODNIE:]
        wczesniej = wartosci[:-OSTATNIE_TYGODNIE][-WCZESNIEJSZE_TYGODNIE:]
        m_ost = statistics.median(v for _, v in ostatnie) if ostatnie else None
        m_wcz = statistics.median(v for _, v in wczesniej) if wczesniej else None
        if m_ost is None or m_wcz is None or len(wczesniej) < 3:
            kierunek = "za mało danych"
        elif m_wcz == 0:
            kierunek = "↑ pogorszenie" if m_ost > 0 else "≈"
        elif m_ost > m_wcz * (1 + PROG_ZMIANY):
            kierunek = "↑ pogorszenie"
        elif m_ost < m_wcz * (1 - PROG_ZMIANY):
            kierunek = "↓ poprawa"
        else:
            kierunek = "≈"
        wynik.append((etykieta, m_wcz, ostatnie, m_ost, kierunek, len(wczesniej)))
    return wynik
