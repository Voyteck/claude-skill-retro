# Sygnały i metryki: co znaczą i czego nie mówią

`scripts/sygnaly.py` czyta transkrypcje Claude Code z okna retro, gita i (gdy jest `gh`) GitHuba.

## Klasy odpowiedzi na pytania (AskUserQuestion)

| klasa | znaczenie |
|---|---|
| `rekomendowana` | wybrano opcję oznaczoną jako rekomendowana („(rekomendowane)”, „Rekomendacja”, „zalecam”, „Recommended”) |
| `inna` | wybrano inną opcję z listy |
| `wlasna` | użytkownik wpisał własną odpowiedź spoza opcji: często korekta kierunku, czytaj w osi czasu |
| `odlozone` | pytanie zamknięte bez odpowiedzi („[User dismissed …]”) |
| `bez_wyboru` | odpowiedź „[No preference]” |
| `bez_rekomendacji` | pytanie nie miało oznaczonej opcji rekomendowanej |

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
| `claude_md_linie` | suma linii plików reguł: `~/.claude/CLAUDE.md`, śledzone `CLAUDE.md` na dowolnej głębokości repo, `CLAUDE.local.md`, `pliki_regul_dodatkowe` | rośnie = puchnięcie reguł; liczone z dysku, więc przy checkoucie w tyle za zdalną (kolumna „za zdalną”) nieaktualne |
| `pamiec_pliki` | pliki pamięci projektów | |

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
- **Format transkrypcji** nie jest publicznym API Claude Code i może się zmienić. Gdy liczby nagle spadają do
  zera, sprawdź skrypt na świeżej transkrypcji.
- **GitHub** tylko przez `gh` zalogowane na konto z dostępem do repo; repo bez zdalnego jest liczone tylko z gita.
