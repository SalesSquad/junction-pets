# TimeLaw: is this clause the law on this date? (2026-11-14)

620 claims from 10 official provisions (eCFR versioner, legislation.gov.uk point-in-time); 234 true, 191 stale (an earlier amount), 195 premature (a later amount). Gold = the official text on that date.

| method | balanced accuracy | accuracy | historical dates | latest date | true accepted | stale rejected | premature rejected |
|---|---|---|---|---|---|---|---|
| current text, code | 51 % | 378/620 (61 %, 95 % CI 57–65) | 59 % | 100 % | 9 % | 100 % | 85 % |
| point-in-time, code | 100 % | 619/620 (100 %, 95 % CI 99–100) | 100 % | 100 % | 100 % | 100 % | 99 % |
| current text, Jev | 51 % | 378/620 (61 %, 95 % CI 57–65) | 59 % | 100 % | 9 % | 100 % | 85 % |
| current text, Jev + code | 51 % | 378/620 (61 %, 95 % CI 57–65) | 59 % | 100 % | 9 % | 100 % | 85 % |
| point-in-time, Jev | 100 % | 620/620 (100 %, 95 % CI 99–100) | 100 % | 100 % | 100 % | 100 % | 100 % |
| point-in-time, Jev + code | 100 % | 620/620 (100 %, 95 % CI 99–100) | 100 % | 100 % | 100 % | 100 % | 100 % |
| no document, Jev prior | 50 % | 310/620 (50 %, 95 % CI 46–54) | 50 % | 46 % | 48 % | 49 % | 53 % |
| no document, Haiku from memory | 92 % | 575/620 (93 %, 95 % CI 90–95) | 93 % | 89 % | 91 % | 94 % | 94 % |

Haiku from memory, accuracy by year: 2015 75 %, 2016 91 %, 2017 100 %, 2018 100 %, 2019 95 %, 2020 96 %, 2021 91 %, 2022 87 %, 2023 100 %, 2024 94 %, 2025 89 %, 2026 89 %
