# Tapahtumaopas: esittelystä toimivaan kumppaniin

## Mitä voit näyttää nyt?

Katalogista voi esitellä 34 yrityskohtaista pakettia, niiden käyttötapoja, lähteitä, agenttiohjeita ja aloituskehotteita. QR on tässä vaiheessa **esikatselu**. Kokonaisuus on yksityinen ja julkaisematon, ja vastaanottajan koko Chibi-käyttöpolku on varmentamatta.

Esittely voi olla: ”Tämä on itsenäisesti luotu yrityksenne aihepiirin kumppani. Se on suunniteltu auttamaan näissä kolmessa tehtävässä. Käyttöönotto ja todellinen keskustelu varmennetaan Chibissä ennen jakelua.” Älä lupaa toimivaa keskustelua pelkän profiilin tai toimivan QR-koodin perusteella.

## Tavoiteltu vastaanottajan polku

| Vaihe | Vastaanottajan kokemus | Mitä on todennettava |
| --- | --- | --- |
| 1. QR | Vastaanottaja skannaa tämän yrityksen julkisen koodin. | Koodi avaa oikean kanonisen Chibi-tuotesivun. Se ei sisällä käyttövaltuutta, käyttäjätunnistetta tai kirjautumistokenia. |
| 2. Tuotesivu | Sivulla näkyvät yritys, käyttötarkoitus, lähteet ja itsenäisen tekijän ilmoitus. | Paketin tunniste, versio ja sisältö vastaavat hyväksyttyä tuontia. Julkaisematon sivu ei teeskentele saatavuutta. |
| 3. Olemassa oleva kirjautuminen | Vastaanottaja käyttää Chibin kirjautumista ja palaa oikeaan tuotteeseen. | Paluuosoite säilyy; toinen tili ei saa ensimmäisen tilin tietoja tai keskusteluja. |
| 4. Täsmällinen tarjous | Vastaanottaja näkee ja hyväksyy juuri kyseisen version ehdot ja käyttöoikeuden. | Tarjous on yksilöity ja muuttumaton hyväksymiseen nähden. Kesto, mahdollinen hinta ja rajat ovat näkyvissä. |
| 5. Tiliin sidottu adoptio | Kumppani liitetään vastaanottajan omaan Chibi-tiliin sovituin ehdoin. | Adoptiotietue syntyy oikealle tilille. Pelkkä QR tai selaimen paikallinen tila ei luo oikeutta. |
| 6. Aktivointi | Vastaanottaja aktivoi kumppanin sallittuun käyttöön. | Käyttöoikeus, voimassaolo ja suorittamisen edellytykset tarkistetaan palvelimella. |
| 7. Keskustelu | Käyttäjä lähettää aloituskehotteen ja saa hyödyllisen, lähteistetyn vastauksen. | Oikea pakettiversio ja yrityksen lähderajaus ovat käytössä. Vastaus, historia ja käyttöoikeuden päättyminen toimivat todellisesti. |

Chibin erillinen lähdekoodi omistaa tili-, tarjous-, adoptio- ja suoritusvastuut. Tämä repo valmistelee sisällön, linkit ja vientiaineiston. Katalogiin ei rakenneta tekaistua tiliä, palveluyhteyttä tai mallivastausta.

## Käyttöoikeus on vielä tuoteratkaisu

Nykyinen host-sopimus tukee nimenomaista trial-käytäntöä, jonka kesto on 1–90 päivää. Tapahtuman lopullista käyttöoikeus- ja hinnoitteluratkaisua ei ole päätetty. Esittelyssä ei luvata ikuista ilmaiskäyttöä tai pysyvää omistusta.

Ennen vastaanottajalle julkaisemista valitaan konkreettiset ehdot: mitä käyttäjä saa, kuinka pitkäksi ajaksi ja millä hinnalla tai kustannusrajalla. Chibi näyttää nämä samat ehdot täsmällisessä tarjouksessa ennen hyväksymistä. Yrityksen mainostamat omat API-krediitit eivät itsestään anna Chibi-käyttäjälle palveluyhteyttä tai todistettua kelpoisuutta.

## Aloita yhdestä pilotista

MariaDB on käytännöllinen ensimmäinen pilotti: hyödyllisen ohjausvastauksen voi arvioida pienellä synteettisellä SQL-esimerkillä ilman tuotantotietokantaa. Valitse yksi pakettiversio, yksi testitili ja yksi aloituskehote. Suorita koko vastaanottajan polku sekä tavallinen onnistuminen että olennaiset epäonnistumiset ennen muiden pakettien jakelua.

Pilotissa tarkistetaan vähintään:

- QR avaa oikean yrityksen sivun työpöytä- ja mobiiliselaimella; kirjautuminen säilyttää kohteen.
- Näppäimistökäyttö, fokus, tekstin luettavuus, dialogin sulkeminen ja takaisin-toiminto toimivat esittelylaitteilla.
- Hyväksytty tarjous vastaa näytettyä versiota ja ehtoja; peruminen ei tee adoptiota.
- Adoptio ja aktivointi kohdistuvat oikeaan tiliin. Kaksoisnapsautus tai sivun lataaminen uudelleen eivät luo ristiriitaista tilaa.
- Keskustelu käyttää oikean yrityksen ohjeita ja lähteitä, kertoo puuttuvasta yhteydestä eikä väitä ajaneensa työtä.
- Toinen tili, vanhentunut käyttöoikeus, puuttuva yhteys ja epäonnistunut palvelukutsu käsitellään totuudenmukaisesti.
- Todisteeseen kirjataan lähdeversio, paketin versio, ympäristö, tarkistukset, havaitut tulokset ja mahdollinen este.

Onnistuneen pilotin jälkeen hyväksy kaikki 34 pakettia samalla mallilla. Yhteinen infrastruktuuritesti voidaan hyödyntää, mutta jokaisen yrityksen sisältö, lähderajaus, esittely ja keskeinen hyöty tarkistetaan oman paketin perusteella.

## Nopea esittelyrunko

1. **Tarve:** ”Mikä dokumentaation tai työnkulun kysymys teillä toistuu?”
2. **Sopiva yritys:** avaa kumppani ja näytä sen kolme käyttötapaa.
3. **Yksi pieni tehtävä:** käytä synteettistä tai puhdistettua esimerkkiä. [MariaDB-, Aiven- ja Arduino-esimerkit](COMPANIONS.md#kolme-helposti-näytettävää-esimerkkiä) antavat lähtökohdan.
4. **Hyödyn arvio:** tarkista, tekeekö vastaus seuraavasta työvaiheesta selkeämmän ja osoittaako se oikeat lähteet.
5. **Palaute:** kirjaa käyttäjän puuttuva tarve ja epäselvyys. Älä lähetä henkilön tai yrityksen aineistoa palveluihin ilman tilanteeseen kuuluvaa lupaa.

Kun runtimea ei vielä ole varmennettu, näytä profiili ja tarkoitetun vastauksen hyväksymiskriteerit. Älä esitä ennalta kirjoitettua vastausta aitona live-keskusteluna.

## Mikä todistaa valmiuden?

Paikallinen validointi ja sopimustestit tarkistavat pakettien ja sovittimien rakennetta sekä rajattuja sääntöjä. Tarkka testimäärä ja tulos saadaan ajon tulosteesta. Build osoittaa kyseisen lähteen rakentuvan. Kumpikaan ei yksin todista kirjautumista, adoptioita, mallivastauksia tai mobiilikäytettävyyttä.

Paketeissa on **204 kirjoitettua käyttäytymistapausta**. Ne ovat arviointisuunnitelma, eivät ilmoitus suoritetuista malliajoista. Todellisen vastaanottajan polun ja mallikäyttäytymisen tulokset kirjataan erikseen täsmälliselle versiolle. Tässä oppaassa ei esitetä CI- tai julkaisuväitettä.

## Alkuperä ja yrityksen suhde

Kaikki kumppanit ovat itsenäisiä, eikä yrityksen hyväksyntää oleteta. Aikaisemman 34 petin alkuperäisiä profiileja ja kuvia ei saatu palautettua; nykyiset paketit ovat uutta sisältöä dokumentoidulle yritysrosterille. Täydelliset challenge-briefit tai henkilökohtaiset palveluedut eivät ole oletusarvoisesti tiedossa. Yksityiskohdat ovat [roster-evidenssissä](../evidence/company-roster.json) ja [kumppanipaketeissa](COMPANIONS.md).
