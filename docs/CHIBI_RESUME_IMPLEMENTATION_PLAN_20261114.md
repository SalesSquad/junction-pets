# Chibi Resume — toteutussuunnitelma ja pitkän aikavälin tuotesuunta

**Päiväys:** 14.11.2026  
**Työ:** junction.meta.resume-plan.20261114  
**Tila:** arkkitehtuuri- ja toteutusehdotus; dokumentaatiotoimitus. Työpaketit eivät ole käynnistettyjä töitä.  
**Tarkistettu main:** 98d5a524d61e431ca36acd62b268ede343fc7fe2. Aiemman koodiauditoinnin a33f525171b6424d39dfc4c889b63e0fc5cb459e jälkeen Meta-ydin ei ole muuttunut; välissä ovat dokumentaatio ja CRACI-kampanjan integrointi.  
**Omistettu muutos:** tämä uusi dokumentti. Nykyiset arkkitehtuurirajat ja julkaisuvaltuudet säilyvät päätöksenteon lähtökohtina.

## 1. Päätös, jota ehdotan

**Rakennetaan Chibi Resume: avustaja, joka palauttaa käyttäjän keskeytyneeseen fyysiseen tehtävään ja auttaa tekemään seuraavan oikean asian.**

Tuotelupaus: *“Jatka siitä, minkä todella sait tehtyä.”*

Nykyinen Lens hoitaa havaintoja ja niiden näyttöä. Resume tuo tavoitteet, etenemisen, keskeytykset ja korjaukset. Myöhemmin Relay siirtää rajatun tehtävän toiselle ihmiselle ja Familiar tunnistaa tehtävän kannalta merkityksellisiä muutoksia tutussa ympäristössä. Nämä ovat yhden tuotteen kyvykkyyksiä.

Pitkän aikavälin omaisuus on **laitteesta riippumaton tehtävämuisti: tavoitteet, vahvistettu eteneminen, havaintojen lähteet, riippuvuudet ja toimiviksi osoitetut menettelyt**. Lasit ovat sille erityisen kiinnostava käyttöliittymä, koska kädet ja katse ovat jo työn äärellä. Puhelin ja Mac mahdollistavat kehityksen ja käytön myös silloin, kun laseja ei ole saatavilla.

Ensimmäinen kohderyhmäehdotus on kuvauskalustoa tai harrastusvälineitä valmisteleva ihminen, jonka työ katkeaa. Aloitus on kolmen esineen kameralaukku yhdessä rajatussa tilassa. Tämä on testattava tuotehypoteesi, ei havaittu asiakaskysyntä.

### Viisi päätöstä heti

1. Yksi käyttäjä, yksi tehtävä, kolme esinettä, yksi keskeytys ja yksi epäselvä havainto.
2. Käyttäjän vahvistama vaihe on kelvollinen eteneminen; sitä ei esitetä koneen todentamana fyysisenä identiteettinä.
3. Pysyvä yksityinen tila ja oikeudet kuuluvat nykyisen arkkitehtuurin mukaisesti Chibille.
4. Ensimmäinen oppiminen tulee oikeista käyttöepisodeista sekä puhelin- ja tarkistuslistavertailusta.
5. AR, VR, oma malli ja lisäagentit tulevat mukaan ratkaisemaan mitattua ongelmaa. Jokaiselle määritetään erillinen jatkamisehto.

## 2. Todellinen lähtötilanne

| Osa | Todennettu lähteistä tai aiemmasta ajosta | Seuraava puuttuva näyttö |
| --- | --- | --- |
| Mainin Lens-ydin | services/meta-spatial sisältää inspect/find/verify-polut, rajatut haut, lähteet, peruutuksen ja host-portit. Täsmällisestä a33f525-lähteestä suoritettiin synteettinen demo: last-observed, guidance-proposed, identity-verified ja not-observed; yksi fixture-mallikutsu. [S1] | Todellinen kamera, yksityinen muisti, valtuutettu host ja oikea mallipalvelu yhdessä työnkulussa. |
| Apple-pohja, PR #73 | Swift/SwiftUI-lähde sekä Resume-tuotevisio. Myöhempi kommentti raportoi 10 Swift-testin ja käännetyn Swift→JS-pariteetin onnistumisen; se täsmentää vanhaa PR-kuvausta. [S2][S3] | Varsinainen käyttöliittymäkokemus, iPhone-ajo ja laitepolku. |
| Virallinen DAT, PR #75 | #73:n päälle pinottu DAT 1.0.1 / MockDeviceKit / Vision OCR. iOS build-for-testing onnistui; CaptureEpochin kaksi kohdennettua testiä onnistuivat. [S4] | SDK-kehyksen, OCR:n, revoken ja disconnectin integraatiotestistä ei saatu testitapauskohtaista tulosta simulaattorin käynnistys-/levytilarajan vuoksi. Fyysisiä laseja ei ole tällä näytöllä kelpuutettu. |
| Mallikokeilu, PR #70 | Viiden numeerisen piirteen logistinen ehdokaspisteyttäjä ja synteettiset aineistot. Tämä ei ole kuvantunnistin. [S5] | Oikea aineisto ja osoitettu hyöty havainto- tai tehtäväputkessa. |
| CRACI-mallikampanja, PR #92 | Nyt mainissa: 12 siementä ja 120 000 lisäesimerkkiä muuttuneesta synteettisestä jakaumasta. False-candidate-osuus 12,4702–15,2428 %. Mittaus onnistui, mallia ei hyväksytty tuotantoon. [S6] | Visuaalinen laatu, oikea kamera, käyttäjähyöty ja toimintapisteen valinta. |
| Chibi | Repon arkkitehtuuri sijoittaa identiteetin, Cedar-politiikan, oikeudet, yksityisen muistin ja todellisen suorituksen Chibiin. Historiallinen integraatiosauma on dokumentoitu pois käytöstä. [S7] | Nykyisen lähteen ja aidosti käytettävän host-reitin paikantaminen ennen integraatiota. Aikaisempi merge ei osoita aktiivista palvelua. |

PR #73:n tarkistettu HEAD on 82f17099ae1d52efde6661e69f7ea5e38fdcd407; PR #75:n 4eaac725b2032253c9e2414a6997ff4bb064e442. Molemmat olivat tarkistuksessa avoimia luonnoksia. #75:n suoritettava toteutus on a1fefd76a100a23ec4051beec487a61d676e08a9; myöhempi HEAD sisältää jatkamistiedon. #73:n Swift-näyttö sitoutuu kommentissa mainittuun df5cf2b90d0d2d264e9aae2e8f039d8e14d6fc72-lähteeseen, ei kaikkiin tuleviin muutoksiin.

**Ensimmäinen integraatiojärjestys on #73 → #75 → Resume-yhdistäminen.** Nykyinen Portfolio PR Recovery säilyy Junctionin integraattorina. Koodin hyväksyminen lähdepuuhun ja laitteen tai tuotteen hyväksyminen käyttöön ovat eri päätöksiä. #70 ei ole tämän ketjun riippuvuus.

## 3. Miksi tästä voisi syntyä oma tuote

Meta kuvaa jo lasien pitkäaikaista muistia, kontekstihakua ja yksityistä pilvikäsittelyä. Google esittää Astrassa multimodaalista muistia ja puhelimen sekä prototyyppilasien välillä jatkuvaa avustajaa. Astra on tutkimusprototyyppi. [S8][S9]

**Strateginen päätelmä:** yleinen lupaus “tekoäly näkee ja muistaa” on heikko erottautumiskohta. Alustatoimijat rakentavat sitä suoraan laitteisiin. Myös yksityisyys pitää toteuttaa uskottavasti; pelkkä yksityisyysväite ei riitä kilpailueduksi.

Resumelle testattava etu on tarkempi:

- Se tietää, minkä työn käyttäjä yritti saada valmiiksi.
- Se erottaa nähdyn, päätellyn ja vahvistetun.
- Se havaitsee, milloin muuttunut olosuhde tekee aiemmasta suunnitelmasta epävarman.
- Se siirtää vain tarvittavan etenemistiedon seuraavalle ihmiselle tai laitteelle.
- Se oppii korjatuista, oikeuksiltaan sallituista työepisodeista toistettavia menettelyjä.
- Sen hyöty näkyy säästyneessä ajassa, vähemmissä unohduksissa ja pienemmässä selitystyössä.

Tämäkään ei muodosta automaattista kilpailuetua. Meta tai Google voi toteuttaa vastaavan ominaisuuden. Kestävämpi asema edellyttää toimivaa kapeaa työnkulkua, käyttäjien toistuvaa käyttöä, laadukkaita alakohtaisia ohjeita, integraatioita ja jakelua siellä, missä työ alkaa.

## 4. Ensimmäinen kokemus ja Junction-demo

Käyttäjä sanoo tai valitsee: **“Pakkaan kameran, mikrofonin ja laturin.”**

Kamera ja mikrofoni vahvistetaan pakatuiksi. Laturi on havaittu pöydällä, mutta sen pakkaamista ei ole vahvistettu. Käyttäjä keskeyttää työn. Keskeytyksen aikana laturia siirretään ja näkyville tuodaan samannäköinen esine.

Kun käyttäjä kysyy “mihin jäin?”, hyvä vastaus on:

> Kamera ja mikrofoni on vahvistettu pakatuiksi. Laturi jäi kesken. Viimeinen havainto oli pöydältä ennen keskeytystä. Näytä laturin merkintä tai vahvista itse, että tämä on oikea.

Tämän jälkeen tarjotaan yksi seuraava askel. Käyttäjä voi vahvistaa, korjata, pyytää tarkennuksen tai jatkaa käsin. Vastaus ei julista laukkua valmiiksi pelkän kuvassa näkyvän esineen perusteella.

### 60 sekunnin esitysrakenne

| Aika | Näytettävä asia | Todistettava hyöty |
| --- | --- | --- |
| 0–8 s | Tehtävä ja kolme esinettä | Kohderyhmä ja tavoite ymmärretään heti. |
| 8–18 s | Kaksi vahvistettua vaihetta | Eteneminen kertyy ilman pitkää keskustelua. |
| 18–28 s | Keskeytys ja esineen muutos | Todellinen tarve tehtävämuistille. |
| 28–40 s | “Mihin jäin?” | Vahvistettu eteneminen erotetaan vanhasta havainnosta. |
| 40–51 s | Samannäköinen laturi, yksi tarkennus | Epävarmuudesta päästään eteenpäin. |
| 51–57 s | Vahvistus ja valmistuminen | Käyttäjä säilyttää päätösvallan. |
| 57–60 s | Tiivis aikajana | Tulos voidaan ymmärtää ja korjata. |

Aikataulu on esityssuunnitelma. Sitä ei merkitä kuvatuksi tai onnistuneeksi ennen todellista ajoa. Puhelin-, MockDeviceKit- ja fyysisen lasin lähteet merkitään oikein. Käyttäjähyötyprosentti näytetään vain, jos se on oikeasti mitattu.

Metan tallennetun challenge-briefin mukaan audio-first ja display sekä web- ja DAT-toteutukset ovat hyväksyttäviä. Oleellisia ovat arjen ongelma, first-person-näkökulman hyöty, toimiva prototyyppi, deck ja käytännön laitetilojen käsittely. Tästä syystä Display-näkymä ei ole ensimmäisen toimituksen edellytys. [S10]

## 5. Tehtävämuistin rakenne

### Kolme erillistä tietoa

| Tieto | Esimerkki | Kuka voi tuottaa sen? |
| --- | --- | --- |
| Havainto | “Laturiehdokas näkyi kehyksessä kello 14.03.” | Kameraketju ja rajattu havaintomenetelmä. |
| Tulkinta tai ehdotus | “Tämä voisi olla tehtävän puuttuva laturi.” | OCR, vertailu tai malli. |
| Vahvistettu tehtävätapahtuma | “Käyttäjä vahvisti laturin pakatuksi.” | Valtuutettu käyttäjä tai erikseen määritetty, kelpuutettu todistuspolku. |

Lisäksi tallennetaan korjaukset, toimet ja niiden tulokset. “Näkyi”, “on sama”, “pakattiin” ja “toimenpide suoritettiin” pysyvät eri väitteinä. Yhden luvun confidence-kenttä ei saa peittää näitä eroja.

### Pienin ehdotettu tietomalli

| Olio | Tarvittava sisältö |
| --- | --- |
| Task | Tavoite, tila, versio, omistajuus hostissa, ohjeversion viite, tehtävän rajaus. |
| Step | Järjestys tai riippuvuudet, seuraava toiminta, valmistumiskriteeri, vaadittu näyttö. |
| Observation | Lähde, hostin vastaanottoaika, laitteen aika erikseen, kuvausistunto ja generation, kuvatunniste, menetelmä, rajattu esine/alue. |
| Assertion | Väite, sen alkuperä, todisteviitteet, tuoreuden ehdot, ristiriita tai korvaava korjaus. |
| Confirmation | Kuka vahvisti, mitä, minkä tehtäväversion yhteydessä ja millä perusteella. |
| Event | Komennon tunniste, odotettu versio, hyväksytty uusi versio, muutoksen laji ja rajatut viitteet. |
| Procedure | Tavoite, edellytykset, vaiheet, vaihtoehdot, näyttövaatimukset, lähde ja julkaisijan hyväksymä versio. |

Tämä on luonnos yhteiseksi sopimukseksi. Nykyisen tietovaraston päälle lasketaan tehtävänäkymä ja tarvittavat suhteet. Erillistä graafitietokantaa ei oteta oletukseksi.

### Pitkälle kantava valinta: riippuvuudet

Vaiheen onnistuminen voi riippua esineestä tai aiemmasta vaiheesta. Jos riippuvuuden tila muuttuu, järjestelmä merkitsee kyseisen oletuksen tarkistettavaksi. Se ei pyyhi historiaa eikä tarkista koko tehtävää alusta.

Esimerkki: käyttäjä on vahvistanut kameran pakatuksi, mutta poistaa sen myöhemmin laukusta. “Pakattu kello 14.02” pysyy historiallisena tapahtumana. Nykyinen “valmiina lähtöön” -päätelmä tarvitsee uuden vahvistuksen.

Tätä kautta pieni pakkausdemo kasvaa myöhemmin usean työn koordinointiin: akun lataus voi estää yhden tehtävän, mutta järjestelmä voi ehdottaa toista riippumatonta valmisteluvaihetta.

## 6. Arkkitehtuuri ja omistajuus

**Ehdotettu kulku:** laitteen rajattu havainto → nykyisen Lensin havaintosopimus → Chibin hyväksymä tehtävätapahtuma → laskettu tehtävänäkymä → yksi ehdotus tai tarkennus → käyttäjän vahvistus.

- **Junction:** julkiseen jakeluun soveltuvat sopimukset, adapterit, rajattu ehdotuslogiikka, synteettiset esimerkit ja kehitysnäyttö.
- **Yksityinen Chibi:** autentikointi, tenant, oikeudet, pysyvät käyttäjätiedot, tehtävän authoritative-versio, todelliset malli-/työkalukutsut ja suorituskuittaukset.
- **Apple-sovellus:** kuvaus, paikallinen esikäsittely, käyttöliittymä, sallittu paikallinen näkymä ja käyttäjän keskeneräisten komentojen jono.
- **Malli:** tuottaa ehdotuksia ja kysymyksiä. Mallin vastaus ei itsessään valtuuta toimintaa tai todista valmistumista.

Nykyiset Lens-portit authorize, runJob, resolveObservation, validateCapture, validateRegistration, searchSightings, searchProcedures, propose ja verifyIdentity säilyvät lähtökohtana. Hostin nykyinen kyvykkyys tarkistetaan lähteestä; pelkkä portin nimi ei tarkoita toteutettua yhteyttä. [S1][S7]

### Tehtäväkomentojen luonnos

Visiossa esiintyvät lens.task.start, checkpoint, resume, correct, handoff ja revoke ovat ehdotettuja nimiä, eivät nykyisiä rekisteröityjä työkaluja. Ensimmäisessä toteutuksessa tarvitaan myös selkeä käyttäjän vahvistusoperaatio, joko oma confirm tai yksiselitteinen checkpoint-tapahtumalaji. Integraattori päättää yhden versionoidun sopimuksen. [S2]

Komento kantaa vähintään komennon tunnisteen, tehtävän tunnisteen, odotetun version, operaation ja rajatut todisteviitteet. Tenant ja toimivalta sidotaan hostissa. Toistettu komento ei saa luoda toista valmistumista. Vanha versio palauttaa konfliktin ja ajantasaisen näkymän; sitä ei ratkaista sokealla viimeisen kirjoittajan voitolla.

Yhteiset virheluokat ensimmäiseen fixture-sopimukseen: luvan puute, peruttu istunto, vanha tehtäväversio, riittämätön näyttö ja tavoittamaton lähde. Toteutus määrittää tarkat koodit ennen rinnakkaisia kirjoittajia.

### Offline ja muistin poistaminen

Verkkokatkossa aiemmin sallittu tarkistuslista ja käsin eteneminen säilyvät käytössä. Näkymä erottaa paikallisen tapahtuman ja hostin hyväksymän synkronoinnin. Uusia jaettuja tai ulkoisia vaikutuksia ei päätellä paikallisesta jonosta.

Peruutus sulkee aktiivisen kuvausistunnon generationin. Myöhäinen kehys tai mallivastaus ei julkaise uutta tulosta peruttuun istuntoon. Jo hyväksytty tehtävähistoria ei katoa automaattisesti kuvaamisen lopettamisesta; varsinainen poistopyyntö käsitellään erikseen.

Poisto ulottuu raakamateriaaliin, johdettuihin havaintoihin, hakuindekseihin ja hallittuihin välimuisteihin. Jäljelle voi jäädä minimaalinen sisällötön poistomerkintä. Jaetun kapselin tuleva käyttö voidaan perua hallitussa palvelussa, mutta jo vastaanottajan itsenäisesti tallettamaa kopiota ei luvata taianomaisesti poistettavaksi.

## 7. Päättely, viive ja kulut

Ensimmäinen putki on tapahtumapohjainen:

1. Käyttäjän pyyntö tai tehtävälle merkityksellinen muutos käynnistää käsittelyn.
2. Laite tarkistaa kuvan käyttökelpoisuuden ja rajaa kiinnostavan alueen.
3. Paikallinen OCR, tunniste tai yksinkertainen vertailu ratkaisee helpot tapaukset.
4. Epäselvä tapaus voi käyttää yhtä rajattua valtuutettua mallikutsua.
5. Tulos sidotaan lähteeseen ja tehtäväversioon.
6. Järjestelmä antaa seuraavan askeleen tai yhden täsmällisen tarkennuksen.

Kysymys “näytä merkintä” voi olla halvempi ja hyödyllisempi kuin uusi suuri malli. Tarkennuksen arvo mitataan sillä, auttoiko se käyttäjää etenemään.

Oletuksena ei tarvita koko päivän videovirtaa. Vain valitun tehtävän tarpeelliset havainnot käsitellään. Myös lyhyen talletuksen säilytysaika ja mahdollinen myöhempi käyttö määritetään käyttötarkoituksen mukaan.

Tuotteen ensimmäiset **ehdotetut**, vielä mittaamattomat suorituskykytavoitteet ovat näkyvä paikallinen kuittaus alle 0,5 sekunnissa ja hyödyllinen yksinkertainen jatkamisvastaus p95 alle 3 sekunnissa määritellyllä laite-/verkkokokoonpanolla. Molemmat mitataan; hitaassa tapauksessa näytetään tila ja tarjotaan käsin jatkaminen.

Tuotantomittari on kustannus onnistuneesti jatkettua tehtävää kohti. Tarkastellaan mallikutsuja, kuvakokoa, tallennusaikaa, uusintayrityksiä ja tukityötä. Nykyinen Lensin paikallinen samanaikaisuusraja ei ole tuotannon hajautettu ajoitusratkaisu.

**Havainnollistava kapasiteettilaskelma, ei ennuste:** 10 000 päivittäistä käyttäjää × 10 tehtävää × 2 pilvikäsittelyä = 200 000 käsittelyä vuorokaudessa, keskimäärin noin 2,3 sekunnissa. Jos huippu olisi 20-kertainen ja käsittely kestäisi 2 sekuntia, yhtäaikaisia käsittelyjä tarvittaisiin noin 93. Todellinen mitoitus perustuu mitattuun kuormaan, purskeisiin ja palvelurajoihin. Hintaa ei voi päätellä ilman valittua palvelua ja laskutusta.

## 8. Laitevalinnat

| Pinta | Ensimmäinen rooli | Mitä ei oleteta? |
| --- | --- | --- |
| iPhone | Käyttäjän ottama kuva, teksti/puhe, vahvistus ja paikallinen käyttö. | Apple Intelligence ei ole ydintoiminnon riippuvuus; esimerkiksi iPhone 14 ei kuulu Applen tukemaan AI-laitejoukkoon. [S11] |
| Meta DAT | Lähde käyttäjän näkökulmasta ja käsien vapautuminen. | MockDeviceKitin lähde ei ole fyysinen lasi; SDK:n saatavuus ei ole käyttäjän laite-/tilipääsy. |
| Mac | Ohjeiden muokkaus, tehtävän selkeä aikajana ja myöhempi asiantuntijanäkymä. | Macin ruutu ei yksin todista lasikokemusta. |
| Meta Display / web | Yksi kompakti seuraava askel, kun juuri tämä hyöty on osoitettu. | Display-kortti ei itsessään ole maailmaan rekisteröity 3D-AR-näkymä. |
| ARKit / Quest / visionOS | Myöhemmin mitattu kohdistus, opastus ja harjoittelu. | Puhelimen posea ei käytetä lasien posena; kunkin laitteen ominaisuudet ja lupaehdot tarkistetaan toteutushetkellä. |

Sovitaan laiteadapterin kyvykkyydet: kamera, ääni, näyttö, luotettava ajanlähde ja erikseen spatiaalinen rekisteröinti. Tehtävälogiikka ei riipu tietystä valmistajasta tai 3D-ankkurista.

Meta AI Connectors ja WebMCP voivat myöhemmin olla jakelureittejä. Niiden käyttöoikeus tai preview-saatavuus ei ole ensimmäisen Resumen kriittinen riippuvuus. Toteutuskohtaiset ominaisuudet tarkistetaan virallisista lähteistä. [S12][S14][S15]

## 9. Ensimmäiset kaksi työpäivää

Arviot kuvaavat järjestystä ja rajattua prototyyppityötä kahdelle tekijälle. Ne edellyttävät käyttökelpoista Apple-ajopaikkaa ja löydettävää Chibi-integraatioreittiä; ne eivät ole lupaus tuotantovalmiudesta 48 tunnissa.

### 0–4 tuntia: lähde ja yhteinen sopimus

Integraattori lukee tuoreet main/PR-headit ja nykyiset omistajuudet. Apple-tekijä tarkistaa yhden käytettävissä olevan Macin/Xcode-ympäristön ja jo talletetut #75-rakennustuotteet. Host-tekijä paikantaa nykyisen Chibi-domainin ja oikean autentikoidun reitin tai kirjaa täsmällisen puutteen.

Sovitaan yksi fixture: kolme esinettä, yksi alue, siirtynyt esine, samannäköinen esine ja peruutus. Se määrittää havainto-, tehtävä- ja virhesopimuksen molemmille.

**Valmis:** omistajat, lähteet ja viesti-/virhesopimus on kirjattu. Laitteiden tai hostin saatavuutta ei päätellä vanhoista manifesteista.

### 4–12 tuntia: kaksi rajattua työlinjaa

**Apple:** käytä säilynyttä testituotetta ja aja puuttuva DAT-integraatio kerran sopivassa Apple-ympäristössä test-without-building-polulla. Tarkista todellinen SDK-kehys, OCR ja myöhäisen tuloksen hylkäys. Uusi rakennus vain jos lähde, työkaluketju tai rakennustuotteen käytettävyys sitä edellyttää.

**Chibi:** toteuta private hostin tehtävän aloitus, vahvistus, keskeytys ja jatkaminen olemassa olevalla pysyvyydellä ja oikeuksilla. Jos host-reitti puuttuu, tee lähteeseen sidottu adapteri ja synteettinen sopimusvalmius; pidä todellisen host-ajon este näkyvänä.

**Valmis:** joko oikea hyväksytty tehtävätapahtuma kulkee päästä päähän tai jäljellä oleva yhteysaukko on paikannettu täsmällisesti. Fixture-tulos ei muutu väitteeksi aktiivisesta hostista.

### 12–24 tuntia: yksi kokonainen Resume

Liitä rajattu havainto tehtävään. Näytä viimeksi nähty tieto, vahvistetut vaiheet ja yksi seuraava askel. Lisää “vahvista”, “korjaa” ja “jatka käsin”. Tarkista uudelleenavaus ja keskeytyksen jälkeinen siirtynyt esine.

Jos laseja ei saada, käytä erikseen toteutettavaa puhelimen kuva-adapteria samalla sopimuksella. Tämä pitää tuoteoppimisen liikkeessä; fyysisten lasien näyttö jää erilliseksi työksi.

### 24–48 tuntia: oikeat episodit ja toimitus

Tee 3–5 käyttäjän tai riippumattoman kokeilijan kanssa lyhyet episodit. Vertaa vastaaviin tarkistuslistatehtäviin ja vaihda suoritusjärjestystä. Tämä löytää käyttökokemuksen ilmeisiä ongelmia; se ei osoita tilastollista paremmuutta.

Tallenna yksi todellinen demo ja sen lähde-/laiterajaus. Tee 5–6 dian esitys: ongelma, kokemus, todellinen toteutus, mitattu tai vielä avoin hyöty, käyttöönotto ja seuraava askel. Lopullinen esityksen julkaisu tai challenge-lähetys kuuluu erilliseen hyväksyttyyn toimituspolkuun.

**Päätöspiste:** jos käyttäjä joutuu tekemään enemmän havainto- ja vahvistustyötä kuin muistamisesta säästyy, supista vuorovaikutusta ennen uusien ominaisuuksien aloittamista.

## 10. Viikot 1–6: käyttökelpoinen pilotti

| Jakso | Toimitus | Ehto seuraavalle vaiheelle |
| --- | --- | --- |
| Viikko 1 | Yksi todellinen Resume-ketju sekä havaintojen ja vahvistusten selkeä ero. | Keskeytys, korjaus ja uudelleenavaus toimivat samalla tehtävällä. |
| Viikko 2 | Offline-jonon rajaus, vanhan version käsittely, muistamisen ja poistamisen peruskäyttö. 8–12 kokeilijaa. | Eteneminen ei tuplaannu; käyttäjät ymmärtävät epävarmuuden ja palaavat kokeilemaan. |
| Viikot 3–4 | Valitaan yksi jatko: Relay, Familiar tai saman työnkulun käyttökelpoisuuden parantaminen. | Valinta perustuu todelliseen palautteeseen ja episodeihin. |
| Viikot 5–6 | Rajattu toistuvan käytön pilotti, kustannus/viive, tarvittaessa yksi uusi adapteri tai kohdennettu malli. | Hyöty toistuu uusilla tehtävävariaatioilla; tuki- ja kuvausvaiva eivät syö arvoa. |

Relay ei tule kalenterin vuoksi: jos kukaan ei tarvitse luovutusta, panostus jää Resumen käytettävyyteen. Familiar ei laajene koko kotiin ennen kuin rajatun pöydän muutokset auttavat oikeassa työssä. Oma malli voi jäädä kokonaan pois ensimmäisestä pilotista.

### Ehdotetut työpaketit

| ID | Tulos ja hyväksyntä | Omistaja / polkuraja | Riippuvuus |
| --- | --- | --- | --- |
| I0 | Lähteet, nykyiset PR-omistajat, yksi sopimus ja toimitusjärjestys. | Nykyinen Junction-integraattori; yhteiset contracts/schemas/manifests/exportit ja testit. | Ei uusia työketjun riippuvuuksia. |
| A1 | #75:n puuttuva SDK-ajonaikainen näyttö; loki erottaa ympäristö- ja lähdevirheen. | Yksi Meta/Apple-kirjoittaja: apps/meta-lens-apple. | #73/#75-lähteet, varmennettu Apple-ajopaikka. |
| H1 | Private Chibi -tehtävädomain: pysyvyys, revision, vahvistus, korjaus ja idempotenssi. | Erillinen Chibi-omistaja; täsmälliset polut vahvistetaan ennen claimia. | I0 ja nykyisen Chibi-lähteen paikannus. |
| A2 | Capture/puhelinadapteri ja host-viestit; lähde/generation säilyvät. | Sama Meta/Apple-kirjoittaja A1:n jälkeen. | A1 tai selvästi merkitty puhelinpolku, H1. |
| R1 | Yksi hyödyllinen seuraava askel, lähde/ikä, korjaus ja manuaalinen jatko. | Meta-kirjoittaja sekä Chibi-omistaja omilla rajoillaan; yhteiset muutokset integraattorille. | H1, A2. |
| P1 | Todellinen demo ja rajattu käyttäjävertailu. | Tuoteomistaja; yksityinen tutkimusaineisto oikeassa säilytyspaikassa, repo vain turvalliset yhteenvedot. | R1. |
| H2 | Offline-konfliktit ja poistojen vaikutus havaintoihin/hakuun. | Chibi-omistaja, Apple-muutokset sarjassa Meta-tekijällä. | H1 ja P1:n havainnot. |
| X1 | Yksi Relay- tai Familiar-koe, jolla on havaittu käyttäjätarve. | Omistaja valitaan työn alussa; ei rinnakkaista kirjoittajaa samaan Meta-pakettiin. | P1, H2. |
| M1 | Lukittu todellinen benchmark ja ehdotetun mallin hyötyvertailu. | Rajattu myöhempi ml-omistajuus services/meta-spatial/ml; ei yksityisiä kuvia repoon. | P1:stä tunnistettu havaintopullonkaula. |
| S1 | Yksi hyödyllinen uusi pinta: Display, AR tai agenttiadapteri. | Erillinen adapteripolku, yhteiset sopimukset integraattorille. | Vakaa tehtävätila ja mitattu hyöty. |

Aloitetaan yhdellä Junctionin Meta-kirjoittajalla ja yhdellä Chibin host-kirjoittajalla. Tämä ei käynnistä työntekijöitä eikä varaa heitä; omistajat tarkistetaan toteutuksen alussa. Yksi raskas natiivi ajo kerrallaan samalla Macilla.

## 11. Todentaminen ilman tarpeetonta testityötä

Nykyisen repon kevennetty työnkulku sallii tavalliset koodi- ja dokumentaatiomuutokset PR:iin ilman pakollista testikierrosta. Valitaan tarkistus konkreettisen riskin mukaan. Vanhaa onnistunutta kokonaistestiä ei toisteta vain ajan kuluttamiseksi. [S13]

Ensimmäisen kokonaisuuden merkitykselliset tapaukset ovat:

- **Keskeytys:** vahvistettu vaihe ja keskeneräinen vaihe palautuvat oikein.
- **Muutos:** siirtynyt tai samannäköinen esine ei muutu nykyiseksi identiteettivarmennukseksi.
- **Myöhäinen tulos:** revoke/disconnect estää vanhan generationin julkaisun.
- **Toistettu komento:** uudelleenlähetys tai uudelleenavaus ei luo toista valmistumista.
- **Oikeus ja rajaus:** toinen tenant tai Relay-vastaanottaja ei saa tehtävän ulkopuolista aineistoa.
- **Korjaus/poisto:** korjattu tieto ei palaudu hakutuloksesta vanhana totuutena.

Jokainen on kohdennettu toteutushetken riskiin. Ne eivät tarkoita uuden suuren testikehyksen rakentamista. Tavallinen UI-teksti voidaan katsoa läpi. Ympäristöongelma kirjataan ympäristöongelmaksi; lähdevirhe korjataan oikeassa kerroksessa.

Tämän suunnitelmadokumentin toimitus tarkistetaan etä-HEADin, yhden muuttuneen tiedoston ja sisällön vastaavuuden avulla. Dokumentin vuoksi ei pyydetä erillisiä tuotekoodin testiajoja. Repon automaattisesti käynnistämien tarkistusten tila luetaan erikseen ja sidotaan niiden todelliseen HEADiin.

## 12. Tuotteen mittarit ja lopettamiskriteerit

Ensisijainen mittari: **aika keskeytyksen päättymisestä seuraavaan oikeaan toimintaan**.

| Mittari | Miksi se merkitsee? | Alustava päätössääntö |
| --- | --- | --- |
| Jatkamisaika | Mittaa suoraan lupausta. | Tavoite noin 25 % parannus vertailuun; tavoite ei ole nykyinen tulos. |
| Unohtuneet ja toistetut vaiheet | Nopeus ei saa tulla virheistä. | Virheet eivät saa kasvaa; eritellään mallin ja käyttäjän virheet. |
| Väärä valmistumismerkintä | Luottamuksen kriittinen tapahtuma. | Jokainen tapaus analysoidaan. Pieni nollatuloksinen otos ei todista yleistä virheettömyyttä. |
| Tarkennuksen onnistuminen | Pelkkä pidättäytyminen ei auta käyttäjää. | Kuinka usein yksi kysymys johtaa oikeaan toimintaan ja paljonko aikaa se vie? |
| Kuvaus- ja vahvistusvaiva | Avustajan ylläpito voi syödä hyödyn. | Käyttäjän lisätyön pitää jäädä säästettyä aikaa pienemmäksi. |
| Vastauskattavuus ja viive | Malli voi näyttää tarkalta kieltäytymällä kaikesta. | Laatu, kattavuus ja viive raportoidaan yhdessä. |
| Omaehtoinen toistuva käyttö | Demo ei osoita tuotetarvetta. | Viikon uusintakäyttö ilman tutkijan jatkuvia kehotuksia. |
| Kustannus onnistunutta tehtävää kohti | Käyttö ei saa skaalata hallitsemattomaksi työksi. | Palvelu-, tallennus-, uusinta- ja tukikulut mukaan. |

Käyttäjävertailussa noin 12 osallistujaa tekee vastaavia tehtäviä tarkistuslistalla, yleisellä avustajalla ja Resumella vaihtelevassa järjestyksessä. Käytetään uusia esine-/tehtävävariaatioita oppimisvaikutuksen vähentämiseksi. Osa vertailusta erottaa puhelimen ja lasien vaikutuksen. Tämä on suunniteltu pienimuotoinen tutkimus, ei etukäteen laskettu tilastollinen teho tai lupaus kattavasta validoinnista.

**Lopeta tai vaihda suuntaa**, jos kahden järkevän UX-kierroksen jälkeen lisätyö ylittää hyödyn; tavallinen tarkistuslista ja yleisavustaja tuottavat saman tuloksen; käyttäjät eivät palaa; tai ainoa ero on näyttävä visualisointi. Jos puhelin voittaa lasit, jatka tehtävämuistituotteena ja lykkää lasipanostusta.

## 13. Oman mallin tie

Nykyisen numeerisen rankerin lisäsiemenet kertovat tämän kokeen vaihtelusta ja heikkoudesta. Ne eivät tuota näköjärjestelmää. Uuden GPU-ajon perusteeksi tarvitaan nimetty virhe ja mittari.

1. **Virheluokittelu:** kuva epätarkka, teksti lukematta, samannäköinen esine, vanha havainto, väärä tehtäväriippuvuus vai hankala käyttöliittymä?
2. **Todellinen vertailuaineisto:** aloita kymmenistä kokonaisista episodeista. Kuvaa valikoituja vaikeita tapauksia eri esineillä, valoilla ja paikoissa. Käyttöoikeudet kirjataan.
3. **Lukittu arviointi:** erottele episodeja ja fyysisiä esineitä, älä vain peräkkäisiä videokehyksiä. Tehtävän oma käyttäjän antama referenssikuva on sallittu syöte, jos se kuuluu tuotteen normaaliin käyttöön.
4. **Yksinkertainen baseline:** OCR/tunniste + tehtävärajaus + tarvittaessa valtuutettu valmis multimodaalimalli.
5. **Kohdennettu oma malli:** esimerkiksi käyttäjän esineiden samankaltaisuushaku, epävarmuuden kalibrointi tai tapahtumien ajallinen tulkinta. Valitse virheen perusteella.
6. **Pienennys ja laitemittaus:** vasta hyödyllinen malli optimoidaan kohde-iPhonelle. Core ML -ajo, viive, muisti, lämpö ja energiankäyttö mitataan aidolla laitteella.
7. **Julkaisu ja palautus:** malli/version valinta sidotaan samaan arviointiin; aiempi toimiva reitti säilyy käytettävissä.

Ensimmäinen benchmark voisi sisältää esimerkiksi 50–100 riippumatonta episodia ennen rajattua pilottia. Se on ehdotus aloituskoon hahmottamiseksi, ei riittävyyslupaus. Arvioinnin luotettavuus riippuu tapauksista, riippumattomuudesta ja tavoitellusta virhetasosta.

Julkisia egosentrisiä aineistoja voidaan tutkia, mutta lisenssi, käyttötarkoitus ja soveltuvuus tarkistetaan ennen käyttöä. Todelliset käyttäjäkuvat eivät siirry automaattisesti koulutusdataksi. Yhteisen oppimisen yksikkö on erikseen sallittu, tarkistettu tehtäväesimerkki.

## 14. Kolmesta kuukaudesta eteenpäin

Aikahaarukat ovat työjärjestyksen suunnittelua, eivät teknologiaennusteita tai luvattuja julkaisuja.

| Horisontti | Kyvykkyys | Edellytys |
| --- | --- | --- |
| 0–6 viikkoa | Resume yhdessä työnkulussa. | Toimiva ketju, korjaus ja käyttäjähyöty. |
| 2–3 kuukautta | Rajattu Relay tai Familiar; ensimmäiset toistettavat ohjeet. | Toistuva käyttö ja näyttö luovutuksen tai muutosten arvosta. |
| 3–6 kuukautta | Usean tehtävän riippuvuudet, ohjeiden luonnostelu episodeista, yksi oikea agentti-integraatio. | Tehtäväversiot, hyväksyntä ja yksityisen datan rajaus toimivat. |
| 6–18 kuukautta | Paikkaan sidottu opastus, jaettu asiantuntijanäkymä, tehtäväkohtainen VR-harjoittelu. | Mitattu spatiaalinen laatu ja hyöty verrattuna yksinkertaisempaan käyttöliittymään. |
| 2–5 vuotta | Menettelyjen siirto ihmisten, laitteiden ja mahdollisesti robotiikan välillä; tilan ja tehtävien yhteinen malli. | Laadukas toistettava tehtävätieto, luotettavat suoritussopimukset ja erillinen fyysisen toiminnan kelpuutus. |

Relay-kapseli sisältää tehtäväversion, tavoitteen, vahvistetut vaiheet, avoimet kysymykset, tarvittavat lähdeviitteet, käyttörajan ja vanhenemisen. Vastaanottaja hyväksyy sen. Käyttäjän koko kuva- tai keskusteluhistoria ei kulje mukana.

Familiar aloittaa nimetyltä pöydältä. Luokat ovat muuttunut, ennallaan, peittynyt ja tuntematon. Esineen puuttuminen nykyisestä kuvasta ei todista, että se on poistettu huoneesta. Toistuvan asetelman tunteminen tukee myöhemmin valmistelu- ja palautustöitä.

## 15. Seitsemän pitkälle vietyä käyttötapaa

Nämä ovat tulevia tuotevaihtoehtoja, eivät nykyisiä ominaisuuksia.

### 1. Keskeytyksen yli jatkuva työmuisti

Käyttäjä aloittaa työn puhelimella, jatkaa laseilla, käsittelee yhden epäselvän kohdan Macilla ja palaa fyysiseen työhön. Sama tehtäväversio seuraa mukana. Arvo kasvaa, kun keskeytys kestää minuuttien sijasta päiviä.

### 2. Työn palautusohje muutoksen jälkeen

Käyttäjä voi kysyä: “Mikä muuttui sen jälkeen, kun tämä oli valmiina?” Järjestelmä näyttää havaitun ja vahvistetun muutoksen sekä ehdottaa palautusaskelia. Historia ei ole kirjaimellinen fyysisen maailman undo; puuttuvat havainnot näkyvät epävarmuutena.

### 3. Asiantuntijuuden siirto näyttää kerran -tyylillä

Asiantuntija tekee rajatun työn, selittää päätökset ja hyväksyy järjestelmän luonnosteleman ohjeen. Seuraava käyttäjä saa samasta ohjeesta omaan tilanteeseensa sopivan seuraavan askeleen. Harvinaiset vaihtoehdot, valmistumiskriteerit ja virheestä palautuminen lisätään tarkastuksessa. Pelkkä yhden videon katsominen ei kelpuuta uutta taitoa.

### 4. Ajasta riippumaton yhteistyö

Yksi ihminen jättää työn vaiheeseen, toinen jatkaa seuraavana päivänä. Hän näkee jo tehdyt asiat, kysymykset ja miksi edellinen tekijä pysähtyi. Tarvittaessa asiantuntija vastaa yhteen rajattuun kysymykseen. Syntyy käytännöllinen vaihtoehto pitkälle “mitä täällä tapahtui” -selitykselle.

### 5. Käyttöohje, joka tuntee työn etenemisen

Laitteen QR tai digitaalinen ohje käynnistää versionoidun menettelyn. Avustaja näyttää vain nykyisen vaiheen, huomaa ristiriidan ja pyytää tarvittavan tarkennuksen. Valmistaja tai kouluttaja voi jakaa ohjeen; käyttäjän yksityinen eteneminen pysyy tämän omassa työtilassa.

### 6. Oma harjoittelutila AR:ssa ja VR:ssä

Todellisen työpisteen rajattu malli ja hyväksytty menettely muodostavat harjoituksen. Käyttäjä voi kokeilla järjestystä ja virhetilanteita ennen todellista työtä. Hyöty mitataan myöhemmässä avustamattomassa tehtävässä: virtuaalisen harjoituksen läpäisy yksin ei riitä.

Taika Motion / Blender voisi tuottaa visualisoinnin ja Reality Twin tilaviitteet. Generoitu puuttuva geometria merkitään arvioksi; se ei muutu tallennetuksi havainnoksi. AR-kohdistuksen epätarkkuus johtaa tekstiohjeeseen tai uudelleenkohdistukseen.

### 7. Tehtävästä toimiva digitaalinen kumppani

Chibi-hahmo voisi myöhemmin näkyä työpisteessä, auttaa sopivalla hetkellä ja muuttaa opettelun peliksi. Hahmo on vuorovaikutuskerros saman tehtävämuistin päällä. Sen identiteetti ja persoonallisuus voivat lisätä sitoutumista, mutta avun ajoitus, korjattavuus ja valmistuva työ ratkaisevat käyttöarvon.

Vielä pidemmällä hyväksytty menettely voidaan sovittaa robottiin tai fyysiseen automaatioon. Se tarvitsee uuden toimilaite-, geometria- ja toimintaturvallisuuden hyväksynnän; ihmisen opastus tai simuloitu video ei suoraan valtuuta robottia toimimaan.

## 16. Yhteys muihin agentteihin ja tuotteisiin

| Osa | Ehdotettu tehtävä | Milloin mukaan? |
| --- | --- | --- |
| Chibi | Käyttäjän tehtävämuisti, oikeudet, vastaanottajat ja todelliset suoritukset. | Heti, rajattu toimiva host-ketju. |
| Meta Lens | Lasien havainnot ja yhden askeleen vuorovaikutus. | Ensimmäisessä demossa käytettävissä olevan laitteen mukaan. |
| Reality Twin / Valmet | Paikan, laitteen tai työpisteen viitteet ja myöhemmin rekisteröinti. | Kun ohjeen sitominen fyysiseen kohteeseen parantaa suoritusta. |
| Taika Motion / Blender | Havainnolliset harjoitukset ja 3D-sisällöt. | Kun menettely on vakaa ja harjoittelulla on osoitettava tavoite. |
| Taimi | Vanhemman ohjaama rajattu yhteinen tehtävä tai luovutus. | Oman käyttäjätutkimuksen ja soveltuvan rajauksen jälkeen. |
| Sailor tai muu alakohtainen agentti | Tietyn työn ohjeet ja rajattu asiantuntijakysymys. | Yhden todellisen toistuvan tarpeen perusteella. |
| NVIDIA / Verda -kehityspolku | Malli- tai 3D-kokeen suoritus olemassa olevilla valtuuksilla. | Kun tarkka laskennallinen pullonkaula ja arviointi on määritetty. |

Taulukko ei väitä näitä integraatioita olemassa oleviksi. Jokainen delegointi kantaa tehtäväversion, pyydetyn kyvykkyyden, rajatut todisteviitteet, vanhenemisen ja toistoneston tunnisteen. Nykyinen Chibi-host tarkistaa oikeudet. Agentin ehdotus palautuu tehtävään; sillä ei ole omaa kilpailevaa käyttäjän tilaa.

Ensimmäisessä tuotteessa pyydetään asiantuntijaa vain tunnistettuun tarpeeseen. Yhden kamerakehyksen ympärille ei käynnistetä koko agenttijoukkoa.

## 17. Liiketoiminta, jakelu ja kestävä etu

Kolme liiketoimintahypoteesia voidaan tutkia järjestyksessä:

1. **Henkilökohtainen käyttö:** toistuvat valmistelu- ja harrastustehtävät. Ratkaiseeko muistaminen riittävän usein ongelman, josta käyttäjä haluaa maksaa?
2. **Pieni työryhmä:** kaluston valmistelu, vuoronvaihto ja keskeneräisen työn luovutus. Säästyykö selitystyötä ja vähenevätkö virheet?
3. **Ohjeen julkaisija:** valmistaja, kouluttaja tai palveluntarjoaja jakaa etenevän käyttöohjeen. Onko sillä arvoa tuessa, koulutuksessa tai onnistuneessa käyttöönotossa?

Hinnoittelua, markkinakokoa tai myyntiennustetta ei johdeta teknisestä demosta. Maksuhalukkuutta ja käyttötiheyttä tutkitaan toimivan kokemuksen jälkeen.

Jakelun luontevia paikkoja ovat olemassa oleva ohje, laitepakkaus, kurssi, tiimin työnjako ja tehtävän luovutuslinkki. QR sisältää ohjeen tai tuotteen osoitteen, ei lupaa, käyttäjätunnistetta tai salaisuutta.

Kestävä etu voi muodostua korjatuista menettelyistä, alakohtaisista vaikeista tapauksista, onnistumisen mittaamisesta ja integroidusta työnkulusta. Pelkkä kuva-arkiston koko, mallin nimi tai lukittu tiedostomuoto on huono puolustus. Käyttäjän pitäisi voida viedä tehtävänsä ja hyväksymänsä ohjeet pois.

## 18. Päätökset nyt, myöhemmin ja vasta näyttöön perustuen

**Nyt ehdotetaan:** Resume ensin; rajattu kameralaukkutyö; Chibi omistaa pysyvän yksityisen tilan; yksi Meta-kirjoittaja ja yksi Chibi-kirjoittaja; puhelinreitti pitää oppimisen liikkeessä; #73 → #75 on nykyinen lähdepino.

**Ensimmäisten episodien jälkeen ratkaistaan:** tuoko lasien käsien vapaus mitattavaa lisäarvoa; missä vahvistus häiritsee; onko oikea jatko Relay vai Familiar; tarvitseeko mikään havaintovirhe omaa mallia.

**Vasta myöhemmin ratkaistaan:** laaja spatiaalinen muistaminen, ohjeiden markkinapaikka, VR-julkaisu, jatkuva ennakointi ja robotiikka. Ne hyötyvät samasta tehtäväperustasta mutta tarvitsevat omat käyttäjä- ja tekniset todisteensa.

### Kolme seuraavaa konkreettista toimeksiantoa

1. **Meta/Apple-omistaja:** jatka #75:n puuttuvasta test-without-building-ajosta varmennetulla Apple-ajopaikalla; säilytä tarkka lähde ja havaittu tulos.
2. **Chibi-omistaja ja nykyinen integraattori:** paikanna oikea host-reitti, lukitse minimaalinen tehtävä-/virhesopimus ja toteuta start → confirm → pause → resume → correct samalla pysyvällä tehtävällä.
3. **Tuoteomistaja:** vie tämä kolmen esineen oikeaan keskeytystilanteeseen ja vertaa tarkistuslistaan ennen uuden ominaisuushaaran avaamista.

Jos ensimmäinen kohta estyy, host ja puhelinpolku voivat edetä. Jos host puuttuu, adapteri ja synteettinen sopimus voidaan toimittaa mutta todellinen yksityinen jatkuvuus pysyy avoimena. Jos käyttäjähyöty puuttuu, teknisesti onnistunut lasidemo ei yksin oikeuta laajentamista.

## 19. Toimitus, rajat ja lähteet

Tämä työ toimittaa suunnitelman sekä dokumentaation oman task-haaran ja luonnos-PR:n. Se ei käynnistä toteutustöitä, malliajoja, palvelimia tai automaatioita. Toteutuksen merge, julkaisu, tuotantomuutos ja uusi kulutus kulkevat nykyisen omistajan valtuuksien kautta.

Kannettavat kokeet ohjataan olemassa olevaan, toteutushetkellä varmennettuun pilviympäristöön. Apple SDK -työt tehdään varmennetulla Macilla tai jo määritetyssä Xcode Cloudissa. Nykyinen CRACI-krediittipoikkeus on aikarajallinen: 15.11.2026 klo 17 UTC / 19 Helsinki. Sitä ei oleteta kuuden viikon budjetiksi tai luvaksi käyttää uusia palveluita. [S13]

### Lähdehakemisto

- **S1:** mainiin integroidun Lens-ytimen README ja lähde; host-portit, rajaukset ja synteettinen demo.
- **S2:** PR #73 ja sen PRODUCT_VISION; Resume, Relay ja Familiar sekä ehdotetut tehtävätyökalut.
- **S3:** #73:n myöhempi Swift-/pariteettinäyttö; vanhempaa PR-tekstiä tarkentava kommentti.
- **S4:** PR #75 ja VERIFICATION.json; virallisen SDK:n lähdepin, rakennustulos ja puuttuva ajonaikainen testi.
- **S5:** PR #70:n numeerisen mallin README; ei kuvantunnistuksen tulos.
- **S6:** mainin CRACI-portfolioraportti ja kampanja 43552620643.
- **S7:** Junctionin nykyiset arkkitehtuuri- ja Chibi-omistajuusrajat.
- **S8:** Metan oma kuvaus Private Processingista, 23.9.2026.
- **S9:** Googlen oma Project Astra -kuvaus; tutkimusprototyyppi.
- **S10:** 14.11.2026 lähdekatalogin Meta M342 -brief ja sponsoriviitteet.
- **S11:** Applen viralliset Apple Intelligence -laitevaatimukset.
- **S12:** Metan virallinen Device Access Toolkit -dokumentaatio; tarkistetaan uudelleen toteutushetkellä.
- **S13:** tämän suunnittelun main-SHA:n AGENTS.md; kevennetty työnkulku, integraattori ja nykyinen CRACI-rajaus.
- **S14:** Metan virallinen Web Apps -dokumentaatio.
- **S15:** Metan virallinen Connectors-kuvaus.

[S1]: https://github.com/SalesSquad/junction-pets/blob/98d5a524d61e431ca36acd62b268ede343fc7fe2/services/meta-spatial/README.md
[S2]: https://github.com/SalesSquad/junction-pets/blob/82f17099ae1d52efde6661e69f7ea5e38fdcd407/apps/meta-lens-apple/PRODUCT_VISION.md
[S3]: https://github.com/SalesSquad/junction-pets/pull/73#issuecomment-6868021685
[S4]: https://github.com/SalesSquad/junction-pets/blob/4eaac725b2032253c9e2414a6997ff4bb064e442/apps/meta-lens-apple/DATMockApp/VERIFICATION.json
[S5]: https://github.com/SalesSquad/junction-pets/blob/634f1e0e6cb2de46bcf0a783532d46c23f513d11/services/meta-spatial/ml/README.md
[S6]: https://github.com/SalesSquad/junction-pets/blob/98d5a524d61e431ca36acd62b268ede343fc7fe2/docs/CRACI_PORTFOLIO_20261114.md
[S7]: https://github.com/SalesSquad/junction-pets/blob/98d5a524d61e431ca36acd62b268ede343fc7fe2/ARCHITECTURE.md
[S8]: https://engineering.fb.com/2026/09/23/security/private-processing-meta-ai-glasses/
[S9]: https://deepmind.google/models/project-astra/
[S10]: https://github.com/SalesSquad/junction-pets/blob/02458b4e9025d9f45b071765c0601e53d6c94877/docs/challenge-research/current-source-catalog.json
[S11]: https://support.apple.com/en-gb/121115
[S12]: https://developers.meta.com/wearables/device-access-toolkit/
[S13]: https://github.com/SalesSquad/junction-pets/blob/98d5a524d61e431ca36acd62b268ede343fc7fe2/AGENTS.md
[S14]: https://developers.meta.com/wearables/web-apps/
[S15]: https://dev.meta.ai/products/connectors
