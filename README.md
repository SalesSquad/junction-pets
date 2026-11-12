# Junction Pets

34 versionoitua, yrityskohtaista Chibi-kumppanipakettia Junctionia varten. Lähderepo on yksityinen [SalesSquad/junction-pets](https://github.com/SalesSquad/junction-pets).

Tavoite on antaa yrityksen edustajalle nopeasti ymmärrettävä, hyödyllinen kumppani: tutustu siihen katalogissa, kokeile rajattua esimerkkitehtävää ja siirry julkaisemisen jälkeen olemassa olevan Chibin tilille sekä keskusteluun. Kumppanit auttavat dokumentaation ymmärtämisessä, käyttäjän toimittaman aineiston arvioinnissa ja seuraavan tarkistuksen suunnittelussa. [Kumppaniluettelossa](docs/COMPANIONS.md) ovat kaikki 34 yritystä käyttötapoineen.

## Nykyinen tila

Tämän version lähtötila on **yksityinen, julkaisematon kokonaisuus; vastaanottajan koko Chibi-käyttöpolkua ei ole todennettu**. [Host-asetuksissa](config/host-config.json) runtime on `unverified` ja julkaistujen pakettien lista on tyhjä.

| Osa | Nykyinen sisältö | Mitä siitä voi päätellä |
| --- | --- | --- |
| Yrityspaketit | 34 pakettia, jokaisella kolme käyttötapaa ja aloituskehotetta | Sisältöä voi tarkastella, versioida ja valmistella Chibiin vietäväksi. |
| Agenttiohjeet | Yrityskohtainen `AGENTS.md`, lähteet ja toiminnan rajat | Ohjeet määrittävät tarkoitetun käyttäytymisen. Ne eivät muodosta valmista palveluyhteyttä. |
| Katalogi | Yritysten selaus, pakettilataukset ja QR-esikatselu | Julkaisemattoman kumppanin käyttöönottotoiminto on estetty. QR ei todista vastaanottajan käyttöpolun toimivuutta. |
| Käyttäytymisen arviointi | 204 kirjoitettua arviointitapausta | Tapaukset ovat arviointisuunnitelma; niitä ei ole tässä työssä ajettu mallia vasten. |
| Paikallinen tarkistus | Validointi-, sopimustesti- ja build-komennot | Tulos koskee ajettua lähdeversiota ja tarkistuksen rajattua kattavuutta. |
| Chibi-integraatio | Linkki- ja vientisovittimet sekä erillinen host-raja | Tilit, ehdot, adoptio, aktivointi ja keskustelu tarvitsevat Chibin toteutuksen ja oman varmennuksensa. |

Jokainen kumppani on itsenäisesti luotu. Yrityksen hyväksyntää tai virallisen edustajan asemaa ei oleteta. `content: ready` tarkoittaa valmisteltua sisältöä; `runtime: chibi-host-required` säilyttää suorittavan sovelluksen rajan.

## Käynnistä paikallisesti

Tarvitset Node.js-version 22 tai uudemman, npm:n ja pääsyn yksityiseen repoon. Aja repon juuressa:

```sh
npm ci
npm run validate
npm test
npm run build
```

`npm ci` asentaa lukitustiedoston mukaiset riippuvuudet. Validointi tarkistaa pakettisopimuksen. `npm test` ajaa paikalliset sopimustestit; testimäärä ja tulos näkyvät komennon tulosteessa. `npm run build` muodostaa katalogidatan ja rakentaa käyttöliittymän hakemistoon `dist/site`. Build ei julkaise paketteja eikä kytke yritysten palveluja.

Kehitysnäkymä käynnistyy komennolla `npm run dev`. Käyttöliittymän tekniset ohjeet ovat [katalogin README-tiedostossa](apps/catalog/README.md).

## Jokaisella yrityksellä on oma kehityslinja

**Kehitysorkestrointi:** jokaiselle 34 petille on oma kehittäjäagentin määrittely ja tavoiteltu Codex Cloud -ympäristö `ops/environments/`-rekisterissä. Yksityinen [Mission Control](docs/DEVELOPMENT_SYSTEM.md) näyttää pet-kohtaisen lähde-/testinäytön, työtilan, estäjän ja seuraavan toimen. Ympäristömäärittely ei ole sama asia kuin todistetusti julkaistu ympäristö; vahvistamattomat Cloud-ID:t ja malliajot näkyvät puuttuvina.

Jokaisella petillä on myös oma lähteeseen sidottu, **skills-only** [plugin-paketti](docs/PET_PLUGINS.md). Kaikki 34 kanonista pluginia on nyt rekisteröity yksityisesti ChatGPT Plugin Creatorissa ja niiden tunnisteet on tarkistettu sekä sidottu lähdetiedostoihin. Rekisteröinti **ei tarkoita** Chibi-asennusta, suoritettuja malliajoja tai sallittuja Chibi-työkaluja. Kehitysnäkymän sekä jäljitettävän, synteettisen petiltä petille -[yhteistyödemon](docs/INTER_PET_COLLABORATION.md) saa omassa Node-ympäristössä komennolla `npm run ops:preview`. Yksityiset näkymät valmistuvat hakemistoihin `dist/mission-control` ja `dist/collaboration-demo`; niitä ei lisätä julkiseen katalogiin. Omistajan [yksityinen kehityskeskus](https://chatgpt.com/space/page_72f945dcf8a48191a72178904f8ab22d) saa erillisen tilannekuvan komennolla `npm run ops:page:build`.

Junctionin palautettava agenttikoodi pysyy erillään yksityisestä Chibi.pet-tekniikasta. Katso [kehitysjärjestelmä](docs/DEVELOPMENT_SYSTEM.md) ja [palautusraja](docs/JUNCTION_SUBMISSION.md).

Yrityksen oma linja tarkoittaa omaa `pets/<company-slug>/`-hakemistoa, paketin versionumeroa, lähteitä ja arviointitapauksia. Kokonaisuutta ylläpidetään yhtenä monorepona; 34 pysyvää Git-haaraa eivät ole pakettimalli. Muutokset tehdään rajatuilla tehtävähaaroilla ja katselmoidaan yhteisten sopimusten kautta.

| Tiedosto tai hakemisto | Tarkoitus |
| --- | --- |
| `pets/<company>/pet.json` | Tunniste, versio, esittely, kolme käyttötapaa, kehotteet ja lähteet. |
| `pets/<company>/AGENTS.md` | Yrityskohtainen agenttikäyttäytyminen, tiedon rajaus ja yhteyksien ehdot. |
| `pets/<company>/STORY.md` | Käyttäjän esittely ja suomenkielinen yhteenveto. |
| `pets/<company>/evals.json` | Kuusi arviointitapausta yritystä kohden. |
| `evidence/company-roster.json` | Yritysjoukon alkuperä ja epävarmuudet. |
| `apps/catalog/` | Katalogin käyttöliittymä. |
| `config/host-config.json` | Kanoninen Chibi-osoite ja julkaisemisen varmennustila. |
| `lib/`, `scripts/`, `schemas/` | Yhteiset sopimukset, vienti ja tarkistukset. |

Säilytä paketin `id`, `slug` ja `artIndex` vakaina. Muuta yrityksen omia tiedostoja ja nosta versionumeroa sisällön muuttuessa. Generoidut tiedostot muodostetaan yhteisillä skripteillä. Kenttäsopimus on [catalog-contract.md](catalog-contract.md).

## Chibi on varsinainen tuote

Tämä repo omistaa yrityssisällön, katalogin ja Chibiin valmisteltavat vientipaketit. **Varsinainen Chibi-lähdekoodi on erillisessä repossa.** Se omistaa tilit, käyttäjien eristämisen, hyväksytyn tarjouksen, tilille sidotun adoption, käyttöoikeudet, aktivoinnin, keskusteluhistorian sekä mallien ja palvelujen suorittamisen.

Katalogi ei luo rinnakkaista kirjautumista tai tekaistua keskustelua. Julkinen QR sisältää vain kanonisen tuotesivun osoitteen. Skannaaminen ei anna tilioikeutta tai palvelun käyttövaltuutta.

Tavoiteltu tapahtumapolku on [tapahtumaoppaassa](docs/EVENT_GUIDE.md). Nykyinen host-sopimus tukee nimenomaista trial-käytäntöä, jonka kesto on 1–90 päivää. Lopullista tapahtuman käyttöoikeus- tai hinnoittelupäätöstä ei ole tehty. Tämän sisällön perusteella ei luvata ikuista ilmaiskäyttöä tai pysyvää omistusta.

Tarkka pakkaaminen, Maker-vienti, API-rajat ja julkaisun edellytykset: [CHIBI_INTEGRATION.md](docs/CHIBI_INTEGRATION.md). Toteutuksen kuvat ja visuaalinen tarkistus: [fidelity-ledger.md](design/fidelity-ledger.md).

## Mistä 34 yritystä tulevat?

Kokonaisuus on koottu Junction Spaceen tallennetusta yritysinventaariosta: 18 challenge-kumppania, 13 technology-kumppania, Arduino, Verda ja Google DeepMind. Lähteet, havaintopäivät ja roolien epävarmuudet ovat [roster-evidenssissä](evidence/company-roster.json).

Aiemman 34 petin alkuperäisiä profiileja, nimiä ja kuvatiedostoja ei saatu palautettua. Tämän repon profiilit ovat uusia, itsenäisesti kirjoitettuja kumppaneita dokumentoidulle yritysjoukolle. Yrityskohtaiset faktat perustuvat pakettien omiin ensisijaisiin lähteisiin. Puuttuvaa challenge-briefiä ei ole korvattu keksityillä vaatimuksilla.

## Seuraava käytännön askel

Aloita yhdestä pilotista, esimerkiksi MariaDB:stä. Vie yksi täsmällinen pakettiversio Chibin yksityiseen testipolkuun, varmista tarjouksen ehdot ja todenna vastaanottajan koko polku sekä lähteisiin sidottu vastaus. Säilytä lähdeversio, testitulos ja mahdollinen este. Laajenna samoilla hyväksymiskriteereillä kaikkiin 34 kumppaniin onnistuneen pilotin jälkeen.

Aloituskehotteet: [COMPANIONS.md](docs/COMPANIONS.md). Tapahtuman esittely ja hyväksymiskriteerit: [EVENT_GUIDE.md](docs/EVENT_GUIDE.md).
