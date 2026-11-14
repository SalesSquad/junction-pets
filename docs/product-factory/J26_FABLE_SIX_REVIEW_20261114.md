<!-- Independent Fable 5.2 review, executed 14 Nov 2026 in an isolated no-tools native Claude Code session. This is a model critique, not a verified hardware/code test. Original source text SHA-256 a5867b439890822b2ff6686559e9b12d6a79e627777afc0337c914459166d223; no provider account IDs, prompts or keys. -->

# J26: kuuden lippulaivan riippumaton arvio (14.11.2026)

**Ydinviesti:** kuutta rehellistä demoa ei saada valmiiksi sunnuntaihin klo 10:00 mennessä, kun lähtötaso on nolla ajettavaa tuotetta. Tee kaksi palautuskelpoista (AZ ja toinen päätössäännöllä), yksi laitteistoportitettu ja kolme suunnitelmatasolle. Yhteinen kernel ei kuulu tapahtumakelloon.

En ole testannut, ajanut tai selannut mitään; arvio perustuu antamiisi lähdetietoihin ja omaan päättelyyni.

## Faktat ja oletukset

**Faktat (antamasi lähteet):** haasteiden vaatimukset ja rubriikit, Rokokon 207 MB:n CSV ja SDK-lisenssi, Aallon 20 episodia / 11 720 kehystä ja RTX ≥ 24 GB, ds003478:n rajaus, Intelin kolme ristiriitaista pisteytystä sekä se, ettei yhdelläkään kuudesta ole ajettavaa tuotetta tai varmistettua laitteistoa.

**Omat oletukseni, tarkista ennen kuin nojaat niihin:**
- Junctionin säännöt voivat rajata, montako palautusta yksi tiimi saa tehdä ja mitä aiempaa koodia saa käyttää.
- Julkinen aluetason data hoitopolun viiveistä on Suomessa epätasaista: levinneisyys, seulontaosallistuminen ja elossaolo löytynevät, diagnostinen viive alueittain heikommin.
- Syöpästrategian tavoitteen 3 sanamuotoa en tunne; siteeraa se suoraan lähteestä.
- VLA-malli ei välttämättä aja NPU:lla; tarkista OpenVINO-dokumentaatiosta.
- Kaupalliset arviot ovat näkemyksiäni, eivät markkinadataa.

## 1) Top 12 aukkoa

| # | Taso | Aukko | Korjaus |
|---|---|---|---|
| 1 | P0 | Laajuus: kuusi demoa, alle vuorokausi, nolla ajettavaa | 2 palautusta + 1 portitettu + 3 suunnitelmaa; päätös tänään |
| 2 | P0 | Palautuskelpoisuus (palautusten määrä, aiempi IP, MIT) varmistamatta | Kysy järjestäjältä kirjallisesti nyt; Taimi/Valmet-koodia ei mukaan ilman varmistusta |
| 3 | P0 | Kernel ja Rust eivät tuota yhtään rubriikkipistettä 24 tunnissa | Yksi JSON-kuittiskeema ja sivun konventiot; ei yhteistä ajoympäristöä |
| 4 | P0 | Aalto Humanoid: ei RTX-renderöintiä eikä pilvibudjettia, joten suljetun silmukan arviointi on mahdoton | Modulaarinen ratkaisu ja vain avoimen silmukan mittarit, kunnes GPU on |
| 5 | P0 | Intel: asema varmistamatta, kolme eri rubriikkia | Pyydä sponsorilta kirjallinen ratkaisu; optimoi yhteiseen osaan (tehtävän onnistuminen ja integraatio) |
| 6 | P0 | AZ: "politiikkasimulaattori" väittää kausaalisuutta, jota aggregaattidata ei tue | Muuta muotoon "eriarvoisuuden löytäjä + lähdeviitattu toimenpidekortti"; skenaariot vain avoimena laskuna |
| 7 | P1 | AZ: pienet luvut, ikävakiointi, aluejakojen muutokset; potilasviivettä ei saa eroteltua julkisesta datasta | Luottamusvälit, pienten solujen peitto ja näkyvä "ei voida erottaa" |
| 8 | P1 | Rokoko: haaste vaatii SDK:n käyttöä, mutta teillä on vain CSV; lisäksi tuplaotsikot ja laitekellot | Varmista, kelpaako tallenne + simulaatio; jäsennä sarakkeet sijainnin mukaan (kirjastot nimeävät duplikaatit hiljaa uudelleen) |
| 9 | P1 | Beyond Clinic: trendien seuranta liukuu helposti riskipisteeksi; ds003478 houkuttaa väärinkäyttöön | Vain kuvailevat trendit käyttäjän omaan lähtötasoon; EEG-data pois tuotteesta |
| 10 | P1 | Arduino: summeri ei säästä energiaa, ja laitteen oma tehonkulutus sekoittuu rakennuksen säästöön | Mittaa havaintotarkkuus ja laitteen watit; säästö vain "mallinnettuna" |
| 11 | P1 | Mittarit: 20 episodilla mikä tahansa jako antaa valtavan epävarmuuden; "suljettu silmukka" ei sovi AZ:lle | Raportoi aina n ja Wilsonin väli; jako episodi- ja kappaletasolla |
| 12 | P2 | Lisenssit ja julkaisu: SDK-binäärit, esimerkkidatan ja OpenNeuron ehdot, Project Hub -julkaisijaa ei nimetty | Ei SDK:ta eikä sponsoridataa MIT-repoon; nimeä julkaisija tänään |

## 2) Tuotteet

### AZ: Care Equity Navigator
- **Wow:** kartta, joka kieltäytyy asettamasta alueita järjestykseen, kun data ei riitä, ja tuottaa kolmella klikkauksella yhden toimenpidekortin (ero, lähde, vastuutaho, seurantamittari, kytkös tavoitteeseen 3).
- **MVP:** 2–3 polun vaihetta julkisista lähteistä, ikävakioidut luvut väleineen, yksi huolella tehty toimenpidekortti ja alle kahden minuutin demo.
- **Kuukausi 1 / 90 päivää:** toistettava dataputki ja päivitysajot; sosioekonomiset taustamuuttujat, epidemiologin menetelmäkatselmus ja pilotti yhden hyvinvointialueen kanssa.
- **Esteet:** viivedatan saatavuus aluetasolla ja aluejakojen yhteensovitus.
- **Portit:**
  1. 100 %:lla näytön luvuista on lähde ja hakupäivä.
  2. Koko putki raakadatasta kuviin ajetaan yhdellä komennolla.
  3. Demo kestää enintään 110 s ja kortti aukeaa enintään kolmella klikkauksella.
- **Vertailutaso:** raakalukujen ranking ilman vakiointia ja luottamusvälejä.
- **Ei saa väittää:** kausaalivaikutuksia, säästettyjä henkiä, yksilötason päätelmiä tai potilasviiveen erottelua.

### Rokoko: MotionBridge
- **Wow:** laatuportti teleoperaatiodatalle. Jokainen episodi saa kuitin aikasynkronin luotettavuudesta ja robottikelpoisuudesta (nivelrajat, nopeudet), ja vain kelvollinen liike päätyy opetusdataan. Pelkkää uudelleenkohdistusta tekevät kaikki.
- **MVP:** sponsorin CSV kevyeen CPU-simulaattoriin toistona, selvästi merkittynä tallenteeksi. Kvaternioille slerp ja etumerkin jatkuvuus, 83/200 Hz yhteiselle aikakannalle, vienti LeRobot-muotoon.
- **Kuukausi 1 / 90 päivää:** SDK-suoratoisto ja ROS2-silta; Isaac-sovitin sekä osoitus siitä, että suodatettu data parantaa opittua politiikkaa.
- **Esteet:** SDK-hyväksyntä, laitteet ja kameroiden kellosynkroni ilman yhteistä tapahtumaa.
- **Portit:**
  1. 100 % tiedostoista jäsentyy sarakemäärän validoinnilla.
  2. Käsittely pysyy yli 200 Hz:ssä, p95 raportoituna.
  3. Rajarikkomuksia on suodatuksen jälkeen nolla, ja vertailutason luku näytetään rinnalla.
- **Vertailutaso:** suora nivelkulmien kopiointi.
- **Ei saa väittää:** live-teleoperaatiota, testattua SDK- tai Isaac-integraatiota tai laitteiston viivelukuja.

### Aalto Humanoid: nimi pois "Generalist"-sanasta
- **Wow:** ohje muuttuu näkyväksi väri→laatikko-taulukoksi ennen liikettä, ja politiikka pidättäytyy, jos ohje on epäselvä.
- **MVP:** ohjeen jäsennin (6 permutaatiota ja parafraasit), väri- ja muotohavainto datan kehyksistä, pieni matkimisoppimismalli ja nopeusmittaus.
- **Kuukausi 1 / 90 päivää:** suljetun silmukan arviointi RTX-koneella; lisädata, palautumiskäytös ja yhteensopivuus järjestäjän turvasuodattimen kanssa.
- **Esteet:** GPU, datan vähyys ja heikkolaatuiset demot.
- **Portit:**
  1. Ohje→kuvaus on 100 % oikein mallipohjilla ja vähintään 95 % parafraaseilla.
  2. Päättelyn p99 on enintään 33 ms kohdelaitteella.
  3. Vähintään 50 simulaatioepisodia ilman turvarikkomuksia ja onnistuminen yli vertailutason; tämä vasta, kun GPU on käytössä.
- **Vertailutaso:** päästä päähän -matkimisoppiminen ilman ohjeen eksplisiittistä käsittelyä.
- **Ei saa väittää:** onnistumisprosenttia ilman suljettua silmukkaa, yleistymistä tai oikean robotin turvallisuutta.

### Beyond the Clinic: Recovery Companion
- **Wow:** "näe mitä kliinikko näkisi" -esikatselu. Mitään ei lähde ilman käyttäjän hyväksyntää, jako on peruttavissa yhdellä toiminnolla, ja jokainen ehdotus näyttää perustelunsa.
- **MVP:** synteettiset persoonat, mobiiliselainnäkymä, 2–3 matalan riskin toimintoa (valo, musiikki, yhteydenotto) ja kliinikon yhteenveto.
- **Kuukausi 1 / 90 päivää:** kliinikon tarkastamat sisältöpohjat ja paikallinen tallennus; käytettävyystutkimus eettisellä arvioinnilla ja sääntelyluokituksen selvitys (hyvinvointisovellus vai lääkinnällinen laite).
- **Esteet:** kliininen kumppani ja kokemusasiantuntijat.
- **Portit:**
  1. Käyttöliittymässä on nolla diagnoosi- tai hoitoväitettä, tarkistettuna kieltolistalla.
  2. 100 %:lla jaoista on suostumuskuitti ja toimiva peruutus.
  3. Kriisiapu löytyy jokaiselta näytöltä enintään kahdella napautuksella.
- **Vertailutaso:** staattinen omahoitosuunnitelma tai pelkkä mielialapäiväkirja.
- **Ei saa väittää:** relapsin ennustamista, TMS-ylläpitotehoa, EEG-validointia tai hoitoa.

### Arduino: nimi pois "OS"-sanasta
- **Wow:** tyhjän huoneen hukkavahti, jonka yksityisyys on arkkitehtuurissa. Kuva ei poistu laudalta, ja MCU jatkaa vikasietoisesti, jos Linux-puoli kaatuu.
- **MVP (vain jos lauta saadaan):** läsnäolomalli Linux-puolella, lämpötila MCU:n kautta, Bridge-kutsut, summeri ja säätönuppi mukavuusrajalle.
- **Kuukausi 1 / 90 päivää:** viikon mittausjakso oikeassa tilassa; mitattu interventio, jossa ihminen toimii hälytyksen perusteella.
- **Esteet:** laitteisto varaamatta ja 2 GB muistia.
- **Portit:**
  1. Läsnäolon F1 on vähintään 0,9 vähintään 200 itse merkityllä kehyksellä.
  2. Verkkoliikennettä on nolla ajon aikana, ja laitteen teho on mitattu USB-mittarilla.
  3. MCU reagoi alle sekunnissa, kun Linux-prosessi tapetaan.
- **Vertailutaso:** ajastin tai kynnyssääntö.
- **Ei saa väittää:** säästettyjä kilowattitunteja tai ilmanvaihdon ohjausta.

### Intel: Inspect-to-Action Cell
- **Wow:** näyttöön sidottu lajittelu. Poikkeamamallilla on veto-oikeus VLA:han, epävarma pala menee uudelleentarkastukseen, ja jokaisesta palasta syntyy kuitti (kuva, poikkeamakartta, päätös, viive, joulet).
- **MVP ilman asemaa:** Anomalib-putki omilla Duplo-kuvilla, OpenVINO-vienti ja mittaukset sillä Intel-raudalla, joka teillä oikeasti on, laite nimettynä. Ei live-väitteitä.
- **Kuukausi 1 / 90 päivää:** oma SO-101-asema ja datan sukupuu; laitekohtainen CPU/GPU/NPU-vertailu ja pidempi autonominen ajo.
- **Esteet:** asema, Series 3 -rauta ja rubriikkiristiriita.
- **Portit:**
  1. Kolmen kulhon onnistuminen on vähintään 80 % vähintään 30 peräkkäisellä autonomisella yrityksellä, väli ja ihmisen puuttumiset raportoituna.
  2. Viive p50/p95 on raportoitu laitekohtaisesti.
  3. Energia per pala on mitattu ja menetelmä dokumentoitu.
- **Vertailutaso:** VLA yksin ilman tarkastusporttia.
- **Ei saa väittää:** ajamatonta live-ajoa, toisen raudan NPU-lukuja tai arvioitua energiaa mitattuna.

## 3) Yhteentoimivuus

**Jaa vain nämä:**
- **Kuittiskeema (JSON):** `schema_version`, lähdeviitteet tiivisteineen ja hakupäivineen, syötteen tiiviste, päätös, portin tulos ja aikaleimat.
- **Aikakanta:** isännän monotoninen vastaanottoaika ja laitteen oma aika erikseen sekä arvioitu siirtymä, ryömintä ja epävarmuus. Laiteaikaa ei koskaan ylikirjoiteta.
- **Robotiikan konventiot (Rokoko, Aalto, Intel):** SI-yksiköt, radiaanit, kvaternion järjestys eksplisiittisesti, koordinaatistojen nimet ja nivelet nimen eikä indeksin mukaan.
- **Episodimuoto:** LeRobot v3 sellaisenaan, ei omaa formaattia.
- **Arviointiraportti:** n, onnistuminen, Wilsonin väli, p50/p95 ja laitekuvaus.

**Versiointi:** semver, minor-versioissa vain lisäyksiä, ja yhteensopivuus todetaan golden-tiedostoilla eikä yhteisellä kirjastolla.

**Oikeasti uudelleenkäytettävä koodi:**
- Kvaternio- ja uudelleennäytteistysapuri (Rokoko ja Aalto).
- LeRobot-lataaja ja episodijakaja (Aalto, Intel ja Rokokon vienti).
- Viive- ja energiamittauskehys (Aalto, Intel, Arduino).
- Lähdeviitekomponentti selaimessa (AZ ja Beyond Clinic; vain komponentti, ei dataa).

**Suostumusraja:**
- Beyond Clinic on täysin oma reponsa ja tallennuksensa.
- AZ:ssa ei ole henkilötietoja, joten sen kontrolli on pienten solujen peitto eikä suostumus.
- Liikekaappaus on tunnistettavan ihmisen dataa ja vaatii operaattorin suostumuksen.

**Älä jaa:** ajoympäristöä, tallennusta, politiikkaportteja (ne ovat toimialakohtaisia), identiteettiä, kojelautoja, malleja tai suostumuslogiikkaa.

## 4) Toimintasuunnitelma

**Omistajat:** kuusi nimettyä omistajaa. Skeemaomistajan tehtävä viikonloppuna on yhden sivun konventiot ja lisenssi- ja IP-tarkastus, ei koodia.

**Prioriteetti:**
1. AZ täydellä teholla.
2. Toinen palautus alla olevalla päätössäännöllä.
3. Arduino tai Intel vain, jos laitteisto varmistuu.
4. Aalto Humanoid suunnitelmatasolle, ellei RTX-konetta ole jo käsissä.

**Ehdotettu aikataulu:**
- Laitteistopäätökset tänään klo 20.
- Ominaisuusjäädytys klo 02.
- Demovideo klo 07.
- Palautus klo 09.

**Laitteistoportit:**
- **G0:** pääsy ja rauta vahvistettu kirjallisesti.
- **G1:** kuiva-ajo ilman liikettä tai simulaatiossa.
- **G2:** hidas ajo, hätäpysäytys ja ihminen vieressä, työalue rajattu.
- **G3:** autonomiset, lasketut yritykset.
- **G4:** demo raakalokeineen.

Jos G0 ei toteudu määräaikaan mennessä, palautetaan rehellinen "laitteistoa odottava" paketti.

**Robottiturvallisuus:**
- Rust-politiikkaportti ei ole turvajärjestelmä. Rajat (nivel, nopeus, työalue, vahtikoira, hätäpysäytys) kuuluvat alimmalle tasolle ja ovat opitusta politiikasta riippumattomia.
- Aallon robotilla järjestäjän suodatin omistaa turvallisuuden; oma kerros ei saa peittää sen signaaleja.
- Pidättäytymisen on oltava määritelty turvallinen tila; "pysähdy paikalleen" ei aina ole sellainen.
- Teleoperaatiossa pakettikato johtaa pitoon eikä ekstrapolointiin.
- Käsi työalueella tarkoittaa, että käsivarsi on pois päältä.

**Hoitoetiikka:**
- **AZ:** alueiden leimaaminen ja ekologinen harha ovat todellisia riskejä. Lääkeyhtiösponsorin intressi on tuotava näkyviin, eivätkä ehdotukset saa kallistua lääkehoitoihin ilman näyttöä.
- **Beyond Clinic:** käyttäjät ovat haavoittuvia. "Osallistuminen" tavoitemittarina palkitsee nalkuttamisesta, joten korvaa se käyttäjän itse asettamilla tavoitteilla.
- Poisjättäytyminen ei ole epäonnistuminen, eikä hälytyksen puuttuminen tarkoita, että kaikki on hyvin.
- Kriisitilanteissa ei käytetä generoitua vapaata tekstiä, vain kliinikon tarkastamia pohjia.
- Kliinikkonäkymä ei saa muuttua valvonnaksi.

## 5) Tuomio

**Vahvimmat kaksi palautusta:**
1. **AZ.** Faktaa: julkinen data, ei laitteistoa, selkeä tuomarin toive. Oletusta: viivedata riittää vähintään kahteen polun vaiheeseen.
2. **Rokoko**, jos sponsori vahvistaa tänään, että tallenne + simulaatio täyttää SDK-vaatimuksen tai SDK-pääsy hyväksytään. Muuten **Beyond the Clinic**, jolla ei ole ulkoisia riippuvuuksia. Faktaa: Rokokon rubriikki on tiedossa ja data on olemassa. Oletusta: kelpoisuus ilman live-laitteita.

Jos tiimi saa palauttaa vain yhden, se on AZ.

**Vahvimmat kolme kaupallista kiilaa (kaikki omia arvioitani):**
1. **Teleoperaatiodatan laatuportti (Rokoko).** Robottioppimisen pullonkaula on kelvollinen data, ja tuote on laiteriippumaton.
2. **Näyttöön sidottu tarkastussolu (Intel).** Auditointijälki per kappale on teollisuudelle ostettava ominaisuus.
3. **Care Equity Navigator.** Ostajia on (hyvinvointialueet, syöpäkeskukset, lääkeyritykset), mutta julkinen data ei suojaa kilpailulta; puolustettavuus tulee menetelmästä ja päivitysputkesta.

Beyond Clinic jää ulos sääntelytaakan ja pitkän myyntisyklin takia, Arduino täyden markkinan takia.

## 6) Eriävä suositus kernelistä

Kyllä, se on ylisuunnittelua.
- "Havainto→hypoteesi→ehdotus→portti→vaikutus→kuitti" on robotiikalle luonteva, mutta AZ:lle ja Beyond Clinicille väkinäinen. Lisäksi se luo juuri sen kytköksen, jonka luottamusrajasi kieltävät.
- Tee sen sijaan yhden sivun spesifikaatio, golden-tiedostot ja kolme apumoduulia.
- Nosta koodi yhteiseksi vasta, kun kaksi tuotetta on kirjoittanut saman asian erikseen.
- Ota Rust käyttöön vasta, kun on oikea deterministinen turvakomponentti laitteistolla, jota itse hallitsette.
