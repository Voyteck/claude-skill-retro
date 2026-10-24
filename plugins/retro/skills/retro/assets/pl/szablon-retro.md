# Retro RNN · RRRR-MM-DD

**Status:** szkic
**Okno:** RRRR-MM-DD … RRRR-MM-DD (N dni roboczych) · **Sesje:** N · **Projekty:** …
**Dane:** `dane/sygnaly-…/` (lokalnie, poza gitem)

## 1. W skrócie

3–5 zdań: najważniejszy wniosek i najważniejsza zmiana.

## 2. Metryki trendu

| metryka | R(N-2) | R(N-1) | RN | kierunek |
|---|---|---|---|---|

## 2a. Tokeny i efektywność pisania

Źródło: sekcja „Tokeny i efektywność pisania” podsumowania sygnałów (obowiązkowa w każdym retro).

| wskaźnik | R(N-3) | R(N-2) | R(N-1) | RN | lepiej / gorzej |
|---|---|---|---|---|---|

- **Lepiej:** … (liczby, przyczyna, dowód)
- **Gorzej:** … (liczby, przyczyna, dowód)
- **Efektywność wg konfiguracji implementatora** (model · poziom rozumowania, w tym samym rozmiarze PR): odsetek PR
  z poprawką, rundy, powroty od przeglądu i CI, **koszt na PR** (oczekiwany koszt zaakceptowanego PR); przy < 5 PR
  w komórce tylko wskazówka.

**Reguły doboru agenta** (kto robi jakie zadanie, na jakim modelu i poziomie):

| zadanie (rola · rozmiar) | teraz (agent · model · poziom) | proponowane | dane (PR, % z poprawką, koszt na PR) | miara w następnych retro |
|---|---|---|---|---|

- Zmiana na tańszą konfigurację ma sens, gdy koszt na PR spada, a odsetek PR z poprawką nie rośnie o więcej niż
  10 pkt proc.; na droższą, gdy spadek poprawek obniża koszt na PR albo czas do scalenia.
- Przy zbyt małej liczbie PR zaproponuj eksperyment zamiast reguły (np. „co drugi PR rozmiaru S do
  `programista-prosty`”, przez dwa retro).
- **Sugestie (2–3):** zmiana · oczekiwany efekt · miara (np. „implementacja PR rozmiaru S na Sonnecie · medium,
  dopóki odsetek PR z poprawką nie wzrośnie o więcej niż 10 pkt proc., a koszt na PR jest niższy niż na Opusie”).

## 3. Rozliczenie zobowiązań

| ID | zobowiązanie | przestrzegane | sens | dowody | proponowany werdykt |
|---|---|---|---|---|---|

## 4. Co działało: kontynuujemy

- **…** · dowód: `MM-DD HH:MM` `sesja` …

## 5. Co nie działało: zmieniamy

- **…** · przyczyna: … · dowód: …

## 6. Strona użytkownika

Koszt i efekt, z dowodami. (Pomiń sekcję, gdy `ocena_wlasciciela` jest wyłączona.)

## 7. Sprzeczności i martwe reguły

## 8. Rekomendacje

Najwyżej 5 nowych zobowiązań; każda mówi, co zastępuje lub skraca.

### P1 · …

- **Treść:** …
- **Kogo dotyczy:** …
- **Mechanizm:** … (albo „brak: reguła w tekście”, z powodem)
- **Sygnał przestrzegania:** …
- **Miara sensu:** …
- **Gdzie zapisać:** …
- **Zastępuje / skraca:** …

## 8a. Czeka na użytkownika

| pozycja | od | dowód | decyzja |
|---|---|---|---|

## 9. Decyzje użytkownika

| propozycja | decyzja | uwagi użytkownika |
|---|---|---|

## 10. Wdrożenie

- `zobowiazania.md`: …
- reguły: … (plik, commit / PR)
- propozycje zmian skillu retro: …
