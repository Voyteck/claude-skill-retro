# retro: retrospektywa pracy z Claude Code

Plugin Claude Code, który wprowadza do pracy z Claude'em proces ciągłego doskonalenia w stylu Agile.
Co kilka dni roboczych (zalecane: co 2) retro:

1. **rozlicza zobowiązania** z poprzednich retro: czy były przestrzegane i czy dały efekt;
2. zbiera **dowody** z transkrypcji Claude Code, gita i GitHuba (wiadomości użytkownika, odpowiedzi na pytania,
   blokady, błędy narzędzi, podagenci, PR-y, CI, rozmiar plików reguł, tokeny i koszt w cenach API: kontekst,
   udział podagentów i Opusa, wybudzenia długich sesji);
3. ocenia, **co działało, a co nie**, także po stronie użytkownika (opcjonalnie);
4. proponuje **najwyżej 5 zmian**, preferując mechanizmy (testy, hooki, szablony) nad regułami w tekście;
5. przyjęte zmiany **wdraża** do plików reguł (`CLAUDE.md`, pamięć, `nauki.md`) i rejestru zobowiązań.

Jeśli przez 5 dni roboczych nie było retro, nowa sesja Claude Code przypomina (hook `SessionStart`).
Wszystko po polsku.

## Wymagania

- Claude Code (CLI albo zakładka Code w aplikacji desktop), sesje lokalne;
- Python ≥ 3.8 w `PATH` (`python3`, `python` albo `py`), tylko biblioteka standardowa;
- git; opcjonalnie `gh` zalogowane na konto z dostępem do repozytoriów (metryki PR i CI);
- bash dla hooka przypomnienia (na Windows: Git Bash, którego Claude Code i tak wymaga).

## Instalacja z repo GitHub (zalecana)

1. W Claude Code na każdym koncie i komputerze, gdzie ma działać:

   ```
   /plugin marketplace add Voyteck/claude-skill-retro
   /plugin install retro@retro
   ```

   W terminalu to samo: `claude plugin marketplace add Voyteck/claude-skill-retro` i `claude plugin install retro@retro`.

2. Nowa sesja (albo `/reload-plugins`).

Własna kopia (fork albo nowe repo z tej paczki) instaluje się tak samo, z `<konto>/<repo>` zamiast
`Voyteck/claude-skill-retro`. Prywatne repo wymaga poświadczeń gita na tym komputerze (klucz SSH albo
`gh auth login` i `gh auth setup-git`), a automatyczne aktualizacje w tle dodatkowo `GITHUB_TOKEN`.

## Instalacja bez GitHuba

Folder z rozpakowaną paczką może być marketplace'em sam w sobie:

```
/plugin marketplace add C:\ścieżka\do\retro-plugin
/plugin install retro@retro
```

Zmiany w folderze działają po `/reload-plugins` albo w nowej sesji.

## Pierwsze uruchomienie

W sesji Claude Code napisz „zróbmy retro” albo `/retro` (pełna nazwa: `/retro:retro`). Retro zapyta o:

- **tryb**: *całe konto* (wszystkie projekty z transkrypcji na tym komputerze; katalog roboczy np. `~/retro`,
  osobne repo git) albo *ten projekt* (tylko jedno repo; katalog `.retro/` w repo, wspólny dla zespołu);
- ocenę strony użytkownika (tak/nie) i kalendarz dni roboczych (polski / sam weekend).

Potem założy katalog roboczy i przeprowadzi **retro zero**: bilans dotychczasowych nauk (pamięć projektów,
`CLAUDE.md`) i pierwszy rejestr zobowiązań do Twojej akceptacji. Kolejne retro rozliczają ten rejestr.

## Co jest w środku

```
.claude-plugin/marketplace.json          to repo jest marketplace'em z jednym pluginem
plugins/retro/.claude-plugin/plugin.json manifest pluginu (wersja)
plugins/retro/hooks/hooks.json           przypomnienie przy starcie sesji
plugins/retro/skills/retro/SKILL.md      procedura retro (instrukcje dla Claude'a)
plugins/retro/skills/retro/scripts/      sygnaly.py, tokeny.py, zbierz_liczby.py, dopisz_metryki.py, zaloz.py, przypomnienie.py,
                                         wspolne.py
plugins/retro/skills/retro/assets/       szablony: retro, rejestr, metryki, nauki, README katalogu
plugins/retro/skills/retro/references/   konfiguracja.md, sygnaly.md (znaczenie metryk), cennik.json
testy/test_retro.py                      testy na sztucznych transkrypcjach
```

## Prywatność

Skrypty czytają tylko lokalne pliki (`~/.claude/projects/*.jsonl`, repozytoria) i `gh`; niczego nie wysyłają.
Wyciągi z transkrypcji trafiają do `dane/` w katalogu roboczym, który jest poza gitem. Dokumenty retro zawierają
krótkie cytaty z sesji jako dowody: w trybie projektu `.retro/` jest commitowane z repo, więc widzą je wszyscy
z dostępem do repo.

## Aktualizacje

Zmień pliki, podnieś `version` w `plugins/retro/.claude-plugin/plugin.json`, wypchnij. Użytkownicy:
`/plugin marketplace update retro` (automatyczne aktualizacje są domyślnie wyłączone). Przed wypchnięciem:

```
python -m unittest discover -s testy -v
claude plugin validate . --strict
claude plugin validate plugins/retro --strict
```

## Ograniczenia

- Widzi tylko sesje lokalne; sesje w chmurze (claude.ai/code) i na innych komputerach nie trafiają do retro, chyba że
  ich transkrypcje skopiujesz i wskażesz w `transkrypcje_dodatkowe`. Koszt to ceny API jako miara względna
  (na subskrypcji ogranicza limit, nie kwota), liczony tylko z lokalnych transkrypcji.
- Claude Code usuwa transkrypcje z terminala i VS Code po `cleanupPeriodDays` (domyślnie 30 dni). Wyciągi
  w `dane/` zostają; kto chce dłuższej historii, podnosi tę wartość w `~/.claude/settings.json`.
- Wyciągi z transkrypcji (`dane/`) są poza gitem, a ciągi wyglądające na sekrety są w nich zamazywane. To
  heurystyka, nie gwarancja: klucz wklejony do rozmowy trzeba i tak zrotować.
- Format transkrypcji nie jest publicznym API Claude Code; gdy liczby nagle spadną do zera, sprawdź skrypt na
  świeżej transkrypcji.
- Polecenie to `/retro`, pełna nazwa `/retro:retro` (nazwa pluginu i skilla). Samo `/retro` działa tylko wtedy,
  gdy żadne inne polecenie nie używa tej nazwy: jeśli na koncie jest też własny skill `retro`, `/retro` uruchomi
  jego, a plugin zostanie pod `/retro:retro`; usuń stary skill.
- Hook przypomnienia sprawdzony w CLI i ręcznie; w aplikacji desktop sprawdź, czy przypomnienie się pojawia.
