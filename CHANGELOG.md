# Zmiany

## 0.1.5 · 2026-10-20

- **Źródła zdalne trendu tokenów** (`zrodla_zdalne`, domyślnie brak): druga maszyna z Claude Code, np. sandbox.
  Dane można wziąć na dwa sposoby:
  - `polecenie` (np. `ssh -T host python3 -`, także z `docker exec` w środku): skrypt podaje na stdin nowy
    samodzielny `scripts/zbierz_liczby.py`, który wypisuje same liczby z transkrypcji tamtej maszyny, bez treści
    rozmów, i niczego tam nie zapisuje;
  - `plik`: ten sam wynik zapisany wcześniej przez właściciela.

  Na każde źródło przypada jedna próba, bez ponawiania; gdy się nie uda, podsumowanie podaje przyczynę, a skrypt
  liczy dalej. Każde źródło ma osobne archiwum `dane/tokeny-archiwum-<nazwa>.json` i wiersze `zrodlo=<nazwa>`
  w `tokeny-tydzien.csv`. Format jest zgodny z ręcznym odczytem sandboksa z 10-20 (`sandbox-liczby.json`,
  `tokeny-archiwum-sandbox.json`). `--bez-zdalnych` pomija źródła zdalne w danym przebiegu.
- **Poprawka 0.1.4:** zapis trendu sklejał wiersze innych źródeł, które miały ten sam tydzień (np. dwa okna
  `sandbox-pomiar` z 09-26), i czyścił kolumny, których skrypt nie liczy (`*_sygnaly`, `pokrycie_wiad_proc`), oraz
  ręczne uwagi w `pokrycie`. Teraz wiersze obcych źródeł zostają dosłownie, a w wierszach skryptu zostają nieznane
  kolumny i cudze uwagi.
- Źródło z kilkoma wierszami na tydzień (pomiary okienne) nie dostaje tabeli trendu.
- Wiadomości właściciela nie obejmują promptów `claude -p` (entrypoint `sdk-cli`).
- `SKILL.md`, krok 1: gdy źródła zdalnego nie da się odczytać, Claude nie ponawia połączenia, tylko podaje
  użytkownikowi polecenie do uruchomienia u siebie.
- Testy: 40 (było 35).

## 0.1.4 · 2026-10-20

Decyzje właściciela z R03 (sekcja 10), po wydaniu 0.1.3.

- **Trend tokenów tydzień po tygodniu.** `sygnaly.py` dopisuje do `tokeny-tydzien.csv` w katalogu roboczym
  (commitowany) wiersz na tydzień, bez duplikatów: tydzień niepełny jest nadpisywany. Kluczem jest para (tydzień,
  źródło), więc skrypt pisze tylko `zrodlo=lokalne`, a wiersze innych źródeł (np. sandbox) zostają nietknięte.
  Kolumny są zgodne z ręcznym `tokeny-tydzien-lokalne.csv` z R03. Podsumowanie ma sekcję „Trend tokenów”:
  ostatnie 4 tygodnie wobec mediany 8 wcześniejszych, ze strzałkami i listą wskaźników, które się pogarszają.
- **Archiwum liczb** `dane/tokeny-archiwum.json`: wywołania, czasy wiadomości i kompaktów, `cost-state`, bez treści
  rozmów. Chroni trend przed `cleanupPeriodDays` (w R03 zniknęły tak sesje z 09-19). Format jest zgodny z archiwum
  założonym ręcznie w R03. `--bez-trendu` pomija archiwum i trend.
- Cennik i liczenie kosztu wydzielone do `scripts/tokeny.py`. W cenniku doszło `rodziny_biezace`, potrzebne do
  kolumny „koszt w cenach bieżących modeli”.
- Wiadomości właściciela nie obejmują już briefów innych sesji („Background (from the session…”),
  `<system-reminder>` ani `<cross-session-message>`.
- `SKILL.md`:
  - krok 1: czytanie trendu;
  - krok 4: „Zrobić teraz” od razu jako karta z przejściem do folderu projektu w briefie, bo w turze wywołanej
    zdarzeniem automatycznym aplikacja pozwala tylko zaproponować kartę, a karta nie wskazuje folderu;
  - krok 5: commit `tokeny-tydzien.csv`.
- Nie ma jeszcze źródła zdalnego (sandbox przez ssh, opcjonalne pole konfiguracji): to następny krok.
- Testy: 35 (było 30).

## 0.1.3 · 2026-10-20

Propozycje z retro R02 (sekcja 10) i R03 (sekcje 2a, 7, 10).

- **Okno od godziny commita poprzedniego retro**, nie od północy: wiadomości, pytania, błędy, commity, PR-y, CI
  i tokeny z sesji tamtego retro sprzed jego zakończenia nie zawyżają nowego okna (R02: 52 pytania zamiast 24).
  `--od` przyjmuje też godzinę (`2026-10-17T20:52`), `--od-poczatku-dnia` wraca do starego zachowania.
- **Klasa `fakt`** dla pytań z „[fakt]” (hook Z-004 je dopuszcza bez rekomendacji): nie wchodzą już do
  `bez_rekomendacji`, a odpowiedź własnym tekstem nie jest liczona jako `wlasna`. Kolumna `pyt_fakt`.
- **Tokeny i koszt** liczone w skrypcie zamiast ręcznie przez podagentów (R03 2a): wywołania deduplikowane po
  `message.id`, razem z transkrypcjami podagentów; koszt w cenach API jako miara względna z cennikiem
  w `references/cennik.json` (nadpisania w polu `cennik` konfiguracji); koszt na wiadomość; mediana kontekstu sesji
  głównej i odsetek wywołań > 200k; udział podagentów w koszcie i udział Opusa w koszcie podagentów; wybudzenia
  (zapis cache > 50k po przerwie > 1 h) z listą; kontekst startowy sesji; najdroższe sesje; koszt w tabelach
  projektów i sesji. Na danych R02 i R03 wyniki zgadzają się z ręczną analizą R03 (np. wybudzenia R02 $9,10).
- **Praca bez lokalnych sesji:** commity i PR-y bez zapisu transkrypcji sesji repo w ±30 min (`commity_bez_sesji`,
  `pr_bez_sesji`) i uwaga w podsumowaniu (childproxy R03: 190 z 205 commitów). Pole `transkrypcje_dodatkowe`
  dołącza transkrypcje skopiowane z innej maszyny.
- **Linie reguł:** pole `katalogi_regul_osobno` (np. `repo-roots/` z kopiami `CLAUDE.md` dla przyszłych repo)
  liczy takie katalogi osobno (`claude_md_linie_osobno`); podsumowanie podpowiada kandydatów (≥ 3 zagnieżdżone
  `CLAUDE.md` w jednym katalogu).
- **`metryki.csv` zgodnie wstecz:** nowe kolumny na końcu nagłówka, za `zobowiazania_aktywne` (także
  `pyt_bez_wyboru`, dotąd tylko w `metryki.json`). Nowy skrypt `dopisz_metryki.py` dopisuje wiersz retro
  i rozszerza nagłówek starszego pliku; ponowne uruchomienie zastępuje wiersz.
- `SKILL.md`: przed werdyktem „martwe/porzucić” pytanie, czy ktoś tego używa; krok 1 korzysta z metryk tokenów;
  krok 5 dopisuje metryki skryptem.
- Testy: 30 (było 21).

## 0.1.2 · 2026-10-10

Poprawki po pierwszym retro na pełnym koncie (R01: 43 sesje, 6 projektów).

- **Sekrety nie trafiają do wyciągów.** `sygnaly.py` zamazuje przed zapisem ciągi wyglądające na sekrety
  (`gh secret set … --body`, `NAZWA_KEY=…`, `Bearer …`, znane przedrostki kluczy, klucze prywatne, długie ciągi
  liter i cyfr); zostawia hashe commitów i digesty obrazów. W R01 klucz wklejony do rozmowy trafił do `dane/`
  i do kontekstu podagentów.
- **Wiadomości wysłane w trakcie pracy Claude'a są liczone.** Były zapisane tylko jako `queued_command` i ginęły
  z osi czasu (w jednej sesji 8 wiadomości, w tym kluczowe dla kosztów). Oś czasu oznacza je „w trakcie pracy
  Claude'a”.
- **Sesje uruchomione w scratchpadzie** (testy `claude -p`) są pomijane, bo zawyżały liczbę sesji i wiadomości.
- **Pliki reguł:** liczone są śledzone `CLAUDE.md` na dowolnej głębokości repo; podsumowanie pokazuje, o ile
  commitów checkout jest za zdalną gałęzią (wtedy reguły na dysku są nieaktualne), i wymienia projekty z pamięcią
  bez lokalnej sesji w oknie.
- **Retencja:** ostrzeżenie, gdy okno retro sięga dalej niż `cleanupPeriodDays`.
- `SKILL.md`: na Windows skrypty uruchamia się przez `py`, gdy `python` to atrapa ze Sklepu Microsoft; przy
  ponad 8 pozycjach „czeka na użytkownika” pytania łączy się per projekt, sprawy bezpieczeństwa osobno.
- Testy: 21 (było 14).

## 0.1.1 · 2026-10-09

- Przypomnienie i README katalogu roboczego podają krótkie polecenie `/retro`. Sprawdzone w Claude Code
  2.1.293 (Windows): skill pluginu odpowiada na samą nazwę, gdy żadne inne polecenie jej nie zajmuje; pełna
  nazwa `/retro:retro` działa zawsze.

## 0.1.0 · 2026-10-09

Pierwsza wersja uniwersalna, wydzielona z prywatnego skillu retro po retro zero (R00).

- Tryb konta (wszystkie projekty z transkrypcji) i tryb projektu (`.retro/` w repo).
- Projekty i repozytoria wykrywane przez git z katalogów sesji; poprawki nazw w konfiguracji.
- Procedura z R00: jedno pytanie = jedna decyzja, sekcja „Czeka na użytkownika”, `nauki.md` na wiedzę
  przekrojową, zasada „mechanizm zamiast tekstu”.
- Klasa odpowiedzi „bez wyboru” (`[No preference]`).
- Kalendarz dni roboczych: polski albo sam weekend, plus własne dni wolne.
- Hook przypomnienia w pluginie (bash z wykrywaniem Pythona).
- Poprawka nazwy projektu w konfiguracji zmienia tylko nazwę; repo nadal wykrywane przez git.
- Testy na sztucznych transkrypcjach (14).
