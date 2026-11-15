# Valio Aimo: agenttikäytön auditointi ja korjaukset

Päivä: 15.11.2026 (Europe/Helsinki). Sovellus:
`solutions/valio-trusted-trade/**`, SalesSquad/junction-pets.
Lähtöversio: `a566364dc5078e8d6e54e4858dbbffe34d2e037d`.
Toteutuksen tarkka commit, katselmointitulokset ja yhdistäminen kirjataan
toimitus-PR:ään. Tämä on päivätty prototyypin arvio, ei jatkuva tilaraportti
tai väite koko järjestelmän tuotantokelpoisuudesta.

## Auditoitu kokonaisuus

Tarve ja diagnoosi, tuotehaku, pakkauserät ja kulut, lähdeversioon sidottu
tarjous, rajattu hyväksyntä, kahden toimijan allekirjoitukset, tilaus ja
uusintayritykset, erillinen testimaksu ja palautus, toimitushavainnot, OCR,
selaimen palautuminen, HTTP-palvelun tallennus, MCP sekä toimittajan lukuliittymä.
PostgreSQL- ja WAL-laboratoriot säilyvät erillisinä kokeina; HTTP käyttää
nyt oikeasti paikallista SQLite-tallennusta.

## Löydökset ja toteutetut korjaukset

| Löydös | Korjaus / varmennus |
| --- | --- |
| Palvelimen sulkeminen hävitti tilan ja omistajuudet | Versioitu yksityinen SQLite-checkpoint; lähdenimiavaruus, laskurit, synteettiset avaimet, tokenien tiivisteet, omistajuudet, varasto, hyväksynnät, maksut ja uusintakirjanpito säilyvät |
| Tilausta voitiin kuitata ennen pysyvää tallennusta | Synkroninen BEGIN IMMEDIATE → tuore tila → tarkistukset → COMMIT → HTTP-vastaus; verkko-/kuvaluku ei pidä kirjoitustransaktiota auki |
| Aikakatkaisu tai kadonnut kuittaus saattoi aiheuttaa uuden ehdotuksen | Täsmällinen, sessioon sidottu komentotunnus ja sisältötiiviste; muuttunut sisältö aiheuttaa ristiriidan |
| Riippumaton ostaja tarkisti laskut mutta ei koko alkuperäistä tarvetta | Omassa asiakaskontekstissa säilytetyt määrät, perheet, ruokavalio, päivä, pakkaus- ja budjettirajat tarkistetaan ennen hyväksyntää/allekirjoitusta |
| Diagnostiikka-agentti jätti toimituskulut ja veron pois | Julkisen politiikan kulut ja vero välitetään laskentaan; väärä budjettivaje korjautuu |
| Varastohäiriö ja peruutus saattoivat ylittää varaston 1 000 000 rajan | Peruutettavien varausten palautusvara huomioidaan ennen lähdemuutosta; ei määrän leikkausta eikä rajan löysennystä |
| Jo hyväksytyn toimitushavainnon uusinta epäonnistui peruutuksen jälkeen | Sama avain palauttaa alkuperäisen havainnon; uudet havainnot peruutetulle tilaukselle estetään |
| JSON-lataus ja toimittajan vastaukset olivat riittämättömästi rajattuja | Tavu-/aikarajat, yhteys- ja sessiorajat, samasta alkuperästä tulevat pyynnöt, loopback-Host, turvalliset virheet ja hallittu toistettavuus |
| Katalogi ja auditointi palauttivat tarpeettoman laajoja vastauksia | Tyypitetyt suodattimet, rajat, lähdeversioon sidotut sivut ja auditoinnin vakaa yläraja; erillinen tiivis agenttivastaus |
| Rajapintakuvaus ja vastaukset eivät kaikilta osin vastanneet toisiaan | Walletin scope, sivutus, työvaiheet, virheiden palautumisohjeet ja yksilölliset operationId:t samassa OpenAPI-tuottajassa |
| Agentilla ei ollut varsinaista MCP-liittymää | Virallinen SDK v2, 8 tiukasti rajattua työkalua; erillinen isäntäohjelman hyväksyntä ja maksuvahvistus, ei mallin approve-argumenttia |
| Selaimen päivitys saattoi hukata aktiivisen tilauksen tai avaimen | IndexedDB ja ei-vietävä CryptoKey; palvelimen sessio, tarjouksen tuoreus, allekirjoitukset, kuitti ja maksutila tarkistetaan uudelleen |
| Puuttuva/vioittunut tallennus saattoi näyttää uudelta ympäristöltä | Yhteensopimaton, katkennut tai checkpointin menettänyt tietokanta hylätään; ei automaattista nollausta tai muistivarajärjestelmää |
| Valion portaalin komentorivipääsy ei toiminut | Virallinen dokumentaatio hankittiin normaalin Safari-kirjautumisen kautta; aidot rajatut lukukutsut varmennettiin |

## Agentille optimoitu käyttötapa

MCP:n 8 työkalua ovat oletuspinta. Mallille palautetaan vain tarvittava tila,
sallitut jatkotoimet ja lähteet; täydet tiedot haetaan allekirjoituksen
riippumatonta tarkistusta varten. Yhdessä saman ehdotuksen mittauksessa tiivis
vastaus oli 860 tavua ja täydellinen 8686 tavua: vähennys 90,1%.
Tämä on yhden vasteen mittaus, ei yleinen tokeni-, nopeus- tai rahasäästölupaus.

Ihmisen vahvistus sidotaan yhteen tarjoukseen, lähdeversioon ja summaan.
Budjettipoikkeus ei nosta seuraavien ostojen valtuutta. Maksu vaatii oman
vahvistuksensa. MCP-isännän vastaanottama vahvistus on tässä prototyypissä
synteettinen; oikeaa henkilöidentiteettiä tai käyttäjän fyysistä läsnäoloa
ei ole todistettu. Toimintojen vihjeet eivät yksin myönnä oikeuksia.

## Valion virallinen mock-API

Lähteet: [OpenAPI](https://junction26.valioaimo.fi/openapi.json),
[Docs](https://junction26.valioaimo.fi/docs),
[ReDoc](https://junction26.valioaimo.fi/redoc).
Havaittu OpenAPI 3.1.0 / palveluversio 0.1.0.
Normaali Safari-kirjautuminen sekä ping ja yksi tuote kummassakin
hinta-/saatavuushaussa palauttivat HTTP200. API-avainta, salasanaa, evästettä
tai valtuutusotsakkeen arvoa ei tallennettu lähdekoodiin tai tähän raporttiin.

API tarjoaa GET /api/ping sekä POST /api/availability ja POST /api/price.
Tilaus-, checkout- tai tilauksen kirjoitusoperaatiota ei ole dokumentaatiossa.
POST-haut ovat lukuja: customer, requestedDate ja rajatut tuotetunnukset.
Asiakasmoduuli sallii enintään 20 tuotetta, vaikka toimittajan dokumentoitu
yläraja on 1000. Automaattisia uudelleenyrityksiä ei tehdä; hintojen/saatavuuden
koko katalogihakua ei tehdä.

Staattisesta 87 Mt tuotetiedostosta luettiin vain 2 MiB alue ja 80 kokonaista
tietuetta. Hakusanoilla löydetylle tunnukselle 460032 tehtiin yksi saatavuus-
ja yksi hintahaku päivälle 16.11.2026, customer=junction-agent-audit.
Nimiosuma ei todista allergia- tai ruokavaliovaatimuksen täyttymistä.
OpenAPI-kuvauksen SHA256: d99239e689c24ff1d524dc16bd4c1ac081c2690dd952e7dcd72472f66fe7d3c6.

Havainnot eivät ole ostovaltuutta:

- Terminal-tuotteen 999999 on dokumentoitu tuntemattoman varaston sentinel,
  ei ostettava tai rajaton määrä.
- Esimerkin closingTime oli lähteen timeNow-arvoon nähden menneisyydessä
  vaikka salesBlock=false; katkaisuajan laajempaa merkitystä ei arvata.
- netPriceFound=false ja yksikköSK estävät tulkitsemasta lukua vahvistetuksi
  nettohinnaksi tai litroiksi. Havaittu catalogPrice.value 174.29 ja
  valueWithTax 197.82 EUR ovat lähdetietoja, eivät meidän tilausehtojamme.
- Avain pysyy palvelinpuolella. Operaattori syöttää sen hyväksytyn
  salaisuussäilön kautta; työkalun argumentteihin ei hyväksytä avainta,
  asiakasta tai mielivaltaista URL-osoitetta.
- Oletusostot käyttävät edelleen nimettyä keksittyä katalogia. Oikeita
  toimittajatilauksia, tuotantohintoja tai verotulkintoja ei väitetä.

## Varmennus ja rajat

146 eri sovellustarkistusta kattaa normaalipolut ja kielteiset tapaukset.
Laajan ajon ainoa viimeinen virhe oli uuden tallennuskokeen puuttuva
writeFile-tuonti; tuonti korjattiin ja sama koe läpäistiin erikseen.
Virhettä ei peitetty eikä väittämiä poistettu.

Oikea SQLite/HTTP-koe kattaa uudelleenkäynnistykset, kahden kirjoittajan
kilpailun, rollbackin ennen COMMITia ja todellisen SIGKILLin tilauksen sekä
maksun COMMITin jälkeen mutta ennen kuittausta. Sama avain palauttaa yhden
vaikutuksen. Varasto ja koko testisumma palautuvat täsmällisesti.
Tiedosto-/WAL-/SHM-oikeudet 0600 ja hakemisto 0700 tarkistettiin.

Virallisen MCP SDK:n asiakas teki oikeat stdio-kutsut, tiukan työkalulöydön,
isäntävahvistuksen hyväksynnän/kieltäytymisen, allekirjoituksen, maksun,
uusinnan, palautuksen ja palvelimen sekä ostaja-asiakkaan uudelleenkäynnistyksen.
Toimittajatyökalun kokeet käyttivät injektoitua vastaajaa; ne eivät tehneet
uusia toimittajakutsuja. SDK-paketit 2.4.0 ja Zod 4.6.7 ovat lukittuja;
tuotantoriippuvuuksien npm audit raportoi 0 tunnettua haavoittuvuutta
tarkistushetkellä.

Chromium 1440×1050/390×844 tarkisti olemassa olevat ostopolut, palautumisen,
stale-lähteen torjunnan, palvelinvirheen säilyttävän session, estetyn
IndexedDB:n ja oikean paikallisen OCR:n. Taloudellisia vaikutuksia ei tehdä
tilan palauttamisen yhteydessä. Safari-sovelluspolkua, fyysistä kameraa,
oikeaa ostaja-/hyväksyjäidentiteettiä, tuotantomaksua, monipalvelinympäristöä
tai reaaliaikaista pgvector/embedding-palvelua ei ole tällä näytöllä
varmennettu. Paikallinen checkpoint on rajattu 16 MiB:iin; se ei ole
varastokaupan mittakaavan tietokantaratkaisu.

Lähdekoodin riippumaton riskikatselmointi ja täsmällinen toimitusversio
löytyvät tämän työn PR:stä. Vanhat receiptit ja muut tuotteet jätettiin ennalleen.

Riskikatselmuksessa rajattiin ulos vapaatekstin tallentaminen selaimeen sekä muu kuin 1–12 numeron katalogitunnus toimittajahauissa. Hylätyn maksukomennon uusi päätös tarvitsee uuden komentotunnuksen. Tarkat löydöskohtaiset ratkaisut ja jälkitarkistukset ovat toimitus-PR:ssä #298.
