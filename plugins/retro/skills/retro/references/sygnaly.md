# Sygnały i metryki: co znaczą i czego nie mówią

`scripts/sygnaly.py` czyta transkrypcje Claude Code z okna retro, gita i (gdy jest `gh`) GitHuba.

## Okno

Okno zaczyna się od **godziny commita**, którym poprzednie retro dostało `**Status:** zakończone` (szuka go w gicie
katalogu roboczego, gdy `--od` to dzień zakończenia tamtego retro). Wiadomości, pytania i błędy z sesji tamtego retro
sprzed commita nie zawyżają więc nowego okna (w R02 zawyżały `pytania` 52 zamiast 24). To samo okno obowiązuje
commity, PR-y, CI i tokeny. `--od RRRR-MM-DDTGG:MM` podaje godzinę wprost, `--od-poczatku-dnia` liczy od północy.
Retro niezacommitowane albo spoza gita: okno od północy (podsumowanie podaje, skąd wziął się początek).

## Klasy odpowiedzi na pytania (AskUserQuestion)

| klasa | znaczenie |
|---|---|
| `rekomendowana` | wybrano opcję oznaczoną jako rekomendowana („(rekomendowane)”, „Rekomendacja”, „zalecam”, „Recommended”) |
| `inna` | wybrano inną opcję z listy |
| `wlasna` | użytkownik wpisał własną odpowiedź spoza opcji: często korekta kierunku, czytaj w osi czasu |
| `odlozone` | pytanie zamknięte bez odpowiedzi („[User dismissed …]”) |
| `bez_wyboru` | odpowiedź „[No preference]” |
| `fakt` | pytanie z „[fakt]” w treści: o fakt znany tylko użytkownikowi (np. „w jakiej sieci jesteś?”); odpowiedź, także własnym tekstem, nie jest korektą |
| `bez_rekomendacji` | pytanie nie miało oznaczonej opcji rekomendowanej (od 0.1.3 bez pytań „[fakt]”) |

Odsetek `rekomendowana` mówi, jak dobrze Claude przewiduje decyzje użytkownika. `wlasna` i `odlozone` to
najciekawsze miejsca do przeczytania w osi czasu.

## Metryki (`metryki.json`, kolumny `metryki.csv`)

| metryka | skąd | uwaga |
|---|---|---|
| `wiad_wlasciciela` | wiadomości wpisane przez użytkownika | bez poleceń `/…`, powiadomień i wiadomości między sesjami; razem z wysłanymi w trakcie pracy Claude'a (rekordy `queued_command`, w osi czasu „w trakcie pracy Claude'a”) |
| `wiad_mozliwa_korekta` | słowa typu „nie”, „dlaczego”, „znowu” | heurystyka z dużym szumem; tylko trend |
| `wiad_po_20` | wiadomości poza godzinami pracy (`godziny_pracy`) | |
| `pytania`, `pyt_*` | odpowiedzi na AskUserQuestion | patrz klasy wyżej |
| `przerwania` | „Request interrupted by user” | liczone tylko, gdy transkrypcja zapisała ten znacznik |
| `blokady_klasyfikatora` | odmowy klasyfikatora trybu auto (sesje i podagenci) | |
| `odmowy_wlasciciela` | odrzucone prośby o zgodę na narzędzie | |
| `bledy_narzedzi` | wyniki narzędzi z błędem | najczęstsze w osi czasu projektu |
| `kompakty` | kompakty kontekstu | |
| `podagenci` | wywołania Agent/Task | osobno: model zadany i faktyczny (z transkrypcji podagenta) |
| `wiad_miedzy_sesjami` | SendMessage | |
| `commity`, `pr_*`, `ci_*` | git (wszystkie gałęzie) i `gh` | commity/PR liczone z 40 ostatnio scalonych PR (limit GraphQL) |
| `claude_md_linie` | suma linii plików reguł: `~/.claude/CLAUDE.md`, śledzone `CLAUDE.md` na dowolnej głębokości repo, `CLAUDE.local.md`, `pliki_regul_dodatkowe`; bez katalogów z `katalogi_regul_osobno` | rośnie = puchnięcie reguł; liczone z dysku, więc przy checkoucie w tyle za zdalną (kolumna „za zdalną”) nieaktualne |
| `pamiec_pliki` | pliki pamięci projektów | |

Kolumny od 0.1.3 (w `metryki.csv` na końcu, za `zobowiazania_aktywne`; starsze wiersze mają je puste):

| metryka | skąd | uwaga |
|---|---|---|
| `okno_od_godzina` | początek okna (patrz „Okno”) | `00:00` = od północy |
| `pyt_fakt`, `pyt_bez_wyboru` | klasy odpowiedzi | `pyt_bez_wyboru` była w `metryki.json` od 0.1.0, w CSV od 0.1.3 |
| `wywolania_api` | unikalne `message.id` w oknie, sesje i podagenci | patrz „Tokeny i koszt” |
| `koszt_api_usd` | tokeny × ceny API z `references/cennik.json` | miara względna, dolne oszacowanie |
| `koszt_na_wiadomosc_usd` | `koszt_api_usd` / `wiad_wlasciciela` | porównywalne między retro, gdy cennik ten sam |
| `kontekst_mediana` | mediana kontekstu (wejście + zapis + odczyt cache) wywołań sesji głównych | rozmiar kontekstu × liczba wywołań to główny koszt |
| `kontekst_ponad_200k_proc` | odsetek wywołań sesji głównych z kontekstem > 200k | |
| `kontekst_startowy_mediana` | mediana kontekstu pierwszego wywołania sesji zaczętych w oknie | stały narzut: prompt systemowy, narzędzia, skille, MCP, CLAUDE.md, pamięć; sesja z kopiami wywołań innej (rozwidlenie) nie wchodzi |
| `podagenci_koszt_proc` | udział podagentów w koszcie | |
| `podagenci_opus_koszt_proc` | udział Opusa w koszcie podagentów | liczenie podagentów po sztukach myli: w R02 Opus to 23% podagentów, ale 89% ich kosztu |
| `wybudzenia`, `wybudzenia_koszt_usd` | wywołania sesji głównej z zapisem cache > 50k po przerwie > 1 h od jej poprzedniego wywołania; koszt samego zapisu | zwykle pytanie zamykające („czy mogę archiwizować?”) do długiej sesji; lista w podsumowaniu |
| `commity_bez_sesji`, `pr_bez_sesji` | commity (czas commitera) i otwarte PR-y bez zapisu lokalnej transkrypcji sesji tego repo w odstępie ±30 min | praca w sandboksie, chmurze, na innej maszynie, scalenia na GitHubie; podsumowanie ostrzega, gdy to ≥ 20% (i ≥ 3 commity albo ≥ 2 PR) |
| `claude_md_linie_osobno` | linie plików reguł w `katalogi_regul_osobno` | np. kopie `CLAUDE.md` dla przyszłych repozytoriów (`repo-roots/` w childproxy) |

## Tokeny i koszt

- **Wywołanie API** = unikalny `message.id`. Claude Code zapisuje jedno wywołanie w kilku rekordach (po jednym na
  blok treści), w trakcie strumienia z częściowym `usage`: liczony jest rekord z największym `output_tokens`
  i najwcześniejszym czasem. Ten sam `message.id` w dwóch sesjach (kopia po rozwidleniu) liczy się raz, w sesji
  starszej. Transkrypcje podagentów (`<sesja>/subagents/agent-*.jsonl`) wchodzą do kosztu sesji, która je uruchomiła.
- **Koszt w cenach API** z `references/cennik.json` (wejście, wyjście, zapis cache 5 min i 1 h, odczyt cache;
  Haiku 5.5 drożej powyżej 100k kontekstu; tryb fast × 2; web search za zapytanie). Model dopasowany po najdłuższym
  przedrostku identyfikatora, `[1m]` pomijane. Nowy model albo zmiana cen: pole `cennik` w `konfiguracja.json`
  (ten sam kształt) albo aktualizacja pliku w repo pluginu. Modele bez ceny nie wchodzą do kosztu; podsumowanie je
  wymienia.
- **To miara względna, nie rachunek.** Na subskrypcji realnym ograniczeniem jest limit (5-godzinny i tygodniowy),
  a nie kwota. Kwoty porównuj między retro, nie z fakturą. Zmiana cennika (np. tańszy nowy model) zmienia koszt bez
  zmiany sposobu pracy: przy porównaniu z retro na innym modelu sprawdź „koszt wg modelu” w podsumowaniu.
- **Dolne oszacowanie.** Wywołania, których nie ma w transkrypcjach (klasyfikator trybu auto, tytuły sesji,
  podsumowania), nie są liczone; w R03 różnica wobec `cost-state` Claude Code wynosiła 0–15%.
- **Tylko lokalnie.** Sandbox, chmura i inne maszyny nie mają tu transkrypcji: koszt na commit albo PR w repo
  z dużym `commity_bez_sesji` nie ma sensu.
- **Wybudzenie** liczy przerwę między wywołaniami sesji głównej; długi podagent (> 1 h) też ją tworzy.

## Trend tygodniowy (`tokeny-tydzien.csv`)

Przy każdym przebiegu (bez `--projekt` i `--bez-trendu`) `sygnaly.py` czyta całą historię transkrypcji w zakresie
retro, dopisuje same liczby do archiwum `dane/tokeny-archiwum.json` (wywołania z `usage`, czasy wiadomości
właściciela i kompaktów, `cost-state`; bez treści rozmów) i z archiwum liczy wiersz na każdy tydzień (poniedziałek,
czas lokalny) do `tokeny-tydzien.csv` w katalogu roboczym. Archiwum chroni historię przed `cleanupPeriodDays`:
transkrypcja usunięta po 30 dniach zostaje w archiwum, jeśli skrypt zdążył ją przeczytać.

- **Klucz wiersza:** (`tydzien`, `zrodlo`). Skrypt pisze `zrodlo=lokalne` i wiersze źródeł zdalnych
  z konfiguracji (`zrodlo=<nazwa>`, niżej). Wiersze innych źródeł (np. pomiary ręczne, także po kilka na tydzień)
  zostają dosłownie, a nieznane kolumny i uwagi w `pokrycie` dopisane ręcznie zostają też w wierszach skryptu.
  Wiersz bez `zrodlo` jest traktowany jako lokalny.
- **Bez duplikatów:** tydzień jest nadpisywany przy każdym przebiegu (także niepełny, oznaczony „okres
  niezakończony”), chyba że wiersz w pliku widział więcej wywołań; wtedy zostaje stary z uwagą w `pokrycie`
  (dane sprzed archiwum usunięte przez retencję).
- **Źródła zdalne** (`zrodla_zdalne` w konfiguracji, domyślnie brak): druga maszyna, na której też działa Claude
  Code (sandbox, serwer). Dla każdego źródła skrypt robi **jedną** próbę odczytu, bez ponawiania:
  - `polecenie`: lista argumentów (albo napis), np. `["ssh", "-T", "host", "python3 -"]` albo z `docker exec -i
    <kontener> python3 -` w napisie dla ssh. Skrypt podaje na stdin `scripts/zbierz_liczby.py`, który na tamtej
    maszynie czyta `~/.claude/projects` i wypisuje same liczby (bez treści rozmów); niczego tam nie zapisuje.
  - `plik`: wynik `zbierz_liczby.py` zapisany wcześniej (ścieżka względna wobec katalogu roboczego albo
    bezwzględna), gdy połączenie robi właściciel sam:
    `ssh -T <host> python3 - < <skill>/scripts/zbierz_liczby.py > <katalog roboczy>/dane/<nazwa>-liczby.json`.
  - `wlaczone: false` wyłącza źródło, `limit_s` zmienia limit czasu (domyślnie 300 s); `--bez-zdalnych` pomija
    wszystkie przy jednym przebiegu.

  Odczyt trafia do osobnego archiwum `dane/tokeny-archiwum-<nazwa>.json` (ten sam format, plus lista `odczyty`
  z metadanymi każdego odczytu) i do wierszy `zrodlo=<nazwa>`. Gdy odczyt się nie uda, podsumowanie mówi dlaczego,
  a trend źródła liczy się z archiwum bez nowych danych. Czas zdalnych zdarzeń przychodzi w UTC i jest zamieniany
  na czas lokalny tej maszyny.
- **Kolumny** jak w metrykach okna, ale na tydzień: `koszt_api_usd`, `koszt_api_usd_ceny_55` (Opus/Sonnet/Haiku
  po cenach modeli z `rodziny_biezace` cennika, żeby zmiana cennika nie udawała zmiany sposobu pracy),
  `koszt_na_wiad`, `wywolania_na_wiad`, `kontekst_mediana`, `kontekst_p90`, `proc_wywolan_ponad_200k`, udziały
  odczytu i zapisu cache w koszcie, `wybudzenia` z kosztem, udział podagentów i Opusa, `kontekst_startowy_mediana`
  (bez sesji `claude -p`), `kompakty`, kontrola `koszt_cost_state_usd` wobec `koszt_policzony_tych_sesji` (sesje
  przypisane do tygodnia ostatniego wywołania). Kolumny `*_sygnaly` i `pokrycie_wiad_proc` są na porównanie
  z wcześniejszymi wyciągami; skrypt ich nie liczy i nie zmienia.
- **Trend w podsumowaniu:** ostatnie 4 zakończone tygodnie z aktywnością wobec mediany 8 wcześniejszych, osobno dla
  każdego źródła. Mediana ostatnich wyższa o ponad 20% = **↑ pogorszenie**, niższa = ↓ poprawa; przy mniej niż
  3 wcześniejszych tygodniach „za mało danych”. Tygodnie z 1–2 sesjami są głośne: strzałka to wskazówka, dowodem
  są sesje tego tygodnia.
- **Wiadomości właściciela** w trendzie liczone jak w osiach czasu (bez poleceń `/…`, powiadomień, wiadomości
  i briefów innych sesji, promptów `claude -p`; sam zrzut ekranu jest wiadomością).

## Ograniczenia

- **Tylko lokalne transkrypcje.** Sesje w chmurze (claude.ai/code) i na innych komputerach nie są widoczne.
- **Retencja.** Claude Code kasuje transkrypcje sesji z terminala i VS Code starsze niż `cleanupPeriodDays`
  (domyślnie 30 dni); sesje z aplikacji desktop nie podlegają temu czyszczeniu. Podsumowanie ostrzega, gdy okno
  sięga dalej. `dane/` w katalogu roboczym jest archiwum wyciągów: po miesiącu to jedyny ślad starszych sesji.
  Kto chce dłuższej historii, ustawia `cleanupPeriodDays` w `~/.claude/settings.json`.
- **Sesje w scratchpadzie** (katalog roboczy `…/claude/…/scratchpad`, zwykle testy `claude -p`) są pomijane;
  ich liczba jest w podsumowaniu.
- **Zamazywanie sekretów to heurystyka.** Przed zapisem raportów znikają: wartość po `gh secret set … --body`,
  wartość po nazwie zawierającej key/token/secret/pass/hasło/klucz (gdy ma litery i cyfry), `Bearer …`, klucze
  o znanych przedrostkach (`sk-`, `ghp_`, `AKIA`, `AIza`, `hf_`, JWT), bloki kluczy prywatnych oraz ciągi ≥ 32
  znaków z liter i cyfr. Zostają pełne hashe commitów (40 znaków szesnastkowych) i digesty `sha256:`. Hasło ze
  zwykłych słów albo krótki kod przejdzie niezamazany; transkrypcje źródłowe nie są zmieniane.
- **Projekty bez lokalnych sesji w oknie** (praca w chmurze albo na innej maszynie) nie mają osi czasu, a ich repo
  i reguły nie są liczone. Podsumowanie wymienia te, które mają pamięć; repo dodaj w `repozytoria_dodatkowe`.
  Gdy repo ma sesje, ale większość commitów powstała bez nich (`commity_bez_sesji`), podsumowanie ostrzega.
  Transkrypcje skopiowane z innej maszyny (katalog `projects`) dołącza `transkrypcje_dodatkowe`; ścieżki `cwd`
  z innej maszyny zwykle nie istnieją lokalnie, więc nazwy projektów popraw w `nazwy_projektow`.
- **Commity a czas.** Okno commitów liczy git po dacie commitera (`--since`), a git przestaje przeglądać gałąź na
  pierwszym commicie starszym niż początek okna: po rebase z datami nie po kolei część commitów może wypaść.
- **Format transkrypcji** nie jest publicznym API Claude Code i może się zmienić. Gdy liczby nagle spadają do
  zera, sprawdź skrypt na świeżej transkrypcji.
- **GitHub** tylko przez `gh` zalogowane na konto z dostępem do repo; repo bez zdalnego jest liczone tylko z gita.
