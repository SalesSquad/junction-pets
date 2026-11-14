# Junction 2026 — kuuden flagship-tuotteen yhteinen kehitysohjelma

**Työ-ID:** J26-PF-SIX-FLAGSHIPS-20261114  
**Laadittu:** 14.11.2026, Helsinki  
**Lähdeperusta:** SalesSquad/junction-pets, autentikoidun `origin/main`-haun havaittu SHA `98d5a524d61e431ca36acd62b268ede343fc7fe2` (tarkista uudelleen ennen koodausta). Viisi pakollista entrypointia: `START_HERE.md`, `AGENTS.md`, `docs/AGENT_SOURCE_INDEX.json`, `docs/challenge-research/CURRENT_SOURCES.md`, `docs/challenge-research/current-source-catalog.json`; snapshot 14.11.2026, 38 briefiä, 35 kumppanin evidenssiavainta.  
**Soveltamisala:** Kuusi Junctionin 19 päätuotteesta, joilla [#80:n viimeisimmässä lähdepohjaisessa inventaariossa](https://github.com/SalesSquad/junction-pets/issues/80#issuecomment-6872525756) ei vielä ole ajettavaa päätuotetta. Muut 13 eivät ole automaattisesti tuotantovalmiita.  
**Muutosluokka:** toteutussuunnitelma, EI julkaisu-, laite-, integraatio- tai testisuoritus. Kumppanihaasteiden päivitetyt ohjeet, etenkin `latestClarification`, ohittavat vanhemmat keskustelut. Suunnitelman avoimet resurssit ja laatutavoitteet ovat ehdotuksia, eivät toteutuneita tuloksia.

## 1. Tuoteportfolio — kuusi itsenäistä menestyjää

| # | Virallinen haaste, avain ja brief | Tuote / ensimmäinen käyttäjä | Lupaava erottautumistekijä | Portin 1 välitön tavoite |
|---|---|---|---|---|
| 09 | AstraZeneca `astra-zeneca` / `M344` | **Equity Navigator** — hyvinvointialueen syöpähoidon kehitysjohtaja | Lähdepohjainen *toimenpidekartta* kansallisen strategian tavoite 3:een, ei pelkkä epätasa-arvokartta | Julkisen aggregaattiaineiston provenienssi → 2 min:n päätösbrief |
| 15 | Rokoko `rokoko` / `M326` | **MotionBridge Studio** — robotiikkalaboratorion teleoperaattori | Opeta liikkeellä, näytä turvarajat, nauhoita auditoitava demonstraatio ja uudelleentoista simulaatiossa | Rokoko-esimerkkidatan parseri + turvallinen simulaatiotoisto |
| 16 | Aalto `aalto` / `M320` | **Humanoid Skill Engine** — tutkimuslaboratorion robotti-insinööri | Ohjeen mukaan muuntuva tarttuminen ja lajittelu epävarmuuden sekä turvallisen palautumisen kanssa | Kilpailun 30 Hz:n policy-server-sopimus ja rajattu baseline |
| 17 | Aalto `aalto` / `M343` | **Recovery Compass** — TMS-hoidon jälkeen arkea rakentava ihminen | Omaehtoinen, vähäkuormitteinen hyvinvoinnin tukisuunnitelma, joka näyttää epävarmuutensa ja oppii valinnoista | Turvallinen täysin synteettinen check-in → valinnainen tuki → peruuta -polku |
| 18 | Arduino `arduino` / `M356`, `T45` | **Green Edge OS** — taloyhtiön tai työtilan käyttäjä | Yksityisyyttä suojaava paikallinen sensoritulkinta ja mitattava energia-/mukavuuspäätös ilman pilviriippuvuutta | UNO Q -sopiva App Lab -sovellus + oikea anturi, jos laite vahvistuu |
| 19 | Ignite×Intel `ignite-next-and-intel` / `M330` | **Inspect-to-Action Cell** — laaduntarkastusta automatisoiva tuotantotiimi | Jokaisesta fyysisestä lajittelusta todennettava kuva–vika–päätös–liike–tulosketju | Jäädytetty virallinen station-rajapinta → Anomalib + action-loop paikallisen lähdedatan avulla |

**Liiketoiminnallinen vaatimus:** jokaisella on oma kohdeasiakas, oma hinnoiteltava hyöty, turvallinen fallback, erottuva demo ja itsenäinen 90 päivän roadmap. Kuusi tuotteita ei kopioida samaan appiin kuudella nimellä. Sponsorin omasta SDK:sta/hardwaresta ei väitetä yhteyttä ilman todennettua ajokuittia.

## 2. Järkevä yhteinen alusta: *Evidence-to-Action* — ei megamonoliittia

Yhteiset kaavat ovat kalliita keksiä kuudesti: tapahtuma-aika, kameran koordinaatisto, yksiköt, luvalliset vaikutukset, turvallinen kieltäytyminen, alkuperä ja testiepisodin toistettavuus. Nämä ovat **ehdotettuja yhteensopivuussopimuksia, eivät rakennettavaa yhteistä ajoympäristöä**. Hackathon-vaiheessa tehdään vain yksi sivu konventioita ja muutama golden-esimerkkitiedosto; ei uutta Rust-kerneliä, keskitettyä tallennusta eikä yleistä politiikkamoottoria. Yhteinen integraattori saa nostaa koodia jaettuina kirjastoina vasta, kun vähintään kaksi tuotetta tarvitsee samaa todettua toimivaa moduulia. Viisi rajapintaehtoa voidaan supistaa tuotteissa niitä tarvitseviin kenttiin.

1. **`observation.v1`** (robotit/edge): `event_id`, `source`, `clock_domain`, `captured_at_utc`, `monotonic_ns`, `frame_id`, `units`, `calibration_version`, `data_digest`, `synthetic_or_real`, `quality_flags`. Kameralla, käsineellä ja MCU:lla on eri kellot — niiden aikaleimoja ei oleteta automaattisesti yhteismitallisiksi.
2. **`action-proposal.v1`** (robotit/edge): ehdotettu liike/ohjaus, rajat, havaintoviitteet, vastuullinen ohjauspolitiikka, `deadline`, `idempotency_key`, pysäytys- ja manuaaliohitusmahdollisuus. Tämä on **ehdotus**; vain paikallinen turvallisuuskontrolleri voi hyväksyä fyysisen toiminnon.
3. **`episode-receipt.v1`** (robotiikka): pinattu input- ja malliversio, robotin/SDK:n versio, yksikkö- ja muunnoshistoria, telemetria, syötesplit, pysäytykset, lopputulos, `SIMULATED`/`PHYSICAL`-raja. Ei videoita, tunnistetietoja eikä luvattomia laiteavaimia defaultina.
4. **`decision-evidence.v1`** (tuotteiden perustelut): luvallinen lähde, julkaisuaika, dataprosessoinnin versio, väite, epävarmuus, vaihtoehdot, ihmisen päätösvastuu. Tämä **skeema** voidaan jakaa AstraZenecan, Recovery Compassin ja robotiikan kesken; käyttödataa, mallipainoja tai päätöspolitiikkaa ei.
5. **`eval-case.v1`** (tarkistuskriteerit): mitattava vaatimus, datasetin lisenssi ja SHA, erotetut train/validation/holdout-joukot, todennusympäristö, baseline, tulos, epäonnistuminen ja verifioijan omistaja. Sama manifestimuoto vähentää itseään toistavia QA-kierroksia.

**Eristys on olennainen:** kliininen/henkilökohtainen Recovery Compass ei käytä yhteistä robottilokia tai datavarastoa; AstraZeneca käyttää vain aggregoitua julkista tietoa; robotteja ei voi ohjata geneerisellä agenttityökalulla ilman laitteen omia portinvartijoita. Robotiikan nopeat kontrollisilmukat eivät kulje pilvessä toimivan LLM:n läpi. Malli ehdottaa korkealla tasolla, rajattu deterministinen kontrolleri päättää ja pysäyttää.

**Oletusteknologia:** Rust/Python/TypeScript tuoterajapinnoissa, ROS 2 / Isaac Lab vain yhteensopiville robottiadeptereille, OpenVINO Intelille, Arduino App Lab (Python + Sketch/Bridge) UNO Q:lle, saavutettava web-UI selityksille. Versiot ja laiteprotokollat pinataan per tuote: ei oleteta että Rokokon nykyinen Isaac Lab 2.3/Isaac Sim 5.1 on yhteensopiva Aallon kilpailusimulaattorin kanssa ilman omaa adapteria. Verda/CRACI/Codex Cloud ovat **erillisiä, todentamista vaativia suoritusympäristöjä**, eivät yksi ja sama olemassa oleva worker tai rajaton GPU-tili.

### Todelliset uudelleenkäytön nuoliketjut

- **Rokoko → Aalto Humanoid:** lisensoidut, luvallisesti kerätyt ihmisen käsiliikkeet → koordinaattimuunnos/retargetointi → ehdotettu demonstraatioepisodi → G1-turvafiltteri → eroteltu harjoitusdata. Ei suoraa liikeradan toistoa fyysisessä robotissa.
- **Rokoko → Intel:** SO-101:n erikseen kalibroitu opetuskäyttö ja episodit; alkuperäinen leader-arm on vahvin baseline. Älä väitä, että Smartgloves on heti SO-101-tuki.
- **Aalto Humanoid ↔ Intel:** yhteinen havainnon ja ohjeen versiointi, epävarmuuden käsittely, epäonnistuneen tarttumisen recovery ja häiriötestien malli. **Ei** yhteisiä robotin jointtikäskyjä, painoja tai geometrioita.
- **Arduino → Intel:** Edge telemetry, watchdog ja MCU-turvallisuusperiaatteet; Arduino UNO Q ei korvaa Intelin aidosti mitattavaa Core Ultra/NPU-kohdetta.
- **AstraZeneca ↔ Recovery Compass:** ihmislähtöinen päätösperustelu, suostumus ja epätietoisuuden esittäminen; **ei** yhteisiä potilastietoja, yksilötason riskiarvopäätelmiä eikä kliinistä suositusmoottoria.
- **Kaikki → arviointialusta:** ohjelmiston laatumittarit ja lähdekuittiformaatti uudelleen käytettäväksi myös Valmetissa, Reality Twinissä ja muissa tuotteissa, jos tekijänoikeudet ja tutkimusehdot sallivat.

## 3. LINJA 1 — AstraZeneca: Equity Navigator

### 3.1 Vaikuttava tuote, ei tilastokartta
**Kenelle:** hyvinvointialueen palvelujohtaja, FICAN/THL-tason kehittäjä, syöpähoidon suunnittelija. **Aito työ:** “Mikä vaihe ja mikä alue on ongelma, miksi tieto on epävarmaa, mikä yksi käytännön toimi vähentäisi viivettä, kenen pitää tehdä se ja miten tulos mitataan?”

**Kärki:** valtakunnallinen *Cancer Pathway Opportunity Engine* rakentaa lähteistetyn alue × syöpätyyppi × polun vaihe × ajankohta -näkymän ja kaksi toteutuskelpoista interventiokorttia. Ei pelkkää korrelaatiosta tehtyä johtopäätöstä. Kortissa on tietolähde, tiedon puute, ehdotettu vastuuyksikkö, toimintamekanismi, resurssitarve oletuksena, mitattava seuranta ja oletettu vaikutushaarukka (selvästi skenaario, ei kausaalinen ennuste).

**Käyttäjän 120 sekunnin matka:** avaa aluekartta → valitse esimerkiksi seulontaan osallistuminen tai hoitoonpääsyn viive → näe muutos ja verrokkialue ikä- ja aluevakioinnilla → avaa *miksi tähän ei voi suoraan verrata* → valitse yksi ehdotettu työlistamuutos/referral pathway -interventio → luo nimetty, lähteistetty kokeilukortti ja 90 päivän seuranta. Asiantuntija hyväksyy aina suosituksen.

**Data ja mallit:** Suomen Syöpärekisterin valtakunnalliset/alueelliset tilastot, THL:n avoimet alueindikaattorit ja kansallinen syöpästrategia 2026–2035. Strategian tavoite 3 (yhdenvertainen ja vaikuttava hoito, mm. hoitoon pääsy) sekä alueelliset ja sosioekonomiset erot näkyviin. Erota seulonnat, lähetteet, diagnoosi ja hoidon aloitus sekä potilas- vs järjestelmäviiveet. Käytä lähdetaulukkoa (julkaisuvuosi, alue, ikävakiointi, puuttuva/epäluotettava havainto, käyttöehdot). Merkitse erikseen, kun julkinen data **ei pysty paikallistamaan** polun vaihetta. Älä keksi potilastason viivetietoa, eikä synteettisillä esimerkeillä voi todistaa todellista alue-eriarvoisuutta.

**MVP 0–24 h:** (A) lähdelinkitetty aggregaatti-CSV/parquet importer ja tyypitetty skeema, (B) erojen visualisointi + epävarmuus/puuttuvuus, (C) kolme ennalta määriteltyä toimintakorttia, joilla hyväksyntä, toteuttaja ja mittari, (D) kaksi minuuttia kestävä synteettinen demo, jossa todellisen tilaston ja skenaarion raja on näkyvä. Jos julkinen lisenssi/datasetti ei valmistu, demo pysyy `SYNTHETIC_EXAMPLE`-tilassa.

**Milestone 30 päivää:** alueiden ja syöpätyyppien vertailukelpoinen mittaristo, asiantuntijoiden hyväksymä päätöslogiikka, pidemmän aikajanan toimet, muutosten auditointi; automaattinen datan tuoreuden tarkistus. **90 päivää:** hyvinvointialueen tutkimus/pilottikumppani ja lukittu mittarisopimus, tavoitearvojen seuranta, interventiokorttien hyväksyntäkierto, kausaaliväitteiden erillinen tieteellinen arviointi.

**Vähimmäishyväksyntä:** (1) jokaiselle näkymän numeeriselle väitteelle tarkka lähde ja menetelmä; (2) vähintään yksi Goal 3 -mittari, johon kaksi konkreettista toteuttajallista suositusta; (3) puuttuva/eritahtinen data ei tuota täsmällistä näennäisvertailua; (4) asiantuntija pystyy selittämään päätöskortin alle kahdessa minuutissa. **Baseline:** pelkkä alueellinen kartta, joka ei ehdota toteuttamiskelpoista tointa. **Ei saa väittää:** kliininen päätösapu, alueellisen eroavaisuuden todistettu syy, potilaskohtainen arvio tai todistettu vaikuttavuus.

**Tällä hetkellä ainoa seuraava todellinen riippuvuus:** luvallisen aggregaattiaineiston ja Goal 3 -mittarin lataus/viittaus sekä omistettu `solutions/astrazeneca-care-equity/**`-lähde. Omistaja `astrazeneca`; tuotepolun ulkopuoliset rekisterit suojattu.

## 4. LINJA 2 — Rokoko: MotionBridge Studio

### 4.1 Ihminen opettamassa robotille toistettavan taidon
**Kenelle:** robotiikan tutkija, laboratorio, robottikäden integroija. **Arvolupaus:** “Opeta robotti liikkeellä turvallisemmin kuin skriptillä. Näe joka ikinen liikkeen muunnos ja pysty toistamaan opetus myöhemmin.” Tärkeä ero tavalliseen VR-teleoperaatiodemoihin: kerrasta *dataa*, ei vain hetkellinen ohjaus.

**Käyttäjämatka:** valitse lähde (Rokoko Smartgloves live **tai** selvästi merkitty tallenne) → kalibroi ihmisen/robotin koordinaatisto ja käsimalli → näe digital twin + käsien liikeradat → vedä virtuaalinen turvakuori ja nopeusrajat → tee esimerkiksi herkän kappaleen asettelu → katso liikkeen ja robotin erotus, pudotukset ja staleness → hyväksy episodin vienti simulaatio-opetukseen → tee toisto ja vertaa gamepad-baselineen.

**Teknologia:** Rokoko Device SDK:n RCSP-komennot ja RGMP-binaarivirta, sensorin kvaternionit/positiot; virallinen ROS 2 -silta ja Isaac Lab -integraatio soveltuvuuden mukaan. Dokumentoitu Smartgloves-data jopa 83 Hz, Smartsuit jopa 200 Hz, mutta operaation todellinen motion→command→robot-viive mitataan laitekohtaisesti. SDK:n käyttö tarvitsee erillisen Rokoko ID:n ja sponsorin hyväksynnän/lisenssin; demo-CSV (161 saraketta, duplikaattiotsikoita) EI todista live-SDK:ta. Yhteiskellon kokeellista epoch-leimausta ei saa sekoittaa vahvistettuun kamerasynkronointiin. Käytä sisäistä monotonista kelloa ja mittaa per-laite offset/jitter.

**Kova tekninen sisältö:** target-frame-kalibraatio (kädestä robottikädeksi), retargeting-IK/käsirajoitukset, sormisynkronointi, EMA/jitter-suodatus, dropout-halt, ikääntyneiden pakettien kieltäminen, rajattu nopeus ja liikealue, turvahälytys; operaattorin omistama oikea hätäpysäytys. Tallenna liike raakadatana, normalisoituna lähteenä ja robotin toteutuneena palautteena erillisinä kenttinä. Fysikaalisia kontakteja ei päätellä ainoastaan IMU:sta.

**MVP 0–24 h:** sample-CSV:stä yksiköt/sarakkeiden identiteetit säilyttävä parseri → 3D-virtuaalikäsi simulaatiossa → alue-/nopeusrajojen näkyvä kiinniotto → *teach & replay* -jakso ⇒ käytettävä episode-receipt. Live vain jos lisenssi, laite ja tarkoitettu käyttöympäristö todellisuudessa löytyvät. **30 päivää:** ROS 2 -retargeter, Isaac Lab 2.3 -polku, automatisoitu omien demoepisodien versiointi; pienempiä robotteja varten erilliset adapterit. **90 päivää:** kaupunkilaboratorioille/pienille robotiikkatehtaalle lisenssitarkistettu paketoitu studio, käyttöoikeusperusteinen opetusdatavarasto, käsin→autonomiseksi siirtymisen laadunmittaus.

**Vähimmäishyväksyntä:** (1) dokumentoitu välimuistidatan/toistodatan lähde-SHA ja säilytetyt rinnakkaisotsikot; (2) 100 % ennalta määritellyistä `stale packet`, liikeraja, dropout ja stop -tapauksista turvallisesti pysäyttää; (3) mittaa p50/p95 end-to-end sensor→sim-aktuaattoriviive ja onnistunut toisto *todellisessa* ympäristössä tai merkitsee simulaatioksi; (4) baseline-gamepadiin verrattu tehtäväsuoritus ja aika. **Ei saa väittää:** Rokoko SDK yhdistetty, oikea käsine/Unitree käytetty, simulaatioviive sama kuin rauta tai valmiit emotionaaliset/haptiset palautteet.

**Seuraava riippuvuus:** sample-paketin tarkka käyttöoikeus ja tiedostohajautus, Rokoko SDK -lisenssin ja lainalaitteen todellinen tila. Omistaja `rokoko`, oma `solutions/rokoko-motionbridge/**`; Aalto-jako vain sopimuksen kautta.

## 5. LINJA 3 — Aalto Humanoid: Humanoid Skill Engine

### 5.1 Robotille oikea tehtävä, ei videolle muistettu temppu
**Kenelle:** Unitree G1:n robotiikkalaboratorio ja jatkossa manipulaatiojärjestelmän integroija. Haasteen täsmällinen sopimus: G1, kaksi 7-DoF-kättä + Dex3, 3–5 erimuotoista värikästä kappaletta, kolme sijainniltaan erotettavaa oranssia laatikkoa, jopa ohjeella muutettu värikartoitus, kaksi minuuttia, pään RGBD + rannekamerat + nivelet + tekstiohje, 30 Hz:n target-joint-vektorit. Turvarajat ja varsinainen fyysinen aktuaatio ovat Aallon runnerin vastuulla.

**Kärki:** *instruction-conditioned manipulation with uncertainty-aware recovery*: kielen ohjeesta tyyppitarkistettu lajittelutaulu, 3D-havainto erottelee kappaleen muodon, asennon ja epävarmuuden, tartuntapisteen/otteen ehdotus, turvavalidoitu IK/trajectory, visuaalinen tuloksen tarkistus sekä rajattu toinen yritys. Valitse baselineksi yksinkertaisempi klassinen putki ennen kalliita VLA-painoja; opittu malli saa korvata osavaiheen vasta kun held-out-mittari paranee.

**Työpaketit:** H1: pinnaa kilpailun `participants/`-rajapinta, policy-serverympäristö ja proto-käskyt; toteuta heartbeat/ajastin ja nopeus/tilarajojen kieltäytyminen. H2: 3D-perception + kappaleiden paikannus ja väriluokka kalibroidussa maailmassa, kamera→robottibase-muunnos. H3: tekstiohjeen kielivarianttien jäsennys sekä yksiselitteinen väri→box-position; kaikki epäselvät ohjeet kieltäytyvät. H4: turvallinen tarttuminen ja asettaminen + epäonnistumisen havainto. H5: sponsorin sim + vähintään kaksi itsenäistä holdout-siementä, mukaan viive, keskeytykset, collisions ja perturbations. H6 valinnainen imitaatio-oppiminen / Rokoko-data, vain lähteistettynä.

**Tämänhetkinen reaalitieto:** 14.11. julkaistu ensimmäinen `zupermiez/g1_pick_cube` LeRobot v3 -erä: 20 episodia, 11 720 ruutua, kolme kameraa, 28D state/action, 30 fps; sponsorin mukaan osa demonstraatioista suboptimaalisia. Tutkimusdatasetti on pieni, ei todista yleistämistä. RTX-renderöivä Isaac-simulaatio vaatii sopivan RTX-grafiikkasuorittimen (>=24 Gt -suositus), A100/H100 ei yksin renderöi vaadittua raytracing-sceneä; Verdan GPU käytettävissä vain jos jo valtuutettu ja laskutus/raja todettu. `aalto sim`, `aalto baseline`, `aalto eval --policy ws://localhost:8000` ovat dokumentoituja *ajettavia komentoja*, eivät tehtyjä ajoja tässä suunnitelmassa.

**MVP 0–24 h:** policy-server + tekstiohjeen tulkinta + deterministinen baseline + oikeita dataformaatteja lukevat fixture-testit. Jos ajokelpoinen RTX-simulaattori on vahvistettu, vähintään yksi todellinen `aalto eval` ja pysäytysrajojen loki. Muussa tapauksessa ei sim-/robottilaatusertifikaattia. **30 päivää:** monen ohjeen, eri kappalekulmien ja käden rajojen robusti kalibroitu manipulaatiopino; data-replay. **90 päivää:** pienidatainen taitokirjasto, epävarmuuden kalibrointi ja adaptointi uusille tarttujille; fyysiset mittaukset operaattorivalvonnassa.

**Vähimmäishyväksyntä:** (1) sponsorin policy-rajapinta pinattuna ja ≥27 hyödyllistä turvallista käskyä/s aidossa simulator-runissa; (2) ei turvapysäytyksiä ennalta määritellyissä kiellettyjen jointtikäskyjen tapauksissa, vaan ajallinen turvallinen kieltäytyminen; (3) uusille värikartoitusohjeille, siemenille ja kappaleasennoille selvä onnistumis-% ja 2 min -aikaraja sekä vertailu sponsorin baselineen; (4) erillinen reaalihardware-kuitti vasta kilpailun turvallisuusfiltterin kautta. **Ei saa väittää:** oikea G1-koe, “yleinen robottiäly”, VLA-koulutus tai Verda-ajo ilman todistetta.

**Seuraava riippuvuus:** vahvistettu sponsorin repo-/datasetti-SHA ja policy-serverin oikea Input/Output contract, sitten luvallisen RTX-simulaattorin käynnistys. Omistaja `aalto-university` (M320-työkaista), oma `solutions/aalto-humanoid/**` — erillinen saman sponsorin M343-työkaistasta.

## 6. LINJA 4 — Aalto Beyond the Clinic: Recovery Compass

### 6.1 Ihmiselle parempi arki ilman valheellista lääketieteellistä lupausta
**Kenelle:** masennuksen TMS-hoidon jälkeen arjessaan vointia seuraava käyttäjä, myöhemmin suostumuksen kautta tukihenkilö tai hoitaja. **Arvo:** “Turvallinen, yksityinen, mielekäs päivittäinen tukityökalu, joka keventää arkea ja kertoo mitä käyttäjä itse koki hyödylliseksi.” Tämä EI ole TMS:n korvike, masennuksen diagnostiikkamalli, lääkehoito tai huomaamaton kriisiseuranta.

**Kärki:** *personal adaptive experience, evidence not diagnosis*: 20–30 sekunnin valinnainen kuormittavuus-/mieliala-/uni-check-in, päivän valinta (musiikki, lyhyt kävely, hengähdys, yhteydenotto), omalla luvalla suppea tila- ja palautehistoria, viikon lopuksi “mikä toimi minulle ja mikä jäi kokeilematta” ilman kliinisen vaikutuksen arvausta. Valinnainen lähipiiri-/hoitajan näkyvyys erillisellä nimenomaisella suostumuksella ja pois kytkettävällä jakamisella. Sensorit eivät ole pakollisia; ei ääni-, kasvo- tai EEG-jatkuvakeruuta oletuksena.

**Omatoimisuuden periaatteet:** käyttäjä voi ohittaa kaikki ehdotukset, tyhjentää paikallisen historian, katsoa miksi ehdotus syntyi, asettaa hiljaiset ajat, pysäyttää ilmoitukset ja aina valita tavallisen tuen. Riskitekstit tarjoavat paikalliset, ajantasaisesti varmennetut yhteystiedot ja ohjauksen ihmisen apuun; algoritmi ei tee diagnoosia tai automaattista lääketieteellistä päätöstä. Alaikäisiin/kolmansiin osapuoliin ei kosketa tämän tuotteen ensimmäisessä vaiheessa.

**Tutkimusraja:** OpenNeuro `ds003478` on lepotilan EEG-aineisto korkealla/matalalla BDI-pisteytyksellä valikoidusta nuoresta kohortista, ei näyttöä TMS:n jälkeisen ylläpitohoidon tehokkuudesta eikä kotona mitattavan masennuksen relapsin orakkeli. Sitä voidaan käyttää tutkimusmenetelmien demonstratiiviseen datalukijaan ja datavuodon torjuntaan, **ei** väitteeseen masennuksen ennustamisesta tai yksilön hoidosta. Ilman eettistä/hoitotutkimuksen hyväksyntää mittaamme UX:ää ja turvallisuutta, emme kliinistä vaikuttavuutta.

**MVP 0–24 h:** synteettinen saavutettava mobiili/web-virta: onboarding + suostumus → valinnainen check-in → yksi itse valittu toiminta → palaute/ohita → jakamisen katkaisu → paikallisen tiedon poisto. Ei todellisten käyttäjien terveystietoa; sisältövalinnat heuristisia ja läpinäkyviä. **30 päivää:** opt-in n-of-1 -vertailu käyttäjän itsensä arvioimasta viihtyvyydestä ja kuormituksesta, esteettömyys ja ilmoitusten hiljaisuus; asianmukainen tietosuojakartoitus. **90 päivää:** oikeiden kliinikkojen ja kohderyhmän valvottu yhteiskehittäminen, protokolla mahdolliselle tutkimukselle, suostumuksen säilytys, auditointi ja riskinarviointi. Lääkinnällisen laitteen sääntelyluokitus arvioidaan ennen hoitoväitteitä.

**Vähimmäishyväksyntä:** (1) kaikki henkilökohtaiset syötteet ovat valinnaisia ja käsittely-/jako-/poistopolut testattavissa; (2) mikään käyttöliittymän väite ei esitä kliinistä riskiprosenttia, diagnoosia tai todistettua TMS-tehoa; (3) käyttäjä saa selkeän syyn ja voi kieltäytyä joka vaiheessa; (4) simuloitu riskitilanne ohjaa vakautettuun ihmisavun polkuun. **Baseline:** staattinen omahoitopäiväkirja, ei valheellisia biomarkkerilupauksia. **Ei saa väittää:** lääkinnällinen teho, relapse risk score, jatkuva kliininen valvonta tai loppukäyttäjätestaus.

**Seuraava riippuvuus:** matalariskisen käyttäjätarinan ja suostumus-/poistokäyttäytymisen hyväksytty rajaus; pidä `solutions/aalto-recovery-compass/**` ja M343 täysin erillään G1-policystä.

## 7. LINJA 5 — Arduino: Green Edge OS

### 7.1 Aidosti paikallinen hyöty asunnossa, luokassa tai yhteiskäyttötilassa
**Kenelle:** pienen työtilan/taloyhtiön ylläpitäjä, koulun huoltotiimi, asukas. **Kärki:** “Huomaa, kun lämpö-/mukavuusongelma ja turha energiankäyttö tapahtuvat yhtä aikaa, ja ehdota konkreettista vähäkulutuksista toimintaa *suoraan laitteessa* ilman kameran kuvaa pilveen.”

**Ensivertikaali:** *Microclimate Coach*: Modulino Thermo-anturit + nuppi käyttäjän mukavuusasetukselle + buzzer/merkkivalo ilmoitukseen; UNO Q:n MPU lukee pienen paikallisen mallin, MCU huolehtii deterministisestä anturisilmukasta ja ilmoitusulostulosta. Jos kamera löytyy, vain paikallinen anonyymi läsnäolotapahtuma (on-device) — ei ruutujen tallennusta tai henkilöiden tunnistusta. Lopputulos on suositus tai turvallinen pienitehoinen indikaattori, **ei** ilman erillistä laitteisto-/sähköturvahyväksyntää kiinteistön lämmitys- tai ilmanvaihto-ohjaus.

**Teknologia:** Arduino UNO Q:n Linux-Qualcomm QRB2210 ja Zephyr-STM32U585 toimivat rinnakkain. App Lab -Pythonissa `Bridge.call`, MCU:ssa `Arduino_RouterBridge.h`, `Bridge.begin()` ja `Bridge.provide()`, vaihtoehtoisesti arduino-router MessagePack RPC. Synteettisillä lämpö-/järkeilytapauksilla pääsee liikkeelle, mutta teknologiahaasteen pisteet edellyttävät oikeaa UNO Q -ajoa; tavallinen Node-demo ei riitä.

**Vaikuttava demo:** fyysinen laite saa huoneen lämpötilan ja käyttäjän toiveen, huomaa nousevan lämpötilan ja luo “nyt kannattaa tuulettaa” -ehdotuksen; käyttäjä kääntää nuppia, päätös vaihtuu välittömästi; verkkoyhteys katkaistaan ja päätös jatkuu paikallisesti. Näytä anturin aikaleimat, mallin kesto, MCU-vastauksen kuitti, päätöksen vaikutus *arvioituna* ja nimenomaan miksi kameradata ei poistu laitteelta.

**MVP 0–24 h:** App Lab -sovellus, UNO Q -yhteensopiva ohjelma, todellinen Thermo/Buzzer/Knob I/O vain jos laite löytyi; pieni kontekstiluokitin/poikkeamailmaisin, kaksi ohjattua fyysistä tilannetta ja netti-poikki-testi. **30 päivää:** korkealaatuinen työtilakäyttöliittymä, sensorikalibrointi, sähköisen energiankäytön mittaus erillisellä luvallisella mittarilla, joustava offline-päivitys. **90 päivää:** usean laitteen Edge OS ja käytönhallinta, mittarin todistama energiansäästö vs baseline, yritys-/kiinteistöpilotti.

**Vähimmäishyväksyntä:** (1) `UNO Q`-laitteen todellinen tunniste, firmware/App Lab -versio ja oikea anturi→malli→MCU→ulostulo-kuitti; (2) irrotettu verkko ei estä paikallista toimintaa ja virhe johtaa turvalliseen neutraaliin tilaan; (3) malli todella ajetaan paikallisella laitteella (ei pelkällä Macilla); (4) ympäristöhyöty osoitetaan energiankulutuksen mittauksella tai merkitään eksplisiittisesti hypoteesiksi. **Ei saa väittää:** todelliset säästöt ilman mittaria, UNO Q -ajo pelkällä lähdekoodilla, sallittu rakennusautomaatio tai valmiit kustannushyödyt.

**Seuraava riippuvuus:** tarkista lainalaitteen saatavuus 5. kerroksen Hardware Labista ja varaa luvallinen sensoripaketti; mikäli fyysinen laite ei ole käytettävissä, toteuta rinnalla selkeä `SIMULATED_MCU`-polku ilman hardware-claimia. `solutions/arduino-green-edge/**`, omistaja `arduino`.

## 8. LINJA 6 — Intel × Ignite: Inspect-to-Action Cell

### 8.1 Kaikesta liikkeestä laatutodiste
**Kenelle:** pienen valmistuslinjan laatuinsinööri tai robottisolun operaattori. **Arvo:** “Opeta solua tunnistamaan viallinen kappale ja lajittelemaan se — niin että insinööri näkee *miksi* kukin kappale meni tiettyyn kulhoon.” Tämä yhdistää tarkkuuden ja fyysisen onnistumisen paremmin kuin pelkkä näyttävä VLA-videoleike.

**Tarkka sponsoriympäristö:** SO-101 leader + follower -robotit, ylä- ja tarkastuskamera (ainakin yksi RealSense D415), Duplo-kappaleet ja kolme kulhoa; Physical AI Studio demonstratio/VLA, Anomalib-poikkeamadetektori, OpenVINO-inferenssi Core Ultra Series 3 CPU/GPU/NPU:lla. **Arviointiristiriita:** virallinen pääbrief 30/30/20/20, sponsorin GitHub-ohje ja PDF sisältävät erilaisia 25/25/20/20/10 ja 25/20/20/20/10/5 -jakoja. Säilytä molemmat lähteet, älä valitse yhtä “uusimmaksi” ilman kumppanin vahvistusta.

**Tuoteidea:** *Defect Passport* — jokaiselle kappaleelle kuvallinen lähdemerkintä, vikaruutu/score, luokan epävarmuus, policy- ja Anomalib-versio, robotin poiminta-/näyttö-/lajitteluketju, kulhon havainnon vahvistus ja mahdollinen uudelleentartunta. Korjaa epäonnistumiset ensin baselinella: suljettu havainto→toiminta→tarkistus-silmukka; vasta sitten taustalla koulutettu VLA opastaa poimintastrategiaa. Käyttäjä näkee STOP/recovery-sekvenssin eikä saa piilotettuja automaattisia sivuvaikutuksia.

**Arkkitehtuuri:** I1 dataset handler (run ID, train/holdout, defections, kamerageometria), I2 teleop-jakso leader-armilta, I3 Anomalib/patchcore-vikaluokitin ja aluekartta, I4 Physical AI Studio policy + varhaisen vaiheen klassinen johtolanka, I5 OpenVINO eksportti/kvantisointi vain yhteensopivalla mallilla, I6 laitteella `CPU/GPU/NPU` kullekin aidosti tuetulle osamallille ja mittaus, I7 pysäytys/timeout/pudotus/uudelleenkuvaus, I8 auditointi jokaisesta rivistä. **Ei** yleistä LLM-agenttia suoraan robottiin. Merkittävästä dropoutista tai epävarmuudesta STOP/human review.

**MVP 0–24 h:** pinnaa `junction2026` sponsorikoodin versio, rakenna kaksi polkua: (a) varma paikallinen Anomalib + oikeanmuotoinen inspection-to-sort-simulaatio, (b) jos asemavaraus vahvistuu, todellinen leader-demo→follower cycle→yksi oikea lajittelu ja video + metriikat. Priorisoi läpimenevä turvallinen 1 sykli ennen 50 demoepisonin koulutusajoa. **30 päivää:** kattava virheluokkaholdout, aktiivinen virhekohtainen opetus ja edge-profilointi. **90 päivää:** laitteen/robotin vaihtoon soveltuvat adapterit, auditoitava laadunohjaus, reaalimaailman käyttöönoton turvallisuus- ja ylläpitosuunnitelma.

**Vähimmäishyväksyntä:** (1) todellinen asema- ja malliversio sekä mallitiedostojen SHA, epäonnistumislogit; (2) fyysisessä 3-kulhoisessa lajittelussa oikea määrä, vika-alue ja pohjakamera/kulho-vahvistus; (3) p50/p95 sykli- ja inference-aika, lämmön/tehon mittaustapa ja vertailu baselineen; (4) vähintään yksi sokkosiemen-/uusi vikatyyppi ilman harjoitusvuotoa ja epävarmoissa STOP; (5) CPU/GPU/NPU-laiteväite perustuu todelliseen device-queryyn ja kunkin käyttämän mallin toteutuneeseen ajokuitiin. **Ei saa väittää:** Intel-työasema liitetty, NPU käytössä, cloud-finetune tai robottisolu autonominen ilman videotodistetta ja logia.

**Seuraava riippuvuus:** sponsorin `junction2026`-repo/stack-version ja on-site robotin varauksen reaalinen todentaminen. `solutions/intel-physical-ai-cell/**`, omistaja `ignite-next` ja `intel` jakavat **yhden** `partnerEvidenceKey=ignite-next-and-intel`, ei kahta kirjoittajaa.

## 9. Kuuden linjan yhteinen kehitysaikataulu ja omistajuus

### 9.1 Junctionin loppuaika: hallittu toimitus, ei lupausta kuudesta valmiista tuotteesta

**Kriittinen prioriteetti:** J26 FINAL L9 Issue #77 on erillinen aikakriittinen toimitus ja oma controller 15.11. klo 10.00 asti. Tämä kuuden tuotteen ohjelma ei saa keskeyttää, kopioida, ilmoittaa valmistuneeksi tai julkaista sen työtä. CRACI-työjonon 15.11. klo 19.00 Helsinki -katkaisu ja erillinen 1000 €:n olemassa olevan krediitin katto pysyvät. Uusi GPU-laskutus, uusi salaisuus, sponsorijulkaisu, repo-merge tai hardware-aktivointi eivät sisälly suunnittelun automaattisiin oikeuksiin.

**Portit työn alla (n. 0–24 h, eivät lupaus mahtua yhteen yöhön):**

| Vaihe | Kestoarvio työpaketille | Todellinen toimitus | Estävä riippuvuus | Portista läpi, kun |
|---|---|---|---|---|
| G0 Faktat | 1–2 h per linja | virallinen brief, partnerKey, tarkka source/data/license, omistaja, hyötyjuttu | lähde/omistajuus | yksi nimetty kirjallinen slice |
| G1 Ajettava ydinketju | 3–6 h per linja | synteettinen tai julkaistu luvallinen input → näkyvä toimiva output + STOP | lähdekoodin omistaja | toistettava CLI/UI-reitti, virheet hallittu |
| G2 Näyttävä tarina | 2–4 h per linja | kaksi minuutin käyttäjäreittiä, saavutettava responsiivinen UI, vertailu baselineen | G1 | käyttäjän päätös ja syy näkyvät |
| G3 Oikea kumppani | vaihteleva, usein 1–3 päivää | virallinen SDK/API/sim/rauta todella ajettu | lupa, laite, GPU/verkko | lähde SHA + hardware/run-ID + oikea mittari |
| G4 Kilpailupaketti | controller-ohjattu | erilliset hyväksyntälinkit ja live-demo | G2/G3 ja oikeudet | kilpailun oman release-controllerin hyväksyntä |

**Käynnistysjärjestys erillisten omistajien saatavuuden mukaan:** lähde- ja laiteyhteyden tarkistukset **Intel, Arduino, Rokoko, Aalto Humanoid** välittömästi — laitteistolle ei voi tehdä pätevää viimehetken korviketta. Rinnalla **AstraZeneca ja Beyond the Clinic** voivat saada nopeasti todellisen, vähän ulkoisista laitteista riippuvan päätöksen/UX:n. Jos hardware/RTX puuttuu, jatketaan kyseisen linjan algoritmi-/datasopimusta, ei käytetä kaikkia tunteja oletetun GPU:n odotukseen. Intel+Arduino ovat sopivin fyysinen kilpailudemo, AstraZeneca vahvin riippumaton arvolupaus; Aalto ja Rokoko tuottavat pitkän aikavälin robotiikkakykyä. Lopullinen voittopotentiaali on ehdollinen, ei tulosväite.

### 9.2 Yksi writer per päätuote, yksi integroija

| Omistettu polku | Kirjoittaja | Erillinen riskikatselmointi | Yhteinen rajapintariippuvuus |
|---|---|---|---|
| `solutions/astrazeneca-care-equity/**` | `astrazeneca` | epidemiologia / virheelliset tulkinnat | `decision-evidence.v1` |
| `solutions/rokoko-motionbridge/**` | `rokoko` | sensorigeometria + turvallinen stop | `observation.v1`, `episode-receipt.v1` |
| `solutions/aalto-humanoid/**` | `aalto-university/M320` | nopeus/rajoitus/pudotus | `action-proposal.v1`, `episode-receipt.v1` |
| `solutions/aalto-recovery-compass/**` | **sama yksi `aalto-university`-kirjoittaja** kuin M320:ssä; kaksi erillistä työviipaletta **peräkkäin**, erilliset tarkastajat | suostumus/terveyssisältö | `decision-evidence.v1` vain skeemana |
| `solutions/arduino-green-edge/**` | `arduino` | fyysinen sähköturva/MCU/edge-data | `observation.v1` rajattuna |
| `solutions/intel-physical-ai-cell/**` | `ignite-next` / `intel` **yksi writer** | robottisolun turvallisuus + vika-FPR | `episode-receipt.v1` |
| shared root/agents/manifests | nykyinen root-integraattori | source + versioning | muutos vain hyväksytyn rajapintatarpeen kautta |

**Yhden kirjoittajan lukko:** M320 ja M343 ovat erilliset kilpailutuotteet, mutta Aalto-yhtiörajauksen writer-lease on yhteinen. Älä käynnistä niihin kahta samanaikaista lähdekoodikirjoittajaa ilman nykyisen omistajan erikseen todennettua siirtoa/rajausta.

**Prosessi:** (1) tarkista nykyinen authenticated main, PR HEAD ja epäpuhtaat worktreet; (2) lukitse yksi tuotepolku/branch, toinen kirjoittaja ei koske siihen; (3) toteuta yksi toimiva kyvykkyys, merkitse fixture-vs-real; (4) tee vain riskin mukainen tarkistus, säilytä aidot epäonnistumiset; (5) commit ja push draft PR, remote HEAD -verifiointi; (6) anna nykyiselle **Portfolio PR Recovery** -integraattorille tarkka lähde, este ja seuraava riippuvuus. Ei suoraa mainia, mergeä, tuotantodeployta tai julkaisemista tässä dokumenttityössä.

### 9.3 Kustannukset ja laitteet

- Ilmaiset/synteettiset paikalliset testit ensin. CRACI:lla tehdään **vain** jo olemassa olevan ajokelpoisen tuotteen todellinen, kattamaton portable/browser/fixture-ajo, nykyinen aika- ja euromääräinen vartiointi. Siellä ei ajeta Aalto Isaac RTX/G1-robotin oikeita kokeita eikä väitetä Mac-simulaatiota verifioiduksi GPU-ajoksi.
- Verda ja muut GPU-ympäristöt: tarkista nykyinen sessio, käytettävissä oleva krediitti, oikeus ja resurssit ennen yksittäistä työtä; älä avaa laskutettavaa GPU:ta tai välitä avainta tähän ohjelmaan ilman todellista auktoriteettia. Aallon simulator on RTX-kyvykkyyden vaatimus.
- Intel- ja Arduino-asemat ovat tapahtuman rajattua hardwarea: kenen hallussa, fyysinen slot, verkko, mallin asennus ja lokin omistus ennen live-väitettä. Smartgloves vaatii Rokokon hyväksytyn SDK-lisenssin.
- Jokainen sponsoridatasetti merkitään lisenssin, anonymisoinnin, julkisuusasteen ja kilpailun kelpoisuusehtojen mukaan; PR-koodia ei automaattisesti julkaista avoimena ilman release/immateriaalioikeuskontrollia.

## 10. Mittaus, nopea eval ja potentiaaliset pahimmat epäonnistumiset

**Yhteinen taulukko, muttei yksi yhteinen “AI score”:**

| Tuote | Ensisijainen metriikka | Vastamitta / guardrail | Vertailu |
|---|---|---|---|
| AstraZeneca | lähteeseen sidottujen alue×indikaattori-suositusten osuus, hyväksytty toimi | puuttuva data, sekoittavat tekijät, epätarkka kausaaliväite | kartta ilman toimenpidettä |
| Rokoko | tehtäväsuoritus, sensor→robot p95, turvallisen pysäytyksen kattavuus | dropout/jitter/rajojen ylitys, väärä frame | gamepad/teleop ilman laatukuitteja |
| Aalto Humanoid | holdout % oikein kahdessa minuutissa, hyödylliset Hz | sim-kolarit, epäonnistuneet graspit, ohjemuutos | virallinen klassinen baseline |
| Recovery Compass | itse aloitettujen tukitoimien valmistuminen, käyttökuormitus, opt-out | ei diagnoosiväitteitä, tietosuojan rikkomiset, hälytysväsymys | staattinen oma päiväkirja |
| Arduino | laitteen oma päätös latency + offline-toiminta, mitattu energiamuutos | väärä paikallaolopäätelmä, turvaton aktuointi | kiinteä sensori-/termostaattisääntö |
| Intel | autonominen oikea kulho %, cycle time, CPU/GPU/NPU-perf | vika-FNR/FPR, ohitetut stoppit, train/holdout-vuoto | klassinen poiminta + peruskynnys |

**P0-nostot:** epävarma robottiohjaus ei saa johtaa itsenäiseen laitteeseen; masennustukea ei saa naamioida relapsin hoitoväitteiksi; AstraZeneca-aluevertailusta ei saa tehdä potilaskohtaista kausaalisuutta; sponsorin SDK/rauta ei ole käytössä vain dokumentaation perusteella. **P1:** cross-device ajan ja koordinaatiston virhe, puuttuvan sensorin “zero”-tulkinta, sim-to-real leakage, puuttuva Intel NPU device proof. **P2:** kauniit visuaalit ilman hyötyä, kaupallinen ylihinnoittelu ilman todennettua KPI:tä, liian aikainen yhteiskirjaston rakentaminen.

**Vähimmäislaadun periaate:** vain yksi todellisen virheen todentava kohdennettu testiryhmä per merkittävä riskiraja, ei kuuden linjan automaattista täyttä testisykliä joka commitille. Rauta- ja tutkimusväitteet tarvitsee niiden omat, erilliset todisteet ja tekijät.

## 11. 30/90 päivän kaupallinen eteneminen

| Tuote | 30 päivän tuotepolku | 90 päivän maksavan asiakkaan/pilotin arvohypoteesi | Mikä voisi muodostaa oikean vallihaudan |
|---|---|---|---|
| Equity Navigator | harmonisoitu alueaineisto + hyväksytty interventiokortisto | alueellisen hoitoketjun kehityspilotti, tilattu vaikutusseuranta | auditoitu alueiden toimenpidehistorian/vaikutusarvioinnin laatu |
| MotionBridge Studio | useampi robottiadapteri + toistettava episodejaosto | labran opetusdatan laadun ja koulutuskulujen pienentyminen | turvallinen retargeter + datan provenance, ei pelkkä UI |
| Humanoid Skill Engine | vähädatainen usean otteen/ohjeen testaustaso | robottivaihdon läpäisevä manipulaatiopolitiikan evaluointi | mitattu failure recovery ja robottiluokkien robustius |
| Recovery Compass | turvallinen matalan kuormituksen mobiilirutiini | tutkimuskumppanin käytettävyys- ja eettinen pilotti | käyttöhalukkuuden ja suostumuksen osoitettu hyvä toimivuus, EI kliininen väite |
| Green Edge OS | todellinen paikallinen sensori ja mittari, offline-ohjaus | ensimmäinen taloyhtiön/tilan säästö- tai mukavuusmittaus | asennuksen helppous, yksityisyyden suoja, mitattu ROI |
| Inspect-to-Action Cell | todellinen robotin syklikanta ja vikadatan holdout | tuotantopilotti, jossa vähenevät virheellinen lajittelu ja operaattorin minuutit | jäljitettävyys + nopeus/virheiden hallinta asiakkaan geometriassa |

Kaupallinen vaihe alkaa todellisesta käyttäjätarpeesta, lisenssistä ja toimivasta datakanavasta, ei siitä että kaikki kuusi jakavat agenttikehyksen. Tavoite on ensin tehdä yksi premium-polku kustakin, vasta sitten kytkeä toisiinsa todistetut moduulit.

## 12. Riippumaton arviointi ja muutospäätökset

**Fable 5.2 -arviointi VALMIS:** riippumaton, työkaluton Anthropic Claude Code -ajon (`claude-fable-5-2`) lähdekoodiin koskematon katselmointi valmistui 14.11.2026: natiivi CLI palautti `subtype=success`, `is_error=false`, `stop_reason=end_turn`, 15 054 merkin suomenkielisen arvion. Tarkastuksen tekstin SHA-256 on `a5867b439890822b2ff6686559e9b12d6a79e627777afc0337c914459166d223`. Arvio ei itse selannut sponsoriportaaleja, testannut koodia tai vahvistanut laitteistoa; se on riippumaton tekninen kritiikki annettuja lähdetietoja vasten. Tulokset ja hyväksytyt muutokset ovat jäljempänä luvussa 14 sekä erillisessä Fable-liitteessä; omistajan MBP:llä säilyy täsmällinen alkuperäistulos.

**Reunaehdot:** yksi tuote = yksi kirjuri; root-manifestien omistajuutta ei ohiteta. L9 #77 erillinen; CRACI:n ajanjakson sulku erillisellä olemassa olevalla automaatiolla. Ei uusia salaisuuksia/tilisiirtoja, julkaisuja, tuotantodeployta eikä maksullista GPU-provisiointia tällä suunnitelmalla. Jokainen tuleva PR linkitetään Issue #80:n kyseiseen rivin tarkkaan lähde-SHA:han ja yhteen seuraavaan todelliseen riippuvuuteen.

## 13. Lähteet

**Projektin ensisijainen nykytila ja viralliset haasteet:**
- [SalesSquad/junction-pets Issue #80](https://github.com/SalesSquad/junction-pets/issues/80), [viimeisin kuuden puuttuvan listaus](https://github.com/SalesSquad/junction-pets/issues/80#issuecomment-6872525756), [päivitetty virallinen lähdekatalogi](https://github.com/SalesSquad/junction-pets/blob/main/docs/challenge-research/current-source-catalog.json).
- [AstraZeneca M344](https://hackjunction.app/participate/45/challenges/344), [Rokoko M326](https://hackjunction.app/participate/45/challenges/326), [Aalto Humanoid M320](https://hackjunction.app/participate/45/challenges/320), [Aalto Beyond Clinic M343](https://hackjunction.app/participate/45/challenges/343), [Arduino M356](https://hackjunction.app/participate/45/challenges/356), [Arduino Tech T45](https://hackjunction.app/participate/45/tech-challenges/45), [Intel M330](https://hackjunction.app/participate/45/challenges/330).
- [Junction 2026 aikataulu ja Hardware Lab](https://2026.hackjunction.com/).

**Teknologian ja aineistojen ensisijaiset lähteet:**
- [Rokoko Device SDK](https://sdk.rokoko.com/), [RCSP/RGMP](https://sdk.rokoko.com/reference/overview/), [SDK-aikakello ja RGMP-stream](https://sdk.rokoko.com/guides/streaming-data/), [Rokoko Isaac Lab 2.3](https://www.rokoko.com/insights/rokoko-sdk-now-supports-nvidia-isaac-lab).
- [Aaltonomous lähderepo](https://github.com/zupermiez/aaltonomous-humanoid), [ensimmäinen LeRobot v3 data](https://huggingface.co/datasets/zupermiez/g1_pick_cube) (käyttöoikeus ja revisio pinattava ennen ajoa).
- [Arduino UNO Q laite](https://docs.arduino.cc/hardware/uno-q/), [UNO Q käyttöopas](https://docs.arduino.cc/tutorials/uno-q/user-manual), [Arduino Router RPC](https://docs.arduino.cc/tutorials/uno-q/routerbridge-multilanguage).
- [Intel Robotics AI Suite](https://developer.robotics.intel.com/pr/40/development-stack/resources/hackathon_resources/index.html), [OpenVINO 2026](https://docs.openvino.ai/2026/about-openvino/release-notes-openvino.html), [Anomalib](https://github.com/open-edge-platform/anomalib).
- [Suomen kansallinen syöpästrategia 2026–2035](https://fican.fi/wp-content/uploads/2026/01/National_Cancer_Strategy_2026-2035_Finland.pdf), [Syöpä Suomessa 2024](https://syoparekisteri.fi/assets/themes/ssy3/factsheets/cancer_in_finland_2024.html), [OpenNeuro ds003478 -kohorttiraja](https://nemar.org/dataset/on003478).

**Lähderajoitus:** sponsorin reaalilaitteiden läsnäolo, kirjautuminen, dataoikeudet, uusin PR-tila, ja asiakkaiden pilottisopimukset on todennettava nimenomaan suoritushetkellä. Tämä roadmap ei ole todiste niiden toteutumisesta.


## 14. Fable 5.2:n riippumaton kriittinen katselmointi — hyväksytyt muutokset (14.11.2026)

**Alkuperäinen arvio:** Claude Code `claude-fable-5-2`, omistajan valtuuttama natiivi tilaus, ajettu omassa työhakemistossa ilman työkaluja, selaamista tai lähdekirjoitusta; `stop_reason=end_turn`, `is_error=false`, 15 054 merkkiä, SHA-256 `a5867b439890822b2ff6686559e9b12d6a79e627777afc0337c914459166d223`. Se ei ole tuomarin lausunto, sponsorin hyväksyntä, kliininen arvio eikä ajotesti. Erillinen sanatarkka Fable-liite säilyttää sen argumentit ja eriävät näkemykset.

### 14.1 Kaksi eri kelloa: eventtituote ja pitkäikäinen flagship

**Kilpailuikkuna:** kuuden tuotteen tekeminen valmiiksi virallisina fyysisinä/aidosti integroituneina demoina ennen 15.11.2026 aamun määräaikoja ei ole lähtötiedolla realistinen: kuusi ovat tutkimus-/helper-vaiheessa eikä yhdellekään kuudesta ole todennettua itsenäistä laiteajoa. Fable ehdottaa korkeintaan kahta rehellistä ohjelmistodemoa, yhtä laitteistosta ehdollista ja kolmea myöhemmin toteutettavaa tuotelinjaa. Tämä on kapasiteettipriorisoinnin neuvo, **ei kuuden tuotteen hylkääminen eikä lupa tehdä uusia kilpailupalautuksia**; J26 FINAL L9 #77 ja kaikki aikarajat/mergaus- ja julkaisuvaltuudet pysyvät omalla ohjaimellaan.

**30–90 päivän tuotekello:** jokaiselle kuudelle rakennetaan oma ostettavaa hyötyä tuottava käyttäjäpolku ja erikseen todennettava sponsorin todellinen integraatio. Yhteistä koodia kerätään todennetun tarpeen perusteella. Ei palkita portfolioa makettien, testiajojen tai PR-määrän mukaan.

### 14.2 Kriittiset P0/P1-portit, joiden vuoksi suunnitelmaa tarkennettiin

| Arvion riskitaso | Kriittinen havainto | Päätetty rajaus ja hyväksyntä |
|---|---|---|
| P0 | Kuusi täyttä palautusta vähällä ajalla ei ole uskottavaa. | Demon tavoite valitaan omistajien todellisten resurssien mukaan; ei kuutta kuvitteellista E2E:tä. |
| P0 | Aiempaa yksityistä Chibi/Taimi/Valmet-koodia tai sponsorin dataa ei voi olettaa Junction-palautuskelpoiseksi. | Tapahtuman kelpoisuusehdot, lisenssit ja palautusten määrä tarkistetaan nimenomaisesti; yksityistä IP:tä/SDK-binäärejä ei kopioida. |
| P0 | Yhteinen Rust-kernel varastaisi toteutusaikaa ja sekoittaisi hoidon/robotiikan luottamusrajat. | **Ei yhteistä ajoympäristöä kilpailuikkunaan.** Yksi sivu yksikkö-, kello-, kuitti- ja frame-konventioita + golden-fixturet. Saman koodin poiminta vasta todetun 2 tuotteen käytön jälkeen. |
| P0 | Aallon vaadittua RTX-simulointia/Intel-asemaa tai oikeaa laitearviota ei ole todennettu. | Edistetään offline-kontraktia; suljetun silmukan tai robotin onnistumista ei raportoida ennen oikeaa ajoa. GPU-menoa ei lisätä ilman sallittua budjettia. |
| P0 | AstraZenecan aggregaattidatasta ei seuraa kausaalinen politiikkasäästö tai eritelty potilas-/järjestelmäviive. | Toimenpidekortti näyttää lähteen, rajoitteet, ikävakioinnin, epävarmuuden ja sen, mitä **ei tiedetä**. Kaikki numerollinen vaikutus on eksplisiittinen skenaario. |
| P1 | Rokokon CSV:n 161 saraketta ja toistuvat otsikot, kellot ja 83/200Hz syötteet voivat rikkoa retargetoinnin. | Parseri säilyttää alkuperäisen sarakeposition, SLERP/kvaternion merkkijatkuvuus, molemmat kellot ja epävarmuus; turvaportti ei ekstrapoloi kadonnutta mittausta. |
| P1 | Aallon 20 suboptimaalista demonstraatioepisodia ja Intelin ristiriitaiset pisteytykset eivät tue yleistyvyys- tai pisteväitettä. | Holdout erotellaan episodi- ja esinetasolla; raportoi n+luottamusväli; Intel käyttää molemmat kilpailevat rubric-lähteet, kunnes sponsorin ratkaisu löytyy. |
| P1 | Beyond Clinic voisi huomaamatta muuttua relapsin ennustamiseksi tai potilaan valvonnaksi. | Ei EEG-datasettiin perustuvaa TMS-tehoväitettä, ei kliinistä riskipisteytystä; käyttäjä hallitsee jakonäkymää ja peruuttamista, kriisiohjeet ovat tarkistettuja, eivät generoituja. |
| P1 | Arduinon summerin hälytys ei itsessään säästä energiaa; laitteen tehonkulutus sekoittuu väitettyyn säästöön. | Mittaa ensin tarkkuus, offline-tila, laitteen kulutus, MCU-failsafe ja vasta myöhemmin havaittu **nettokWh** todellisella interventiolla. |

### 14.3 Fable-arvion paremmat tuotekärjet ja numerolliset hyväksyntäkohteet

1. **AstraZeneca:** *todistuskelpoinen toimenpidekortti*, joka **pidättyy alueiden järjestämisestä** jos ikävakiointi/luottamusväli/pienet solut ovat puutteellisia. Tavoitteena 100 % lukujen lähteistys + päivämäärä, yhden komennon toistettava julkinen dataputki ja enintään 110 sekunnin asiakasdemo. Ei kuolleisuuden kausaaliväitteitä.
2. **Rokoko:** kaupallinen **demonstraatiodatan laatuportti** ennemmin kuin pelkkä motion-avatar. Kohdistuksen, dropoutin ja joint-rajojen kuitti → kelvollinen LeRobot v3 -episodi. Tavoitteina kaikkien sponsorinäytteiden sarake-eheyden tarkistus, 200Hz offline-käsittelyn p95 ja nolla oman portin läpi hyväksyttyä rajanylitystä; oikean laiteviiveen mittaus erikseen.
3. **Aalto Humanoid:** nimi ei vielä *generalist*. Eksplisiittinen ohje→väri–laatikko-mäppäys (kuusi permutaatiota), epäselvistä pyynnöistä pidättäytyminen ja järjestäjän 30Hz target / vähintään 27Hz toteutunut kytkettyyn turvallisuussuodattimeen. Ehdotetut mittarit: p99 enintään ~33 ms kohdelaitteella ja vähintään 50 aitoa simulaatioepisodia ennen onnistumisväitettä; tavoitteet eivät ole tuloksia.
4. **Beyond Clinic:** tuotteen erottuvuus on **"näytä, mitä vastaanottaja näkisi"** ja peruttava suostumus, ei masennuksen automaattinen riskiluokitus. Tavoite kaikille jaoille suostumuskuitti, revokaatio ja kriisiavun löytyminen kahdella napautuksella; arvioi käyttäjän omia tavoitteita, älä käyttäjän maksimaalista ruutuaikaa.
5. **Arduino:** ennen kuin "OS" ansaitaan, ensimmäinen tuote **huoneen paikallinen yksityinen hukkavahti**: laite itse katkaisee havainnon pilviviennin, MCU jatkaa Linuxin kaatuessa. Mahdolliset kvalifikaatiot: F1≥0,90 vähintään 200 itse merkityllä kehyksellä, nolla ulkoista liikennettä offline-testissä, watchdog-reaktio alle 1 s ja laitteen oma energiankulutus mittarilla.
6. **Intel:** wow = **jokaisen kappaleen tarkastuspassi** (kuva, heatmap, vika-score, uudelleentarkastus/viimeinen kulho, cycle time ja *mitatut*, ei arvellut joulet). Anomalibin veto-oikeus VLA-ehdotukseen. G3-tavoite vähintään 30 peräkkäistä autonomista yritystä, oikea kulho ≥80 % + n + luottamusväli; CPU/GPU/NPU-käyttö vain aidosti mitatuilla laitteilla.

**Robottilaitteiston etenemisportit:** G0 varmennettu käyttöoikeus ja oikea hardware; G1 turvallinen offline-/kuiva-ajo; G2 rajattu hidas ajo, erillinen hätäpysäytys ja paikalla oleva valvoja; G3 kirjattu autonominen otos; G4 lähde- ja tuloskuitillinen demo. Yksikään simulaatiotesti ei sertifioi ihmisten turvallisuutta, eikä yleinen Rust-portti korvaa järjestäjän/ohjaimen alemman tason pysäytyksiä.

**Erillinen hoitoetiikka:** lääkeyhtiön sponsorietu ilmoitetaan AstraZenecan lähteissä; aluevertailu ei saa leimata väestöryhmiä. Beyond Clinic on oma suostumus- ja käyttödatasaarekkeensa ilman yhteisiä identiteettejä/robottitallenteita; keskeytys tai vähäinen käyttö ei tarkoita hoidon epäonnistumista. Hätä- tai kriisitilanteen vastaukset perustuvat hyväksyttyihin staattisiin ohjeisiin.

### 14.4 Eriävä johtopäätös — priorisointi ja ylläpito

Fable nosti tapahtumaikkunan ohjelmistoprioriteetiksi (1) **AstraZenecan**, (2) **Rokokon**, jos hyväksytty SDK tai tallenne+simulaatio on sponsoriehtojen mukaan riittävä; muuten **Beyond the Clinic**. Robotit/Arduino nousevat kilpailupolulle vain oikealla laitteella ja omistajan hyväksymän turvallisuusrutiinin läpäisseenä. Tämä on riippumattoman arvion ehdollinen ehdotus, ei Junctionin sisäänjättöpäätös eikä L9-ohjaimen muutos.

Pitkän aikavälin kolme vahvinta kaupallista kiilaa Fable-arvion mukaan: Rokokon laadukas harjoitusdata, Intelin auditoitu teollinen tarkastussolu ja AstraZenecan päivittyvä hoitoketjun toimenpideanalytiikka. Jokainen näistä vaatii todellisen sponsoridatan, ostajakäyttäjän ja saavutetun mittarin ennen liiketoimintaväitettä. Kuusi erillistä flagship-ohjelmaa säilyy; yhteisten sopimusten ylläpito ei saa olla niiden julkaisun pullonkaula.

**Tuloksen läpinäkyvyys:** Fable ei avannut uusia sponsoripages-, Discord- tai GitHub-tilejä eikä nähnyt nykyisiä tuotantokoneita. Se ei vahvistanut 90 päivän ostaja-arvoja, kliinistä vaikuttavuutta, kolmannen osapuolen laitekelpoisuutta tai sponsorin lopullisia pisteytyksiä. Nimelliset prosentit ja aikarajat yllä ovat ehdotettuja hyväksymiskriteereitä, eivät jo suoritetun testin tuloksia.
