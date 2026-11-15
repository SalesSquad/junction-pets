# Paikallinen simulaatiolaboratorio

Laboratorio ajaa seitsemän skenaariota oikean localhost-HTTP-palvelimen,
yksityisen SQLite-tilan, JOSE-allekirjoitusten, ostajan itsenäisen ehtotarkistuksen
ja tarjous-/maksukohtaisen hyväksynnän läpi. Jokainen tulos syntyy suorituksesta
ja väittämien tarkistamisesta; havaittu odotettu torjunta näkyy omana askeleenaan.
Virhe tai sulkemisen epäonnistuminen tuottaa `FAIL`-tuloksen.

Kaikki tuotteet, varastot, hinnat, testihenkilöt, oikeudet, tilaukset ja maksut
ovat **keksittyä paikallista simulaatiota**. `HUMAN` on tässä vain skriptatun
testitoimijan rooli, ei oikea ihminen, henkilöllisyyden todistus tai väite aidosta
suostumuksesta. Laboratorio ei luo tilejä, yhdistä oikeaan identiteettipalveluun,
käytä toimittajatunnuksia tai tee Valio-kutsuja. Ulkoiset hintojen/saatavuuden
adapterit jätetään kokonaan asettamatta.

## Käyttö

Sovelluskansion juuressa:

```sh
npm --prefix identity ci --ignore-scripts
npm --prefix mcp ci --ignore-scripts
node simulation/lab.mjs
```

CLI ajaa kaikki seitsemän tapausta ja tulostaa puhdistetun JSON-raportin;
exit-koodi on 1, jos yksikin tapaus epäonnistuu. Tunnisteita, JWT:itä,
yksityisiä avaimia, JWKS-sisältöä tai kokonaisia audit-tietoja ei tulosteta.

Ohjelmallinen käyttö:

```js
import { createSimulationLab, scenarios } from './simulation/lab.mjs';
const lab = await createSimulationLab();
try {
  const result = await lab.runScenario('purchase');
  // result.steps contains actual checked observations, never canned green status.
} finally {
  await lab.close();
}
```

Valinnainen `stateDirectory` on **luotetun paikallisen suorittajan** määritys,
ei mallin tai selaimen argumentti. Sen on oltava omistajan yksityinen hakemisto.
Jokainen ajo tekee oman uuden kanonisen 0700-alihakemistonsa ja generoi uudet
Ed25519-testiavaimet. SQLite-tiedostot ovat 0600 ja sisältävät vain yksityistä
synteettistä testitilaa sekä testiavaimia; niitä ei viedä iCloudiin tai raporttiin.
Oletuskansiot ovat käyttöjärjestelmän väliaikaisessa hakemistossa. Testitila
säilyy hakemistossa paikallista vianetsintää varten, vaikka kaikki palvelimet ja
ostaja-asiakkaat suljetaan `finally`-haarassa. `close()` odottaa keskeneräiset ajot
ja estää uudet.

## Skenaariot

| Tunnus | Toteutunut tarkistus |
| --- | --- |
| `purchase` | 1 000 L laktoositonta maitoa, alkuperäinen 1 400 EUR budjetti, lähdekohtainen poikkeus, erillinen ostaja-avain, yksi tilaus, erillinen testimaksu sekä täysi peruutus/palautus |
| `reject` | Testi-ihmisen allekirjoitettu hylkäys estää sitoutumisen; tilausten ja maksujen määrä pysyy nollassa |
| `stale` | Erikseen myönnetty testivaraston muutos tekee vanhasta tarjouksesta `QUOTE_STALE`-kelvottoman; uusi lähdeversio vaatii uuden hyväksynnän, minkä jälkeen syntynyt testitilaus perutaan |
| `revoked` | Hyväksyjän oikeuden peruminen hyväksynnän jälkeen estää tilauksen `IDENTITY_REVOKED`-virheellä |
| `retry` | Socket suljetaan kerran tilauksen COMMITin ja kerran maksun COMMITin jälkeen ennen HTTP-kuittausta; palvelin ja ostaja käynnistetään molemmissa kohdissa samoista tilatiedostoista samalla portilla; edelleen vain yksi tilaus ja maksu, lopuksi täysi palautus |
| `shortage` | Kaksi toimituskelpoista maidon testierää asetetaan nollaan; puuttuvaa 1 000 litraa ei korvata kaurajuomalla eikä tilausta synny |
| `expired` | Yhteistä hallittua kelloa siirretään vähintään 121 sekuntia ja aina tarjouksen voimassaolon yli ilman nukkumista; vanhentunut allekirjoitus torjutaan ja uusi allekirjoitus ei elvytä vanhentunutta tarjousta |

`retry` osoittaa todellisen socket-kuittauksen menetyksen ja tilan uudelleen
avaamisen saman Node-prosessin sisällä. Se ei esitä tämän ajon olevan fyysinen
konevika, SIGKILL-, verkkokatko- tai monipalvelinkoe. Varsinainen HTTP-yhteys,
SQLite-COMMIT, uudelleenkäynnistetyt palvelinoliot, allekirjoitukset, varaston
muutokset ja testikirjanpito ovat oikeasti käytössä. Aiemmat erilliset
SIGKILL-kokeet ovat oma näyttönsä, eivät tämän laboratorion tulos.

Raportin turvallinen yhteenveto sisältää vain synteettiset kuitti-/tarjoustunnukset,
summat, vaikutusten lukumäärät, torjuntakoodit ja mittausajat. Käynnissä olevan
palvelimen identiteettirajapinta on testin sisällä `HOST_AUTHENTICATED`, mutta
laboratorion ulkoinen tila on aina `LOCAL_SIMULATION` ja kaupankäynti synteettistä.
Todellinen identiteettipalvelu, hostin aito käyttäjäpäätös sekä Valion tilaus-
rajapinnan hyväksytty sopimus ja sandbox ovat edelleen erilliset integraatiorajat.

## Interactive local laboratory

Install the existing optional verifier dependency with `npm --prefix identity ci --ignore-scripts`, then run `npm run demo:simulation` from the solution directory. The explicit simulator opens at http://127.0.0.1:4188 (override VALIO_SIMULATION_PORT only for a chosen local port). It is separate from normal `npm start`; no production identity configuration or provider key is read. Stop with Ctrl-C.

The page runs all seven scenarios, shows the actual asserted event chain and exports sanitized JSON. `npm run simulation:check` drives the real HTTP boundary and checks input/origin/concurrency limits. `npm run simulation:browser` additionally drives the page with an installed Playwright module (PLAYWRIGHT_MODULE) and optional local Chromium executable (PLAYWRIGHT_CHROMIUM_PATH); artifacts default to the ignored .runtime/simulation-receipts/browser directory. VALIO_SIMULATION_ARTIFACT_DIR selects an operator-owned evidence destination.

Local UI routes: GET /, /app.js, /style.css; GET /api/simulation/status and /api/simulation/report; POST /api/simulation/run with the sole JSON field scenario = all or one documented scenario ID. POST requires the same Origin as its loopback Host, JSON at most 1024 bytes in 3 seconds, and one active run. Arbitrary URLs, credentials, grants and actor input are rejected. The source receipt includes checkout commit, dirty state and hashes of the five executable/UI source files. PASS is derived from executed assertions; an assertion or cleanup error yields FAIL.

The browser actors are scripted fixtures, not authenticated real people. The receipt is a synthetic domain receipt, not Valio acceptance. Backend traffic goes only to its own ephemeral loopback server; no mock-provider API, actual supplier, payment service or identity provider is called. Private synthetic SQLite fixtures remain local; export contains no raw keys/tokens/subjects.

The UI reconciles a lost run reply with single-flight status reads, including transient 503, and never submits another run automatically. Reconciliation is bounded to two minutes; an unresolved state offers a read-only status retry, keeping new runs disabled until verified. Simulation error codes are safe structured diagnostics; raw transport/error messages are not rendered. Controlled expiry derives from the actual quote expiry. Backend close waits are bounded to three seconds and the UI HTTP socket to two minutes.
