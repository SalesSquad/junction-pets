# Aiven-petti — ensimmäinen iso parannuskierros: toteutussuunnitelma

Päiväys 14.11.2026. Lähtötaso mitattu haarassa `agent/junction-aiven-stack-capabilities-20261114`
(viimeisin `38a87ae`). Kaikki mittaukset ovat kehittäjämittauksia Claude CLI:llä, eivät Chibi-isännän
tai Aiven AI gatewayn ajoja.

## Tila 16.11.2026 (WS2)

Injektiosarja laajennettiin 64 tapaukseen, joista 19 puhdasta, ja tyypitetty `content_requests` lisättiin
([`RESULTS-20261116-injection-typed.md`](../../solutions/aiven-model-tournament/RESULTS-20261116-injection-typed.md)).
Väärät hälytykset ovat 0–3 %, joten ≤ 5 %:n tavoite täyttyy. Injektio havaitaan 100 %:ssa vastauksista, ja sitä
noudatetaan 0–1 %:ssa. Läpäisy on Haikulla 81–84 % ja Sonnetilla 92 %, joten 95 %:n porttia ei vielä saavuteta.
Jäljelle jäävät hylkäykset ovat tapauskohtaisia puutteita vastauksen kattavuudessa, eivät turvallisuusvirheitä.

## Tila 15.11.2026

Vaihe 1 ajettu, tulokset: [`RESULTS-20261115-phase1.md`](../../solutions/aiven-model-tournament/RESULTS-20261115-phase1.md).
Turvallisuusportti täyttyy. Haiku + korjaus täyttää WS3:n kustannustavoitteen. WS2 (84–90 %) ja WS4 (Haiku 0,91)
ovat lähellä mutta eivät vielä täytä porttia. Kolmas arvioija odottaa AI gatewayn pääsyä. Pilotit (WS6) aloitettu
etuajassa: Valio 62,5 % → 93,8 %, S-Pankki 75 % → 75 %, AstraZeneca 68,8 % → 75 %.

## 1. Lähtötaso ja tavoite

| Mittari | Nyt (uusi lukematon 5 haastajan sarja) | Kierroksen tavoite |
|---|---|---|
| Konsensus-läpäisy (opus + sonnet), Haiku | 77 % [65–86] | **≥ 90 %, alaraja ≥ 80 %** |
| Konsensus-läpäisy, Sonnet | 80 % [68–88] | ≥ 90 % |
| Injektiotapaukset (työkalutuloste, data) | yleisin virhe | **≥ 95 %** |
| Live-työkalutehtävät (koodipisteytys), Haiku / Sonnet | 0,80 / 1,00 | ≥ 0,95 / 1,00 (20 tehtävää) |
| Turvallisuus (skeema, ei toteutusta, ei salaisuuksia) | 100 % | 100 % (portti) |
| Ehdotuskuri | 58/58 korjaussilmukalla | 100 % (portti) |
| Arvioijien yksimielisyys | 84–90 % | ≥ 90 % |
| Hinta / vastaus (ilman arviointia) | Haiku ~0,03 $, Sonnet ~0,05 $ | ≤ 0,03 $ Sonnet-tason laadulla |
| Oikeat käyttäjät | 0 | **1 todellinen polku Chibissä**: ehdotus → ihmisen päätös |

Kierros on valmis, kun kaikki portit täyttyvät **uudella, lukemattomalla** haastajasarjalla, joka on
kalibroitu ennen ajoa, ja Chibi-polku on demonstroitu.

## 2. Työvirrat

### WS1 — Tuotantopolku Chibiin (vaihtoehto A + decision-silta)
**Omistaja:** Chibi-isännän omistaja + Junction-integraattori. Aiven-linja toimittaa referenssit.
1. Vienti: kaikki moduulit (`pets/aiven/modules`, 11,7k merkkiä) `persona.system_prompt`-kenttään,
   `response.v2` providerin strukturoiduksi tulosteeksi. Ei manifestimuutosta.
2. Rust-portti: `bridge.mjs` (validointi, kanoninen JSON, proposal/payload-hashit, PendingAction)
   ja `lint.mjs` `chibi-api`:iin. Pariteetti: yhteiset testivektorit (JS ja Rust tuottavat saman hashin).
3. Ehdotukset `chibi-store` `action_decisions` -tauluun; olemassa oleva ihmisen hyväksyntä
   (`ActionDecisionBinding`). Gateway toteuttaa vain hyväksytyn, oman politiikkansa alla.
4. Passport näyttää moduulien ja skeeman hashit.

**Hyväksyntä:** yksi todellinen adoptio tuottaa ehdotuksen, ihminen hyväksyy tai hylkää, ja kuitti on tallessa.
JS–Rust-hashit ovat identtiset 100 vektorilla, eikä mikään polku suorita ilman päätöstä.

### WS2 — Injektion torjunta isännän tasolla
**Omistaja:** Aiven-linja (referenssi) → Chibi-isäntä (tuotanto).
1. Isäntä merkitsee työkalutulosteen ja liitetyn datan rajatuksi, epäluotetuksi sisällöksi (tunnisteellinen kehys).
2. Skeemaan v2.1 kenttä `untrusted_instructions_detected[]`: lähde ja toimenpide "ignored, flagged".
3. Lint: vastaus ei saa sisältää ehdotusta tai toimenpidettä, joka toistaa upotetun ohjeen. Lisäksi jokaisesta
   havaitusta upotuksesta tehdään tietoturvaliputus.
4. Injektiosarja: 40 tapausta haastajien tavoin (lokit, CSV, luettelorivit, MCP-tuloste, monikieliset).

**Hyväksyntä:** injektiosarja ≥ 95 % konsensus, ja vääriä hälytyksiä on ≤ 5 % puhtaissa tapauksissa.

### WS3 — Kustannusoptimoitu kaskadi
**Omistaja:** Aiven-linja.
- Oletusmallina toimii Haiku ja kaikki moduulit. Jos lint löytää korjauksen jälkeen yhä puutteita tai pyyntö
  luokitellaan erityiseksi (terveys- tai henkilödata, tuotannon poisto), vastauksen tuottaa Sonnet ja reititetyt moduulit.
- Kaskadin päätössääntö on deterministinen, ja se kirjataan vastauksen metatietoon.

**Hyväksyntä:** laatu on vähintään Sonnetin tasolla (luottamusvälit päällekkäin tai parempi), ja kustannus on ≤ 60 % Sonnetista.

### WS4 — Oikeat työkalut laajemmin
**Omistaja:** Aiven-linja.
1. Live-tehtävät 5 → 20: metriikat, lokit, integraatiot, kuluttajaviive, tapahtumaloki, VPC ja IP-suodatin
   sekä ansat (jo tehty, ei olemassa, väärä projekti). Jokainen tehtävä pisteytetään Aivenin API:a vasten.
2. Tyypitetyt tunnisteet kaikkiin työkaluvastauksiin (pattern/enum + `notes`).
3. Core-moduuliin sääntö: "hae jokainen listattu kohde yksitellen, älä jätä `unknown`".

**Hyväksyntä:** Haiku ≥ 0,95 ja Sonnet 1,00 kahdella toistolla. Yhtään kirjoitustyökalua ei kutsuta (read-only-palvelin).

### WS5 — Jatkuva evaluointi Aivenin päällä (oma "Best Use of Aiven")
**Omistaja:** Aiven-linja. Kulut vaativat omistajan hyväksynnän.
1. Ajastettu yöajo: uusi haastajasarja → kalibrointi → ajo (Haiku-kaskadi) → raportti.
2. Tulokset kulkevat Kafka-topicin `eval-results` kautta ClickHouseen (hallinnoitu `clickhouse_kafka`)
   ja sieltä Grafana-näkymään: läpäisy, luottamusvälit, haastajittain, hinta ja regressiot.
3. Regressioportti PR:ään: muutos hylätään, jos konsensus-läpäisy putoaa tai yksikin turvallisuusportti rikkoutuu.
4. Kustannuskatto ajoa kohden.

**Hyväksyntä:** 7 peräkkäistä yöajoa ja näkymä toimivat. Portti hylkää tarkoituksella istutetun regression.

### WS6 — Menetelmä muille peteille (pilotti 3)
**Omistaja:** kunkin petin linjan kirjoittaja. Aiven-linja tekee pohjan.
1. Pettiriippumaton pohja: moduulirunko, `response`-skeemapohja, decision-silta, lint, haastaja-ajuri
   ja kalibrointi.
2. Pilottipetit: Valio Aimo, S-Pankki ja AstraZeneca (jo valmiita haastajia). Ristiinarviointi siten, että
   jokainen petti haastaa muita.

**Hyväksyntä:** kolmella pilotilla on mitattu lähtötaso ja yksi parannuskierros raportoituna.

### WS7 — Toimitus ja Junction
**Omistaja:** Mikael (päätökset), Aiven-linja (toteutus).
1. Haara jaetaan kolmeen PR:ään: (a) petti ja moduulit, (b) evaluointityökalut, (c) silta ja vientiehdotus.
2. Lennonkirjurin live-ajo (tunnukset `creds`-kansioon), ja tulos kirjataan `RESULTS.md`-tiedostoon.
3. Tuomarisivu: mitattu hyöty ennen ja jälkeen, luottamusvälit ja turvallisuusportit.

## 3. Aikataulu

| Vaihe | Kesto | Sisältö | Rinnakkain |
|---|---|---|---|
| 0 Päätökset | 0,5 pv | Vaihtoehto A, kulut WS5:lle, PR-jako, AI gatewayn pääsypyyntö | — |
| 1 Laatu | 3–4 pv | WS2, WS3, WS4 Aiven-linjassa; WS1 Rust-portin suunnittelu ja testivektorit | WS7.1, WS7.2 |
| 2 Tuotanto | 4–6 pv | WS1 integraatio Chibiin; WS5 yöajo ja näkymä | WS6 pohja |
| 3 Skaalaus | 4–5 pv | WS6 pilotit; lopullinen validointi uudella sarjalla | WS7.3 |

Validointi tehdään jokaisen vaiheen lopussa uudella, lukemattomalla ja etukäteen kalibroidulla sarjalla.

## 4. Budjetti (arvio)

- **Evaluointikutsut:** noin 150–250 $ koko kierrokselle. Kerran 30 tapausta kolmella mallilla
  maksaa noin 20 $, ja yöajo noin 5 $/yö kaskadilla.
- **Aiven (WS5):** Kafka free-0, kun riittää. ClickHouse ja Grafana pienimmillä plaaneilla vaativat
  omistajan hyväksynnän ja hinnan tarkistuksen ennen luontia. Krediittiä on jäljellä noin 221 $
  (LEEVI250, voimassa 31.12.2026).

## 5. Riskit ja hallinta

| Riski | Hallinta |
|---|---|
| Ylisovitus omiin testeihin | Joka mittaus tehdään uudella, lukemattomalla sarjalla, eikä kalibroija näe vastauksia |
| Arvioijan oman mallin suosiminen | Opus ja Sonnet konsensuksella. Kolmas, ei-Claude-arvioija, kun AI gateway on käytössä |
| Isäntämuutosten kitka | Vaihtoehto A ei vaadi manifestimuutosta; Rust-portti tehdään pariteettivektorein |
| Jaettu Aiven-projekti (muut agentit luovat palveluja) | Read-only-evaluointi; omat demopalvelut tagataan; ei poistoja ilman omistajaa |
| Kustannusten kasvu | Kutsukohtainen budjettikatto, Haiku-kaskadi ja yöajon katto |

## 6. Päätökset Mikaelilta ennen vaihetta 1

1. Hyväksytäänkö vaihtoehto A Chibin vientiin (integraattori ja isännän omistaja)?
2. Saako WS5:lle luoda ClickHousen ja Grafanan (pienet plaanit, hinta tarkistetaan ensin)?
3. Pyydetäänkö Aiven AI gatewayn pääsy organisaatiolle?
4. PR-jako kolmeen osaan: avaatko vai saanko luoda ne?
5. Tunnukset lennonkirjurin live-demoon.
