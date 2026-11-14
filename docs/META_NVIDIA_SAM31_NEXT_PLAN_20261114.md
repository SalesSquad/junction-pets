# Meta–Chibi: SAM 3.1, NVIDIA ja nykyisen osaamisen seuraava toteutus

Päiväys: 14.11.2026. Työtunnus: META-NVIDIA-REUSE-20261114.
Tila: lähteisiin sidottu toteutussuunnitelma; seuraavan vaiheen koodia tai GPU-ajoa ei ole käynnistetty tämän suunnitelmatyön aikana.

## Päätös

Rakennetaan Chibi Continuityyn kyky havaita, mikä keskeytyneen fyysisen tehtävän ympäristössä muuttui. SAM 3.1 rajaa ja seuraa näkyviä esine-ehdokkaita, nykyinen NVIDIA Nemotron 3.5 Super VL tulkitsee tehtävälle olennaisen havainnon ja Chibin nykyinen tehtävädomain säilyttää käyttäjän vahvistaman tilan. Ensimmäinen kokonainen käyttäjätilanne ratkaistaan ennen uuden mallipalvelualustan tai hahmoanimaation rakentamista.

Tämä jatkaa [nykyistä Continuity-suunnitelmaa](CHIBI_CONTINUITY_EXECUTION_20261114.md) ja sen H1/U1/H2/I2/P1-työjakoa. Uusi [koneluettava työpakettilista](meta-execution/nvidia-next-stage.json) on suunnitelma, ei suoritettava job-konfiguraatio, resurssivaraus tai uusi työjono.

## 1. Kunnianhimoinen tavoite ja seuraava näkyvä tulos

Säilytetään aiempi 90 päivän tavoite: **3 arkista työnkulkua, 30 pilottikäyttäjää ja 300 oikeaa tehtäväjaksoa; jatkamiseen kuluva aika vähenee 35 % ja unohtuneet työvaiheet 50 % omaan lähtötasoon verrattuna.** Nämä ovat mittaamattomia tavoitteita, eivät jo saavutettuja tuloksia tai rekrytointeja. Havaitsemisen onnistuminen sisältää myös oikean epävarmuuden: järjestelmä kysyy, kun se ei voi erottaa kahta esinettä.

Pitkän aikavälin tuote on mukana kulkeva työmuisti: käyttäjän vahvistama tehtävä, esineet ja keskeytyksen syy siirtyvät lasien, puhelimen ja myöhemmän XR-harjoittelun välillä. Esineen löytäminen, tehtävän jatkaminen ja käyttäjän korjaus käyttävät samaa historiaa.

**Seuraava konkreettinen demo:** pakkaa kamera, mikrofoni ja oikea laturi. Käyttäjä vahvistaa kaksi ensimmäistä, keskeyttää ja palaa. Laturi on siirretty tai tilalle on tullut samannäköinen toinen laturi. Chibi näyttää, mihin jäätiin, nostaa olennaisen uuden havainnon ja pyytää tarvittaessa tunnistamaan laturin. Se ei kuittaa pakkausta valmiiksi mallin arvauksen perusteella.

Ensimmäinen versio käyttää yhtä rajattua kuvausjaksoa tai omaa tallennetta. Sama rajapinta liitetään oikeaan DAT-kuvauspolkuun, kun sen nykyinen laite- ja host-polku on todennettu. Mallin toimivuus videolla ja toimivuus Meta-laseilla raportoidaan erikseen.

## 2. Mitä jo löytyy ja mitä siitä otetaan

Alla olevat havainnot perustuvat luettuun lähdekoodiin. Mainitut ajot ovat aiempia, lähteisiin kirjattuja ajoja; tässä auditoinnissa ei ajettu malleja.

| Nykyinen osa | Otetaan tähän | Puuttuva sovitus |
| --- | --- | --- |
| Junctionin Nemotron VL ja Stoa→NVIDIA | Rajatut kuvasyötteet, aikarajat, tarkka malliprofiili, lähde- ja vastaussidonta sekä käyttökuitti. | Meta-kuvan ja tehtävän oma syöte-/tulosmuoto, runTaskObservation. |
| Agentsin ajettu paikallinen Super VL | Säilytetyt NVFP4-painot, vLLM-resepti, cache, rajattu käynnistys ja pysäytys. | Nykyisen varauksen saatavuuden tarkistus ja eksplisiittinen paikallinen profiili. |
| Valmet Truth Engine | Ehdokastunnistus, avoin epävarmuus ja yksi-yhteen-yhdistely. | Kuvien embedding-tuottaja ja ajallinen kalibrointi; tämä ei ole ensimmäisen demon riippuvuus. |
| Valmethack | Korjattava kohdehistoria, epäselvyys, lähderevisiot ja vanhan tuloksen hylkäys. | Kamerahavainnon ehdokasraja; ei suoraa fyysisen identiteetin varmistusta. |
| Reality Twin | Rajattu kuvausarkisto, ruutujen pudotuksen näkyvyys, puskureiden hallinta ja toistettava jakso. | Meta-/tallenneadapteri; nykyinen ARKit/LiDAR-koodi ei siirry sellaisenaan. |
| MacAssetDAM | Kuvan, rajauksen ja maskin materiaalihistoria sekä riippuvien tulosten vanheneminen. | Yksityinen host-sovitus. Materiaalitunniste ei ole fyysisen esineen tunniste. |
| SAVI | Olemassa oleva hahmo, liike ja puhelimen AR-esitys. | Myöhempi Chibi-reaktio ja harjoittelutila; ei havaintoputken edellytys. |
| Verda-ohjain ja Junctionin koerekisteri | Olemassa oleva job-elinkaari, idempotenssi, tulosnielu ja lähdesidottu ajokuitti. | SAM-workerin varsinainen inferenssi ja kuitti. Nykyinen keräin ei käynnistä GPU:ta. |

Tarkat lähteet ja commitit ovat liitteessä sekä JSON-tiedostossa. Yksityisen Chibi-hostin, DAMin ja asiakasprojektien lähdekoodia tai aineistoa ei kopioida Junctionin julkiseen pakettiin. Uudelleenkäytetään rajapintamalleja ja hyväksyttyjä sovittimia.

### Olemassa olevan toteutuksen tärkeät rajat

Junctionin runNemotron edellyttää benchmark-rivejä. Meta-havaintoa ei pidä pakottaa siihen. Samassa moduulissa oleva runDrawingObservation näyttää käyttökelpoisen tavan käyttää rajattua provider-kuljetusta ilman benchmark-riippuvuutta. Piirustuksen sivu-/aluerakenne korvataan uudessa sovittimessa kuva-/rajaus- ja tehtävärakenteella; samaan malliin perustuva toinen tarkistus ei ole riippumaton faktatodistus.

Valmetin recognition.py käyttää ulkoisesti tuotettuja embeddingejä. Siinä ei ole valmista kuvasta embeddingiksi -mallia. Matching ratkaisee annetun kustannusmatriisin, ei itsenäisesti opi esineidentiteettiä. Ensimmäinen pystysuuntainen toteutus käyttää näkyvää ehdokasta ja käyttäjän vahvistusta; embedding-haara lisätään vasta perustellusta tarpeesta.

Valmethackin nykyinen verified-tila on estetty ilman fyysistä varmennusta. Gaussian-maskit ovat 3D-pisteindeksejä, SAM-maskit 2D-kuvamaskia. Niiden yhdistäminen vaatii oikean kalibroinnin ja projektion.

Reality Twinin neljän keskeneräisen ruudun raja ja avainruutujen arkistointi ovat käyttökelpoisia suunnittelumalleja. Niiden ARKit-syvyys, pose ja intrinsiikit eivät synny automaattisesti Meta DAT:sta. Puuttuva kenttä pysyy puuttuvana.

SAVIn tarkistettu oletushaara on baseline/round2. Taika Motion Cloudin tarkistettu puu sisältää vain README:n; sitä ei lasketa valmiiksi animaatiomoottoriksi.

## 3. SAM 3.1:n rooli

Metan virallinen SAM 3.1 -julkaisu on 27.3.2026. Käytetään facebookresearch/sam3-lähdettä ja facebook/sam3.1-painoa; oikea rakentaja on **build_sam3_multiplex_video_predictor**. Tavallinen build_sam3_video_predictor ei itsessään vaihda SAM 3.1:een. Mallikortti kertoo checkpoint-julkaisusta ilman Transformers-integraatiota. Painojen käyttöoikeus ja SAM License tarkistetaan ennen latausta. [Julkaisu](https://github.com/facebookresearch/sam3/blob/eef6839bcfc3458dd52ea80535dc6bd62aea86b1/RELEASE_SAM3p1.md), [mallikortti](https://huggingface.co/facebook/sam3.1).

Ensimmäinen worker käyttää virallista PyTorch-toteutusta, lukittua checkpointia ja pientä ruutujoukkoa. Yleispätevää VRAM-minimiä ei oleteta. Python/PyTorch/CUDA-yhteensopivuus sekä oletusarvoisen FA3-polun sopivuus tarkistetaan käytettävällä GPU:lla. Mitataan todellinen huippumuisti; ei aloiteta TensorRT-siirrolla.

SAM vastaa kysymykseen “missä visuaalinen kohde on ja jatkuuko sen seuranta?”. Se ei yksin vastaa “onko tämä käyttäjän oma oikea laturi?”. Seurantatunniste on jakson sisäinen hypoteesi. Peittyminen, vaihto ja uusi kuvaussessio voivat rikkoa jatkuvuuden.

Julkaisun noin seitsenkertainen nopeutus koskee 128 esineen H100-vertailua. Se ei ole tämän kolmiesinetilanteen viivelupaus. Siksi pysyvä käyttöönotto päätetään oman tehtäväkokeen, ei yleisen benchmark-luvun perusteella.

## 4. NVIDIA käytetään nykyisellä todennetulla pohjalla

Junctionin [nykyinen NVIDIA/T46-lähdereititys](AGENT_SOURCE_INDEX.json) ja [brief-lähteet](challenge-research/CURRENT_SOURCES.md) vaativat Nemotron 3.5 Super VL:n olennaisena toimintona. Malli tulkitsee tämän vuoksi oikeasti tehtävän havaintoa. NVIDIAa ei lisätä vain nimeksi eikä vaihdeta Cosmosiin tai Lightning-esimerkkiin.

| Profiili | Nykyinen näyttö | Ensimmäinen käyttöraja |
| --- | --- | --- |
| Hosted NVIDIA | Junction-koodi on olemassa; tämän työn aikana avainta, quota-tilannetta tai live-kutsua ei todennettu. | Tarkka mallinimi nvidia/nemotron-3.5-super-vl-120b-a12b ja nykyiset kuljetusrajat. |
| Paikallinen Super VL | Agents PR106:n lähteissä oikeat pienet text/image/tool-formation-ajot. | NVFP4, 2 × RTX PRO 6000 Blackwell, vLLM 0.32.0, TP2, konteksti 4096, yksi kuva, enintään 256 uutta tokenia, concurrency 1, ei videota. |

Paikallinen palvelin käytti eri served-aliasta kuin hosted-malli. Toteutetaan nimetty paikallinen profiili ja säilytetään tarkka painorevisio; kiinteän hosted-endpointin tai mallin vartiointia ei höllennetä yleiseksi URL-vaihdoksi.

Aiemmassa paikallisessa kokeessa noin 75 GB:n painot ladattiin ja tarkistettiin. Viisi pientä koetta onnistui, joista viides on erillinen jatkokoe; inference-summary.json sisältää neljä. Aiempi kylmäkäynnistys oli 482 s ja cachea hyödyntävä käynnistys 60 s. Nämä ovat yksittäisiä havaintoja. Palvelimet pysäytettiin, painot ja cache säilytettiin; saatavuutta ei ole tarkistettu uudelleen tässä työssä.

Tehokas ajo: yksi rajattu lämmin sessio, sen sisällä samat episodit molemmille vaihtoehdoille, sitten omien prosessien pysäytys. Yhden kuvan paikalliseen profiiliin ei syötetä kahta kuvaa tai videota ilman erillistä todentamista. Yhden GPU:n virallinen resepti ei korvaa omaa aiempaa kahden GPU:n suoritusnäyttöä.

### NVIDIA Skills ja MCP

NVIDIA Skills -reititin luettiin ja virallinen katalogi tarkistettiin myös komennolla npx skills add nvidia/skills --list. Uusia taitoja ei asennettu.

- **nemotron-customize:** mahdollinen myöhempi eval/model_eval-arviointi olemassa olevalle endpointille. Ei tarvetta käynnistää hienosäätöä; tarkat repo-konfiguraatiot ja endpoint pitää valita ennen ajokomentoa.
- **deepstream-import-vision-model:** tukee objektideteiktiota, torjuu segmentoinnin. Se ei ole SAM 3.1:n tuontipolku.
- **vss-build-vision-ai:** kokonaisen palvelukokonaisuuden pystytys. Otetaan vasta, jos jatkuva monivirtavideo tai videohaku osoittaa tarpeen.

GitHub-connector oli tämän auditoinnin todellinen repo- ja kirjoituskanava. Metan dokumentaatio-MCP on nykyisessä projektissa aiemmin todennettu. Verdan native CLI stdio MCP:n aiempi 18 työkalun havainto löytyy Agentsista; sitä ei käynnistetty uudelleen tässä suunnitelmatyössä. MCP välittää hallittuja työkalukutsuja, eikä korvaa mallin ajoa tai GPU:n käyttöoikeutta.

## 5. Kolme sovitinta ja yhteinen havaintosopimus

**Kuvausjakso → SAM-seuranta → tehtäväkohtainen SuperVL-tulkinta → Chibin havaintoehdotus → käyttäjän vahvistama komento.**

| Rakenne | Vähimmäissisältö | Merkitys |
| --- | --- | --- |
| FrameObservation | sessionId, captureGeneration, frameHash, timestamp, kuvan koko; pose/intrinsiikit vain jos oikeasti saatavilla | Mistä hetkestä ja syötteestä havainto tuli. |
| TrackHypothesis | runId, malli- ja painorevisio, trackGeneration, maskRef tai bbox, visibility, epävarmuus | Rajaus ja seurannan jatkuvuushypoteesi. |
| IdentityCandidate | ehdokasviitteet, lähdeviitteet ja unknown/ambiguous/candidate-tila | Ei fyysisesti varmennettua identiteettiä mallin päätöksellä. |
| TaskObservation | taskId, expectedRevision, evidenceRefs, havainnot, epävarmuudet, nextQuestion ja nextStepProposal | Ehdotus nykyiseen tehtävään, ei tehtävän vahvistuskomento. |

Nämä ovat suunnitellut rajapinnat. Integraattori lukitsee skeeman ja yhden yhteisen synteettisen syötteen ennen erillisiä kirjoittajia. Nykyinen resume-command.schema.json säilyy käyttäjäkomentojen sopimuksena.

Nykyisen H1-domainin Observation.subjectId tarkoittaa hostin varmistamaa fyysistä kohdetta. SAMin track_id ei päädy siihen sellaisenaan. Host ratkaisee hyväksymisen, tuoreuden, käyttäjäkontekstin ja mahdollisen identiteetin. Vanhentunut tehtävärevisio tai poistettu lähde ei muutu kelvolliseksi mallin vakuuttavalla vastauksella. “Ei näkyvissä” ja “puuttuu” pidetään eri asioina.

## 6. Seuraavat työpaketit ja työnjako

Aika-arviot ovat aktiivisen työn suunnitteluarvioita. Todellinen laite-, aineisto- ja käyttöoikeustilanne voi siirtää kokonaisen demon valmistumista. Aloitetaan enintään kahdella toteuttavalla workerilla sekä koordinaattorilla; kolmas paketti seuraa vapautuvaan paikkaan.

| Työ | Omistaja ja rajaus | Tuotos | Arvio |
| --- | --- | --- | --- |
| I0: sopimus | Nykyinen Meta-integraattori; yhteinen skeema ja fixture. | Yksi kamera–mikrofoni–laturi-jakso, kehys-/maski-/tehtäväviitteet ja virhetilat. | 30–45 min |
| W1: SAM-worker | Agents/Verda-omistaja; uusi rajattu meta-sam31-koehakemisto. | Pinned input → mask/track-tulos ja oikea inferenssikuitti nykyisen job-elinkaaren kautta. | 1–3 h |
| W2: NVIDIA ja näkymä | Yksi nimetty Junction-palveluomistaja; yhteinen kuljetus vain eksplisiittisellä omistuksella. | runTaskObservation, nimetty provider-profiili ja olemassa olevaan Resume-näkymään havainto/kysymys. | 1–3 h |
| W3: H2/I2-host | Nykyinen yksityisen Chibin omistaja; tarkat olemassa olevat polut vahvistetaan siellä. | Nykyinen host-admission, pysyvä tehtävä/kuitti ja atominen revisionumero; malli tuottaa vain ehdotuksen. | 2–4 h |
| P1: yksi oikea jakso | Integraattori + nykyinen native-/kuvausomistaja. | Havainto läpi putken ja sama käyttäjän vahvistuspolku; yksi kirjattu rajattu ajo. | 30–60 min valmiiden osien jälkeen |
| P2: yksi vertailuerä | Sama GPU-omistaja, ei uutta arviointitiimiä. | Baseline/SAM-vertailu, säilytä/pienennä/poista-päätös. | Enintään yksi rajattu sessio |

W1 ja W2 voidaan tehdä rinnakkain I0:n jälkeen. W3 jatkaa nykyistä H2/I2-jonoa; sitä ei aloiteta toisena kilpailevana host-toteutuksena. CPU-rajapinta ja synteettinen end-to-end-polku etenevät, vaikka GPU:n tai laitteen käyttö olisi estynyt. Integraattori omistaa yhteiset tyypit, manifestit, exportit ja lopullisen kytkennän. UI-muutoksia ei anna samanaikaisesti toiselle Meta-kirjoittajalle.

Jokaisen jatkotyön toimeksianto sisältää työtunnuksen, nykyisen lähde-SHA:n, dirty-baselinen, omistetut polut, yhteisen fixture-version, rajatun budjetin ja palautuksen: commit/PR, toteutunut tulos, konkreettinen este sekä yksi seuraava toimi. Nykyinen issue80 ja Product Factory säilyvät työn rekisterinä. Tämä asiakirja ei itse aktivoi workereita.

## 7. Koe, joka ratkaisee kannattaako SAM pitää mukana

Ensin yksi kuva tai rajaus → yksi SuperVL-vastaus → ehdotus → vahvistus. Sen jälkeen 12 lyhyttä omaa tai hyväksyttyä klippiä, esimerkiksi 6–10 sekuntia: selkeä näkymä, peittyminen, paluu/samannäköinen esine, siirretty esine, valaistuksen muutos ja kameran liike. Kaksi esimerkkiä kustakin, neljä kehitykseen ja kahdeksan lukittuun loppuvertailuun. Tämä on pieni tuotekoe, ei tilastollinen yleispätevyysväite.

Sama malliprofiili, tehtävä ja syöteajankohta molemmille:

1. Perustaso: nykyinen koko kuvan SuperVL-tulkinta.
2. SAM-avusteinen: seurannan valitsema ajantasainen rajaus ja lähteeseen sidottu havainto.
3. Mallia kutsutaan olennaisesta muutoksesta tai epäselvyydestä, ei jokaisesta ruudusta.

Offline-toistossa mallille annetaan vain havaintohetkeen mennessä saatavilla oleva video. Tulevien ruutujen tai jälkikäteen tehdyn kaksisuuntaisen seurannan tieto ei kelpaa reaaliaikaisen tuloksen näytöksi. Rajauksen menettämä ympäröivä konteksti kirjataan epäonnistumiseksi eikä piiloteta.

Ratkaisevat mittarit ovat väärän esineen ehdotus, seurannan ID-vaihdos, havaittu olennainen muutos, hyödyllinen jatkamisohje ja turha vahvistuskysymys. Teknisiä mittareita ovat p50/p95-viive, huippu-VRAM, provider-kutsut ja todellinen varattu GPU-aika. Kylmäkäynnistys eritellään. Tarkka fyysinen identiteetti tai tehtävän valmius ei saa tulla automaattisesti vahvistetuksi.

SAM jää putkeen, jos se parantaa tehtävän havaintoa tai vähentää mitattua kuvatulkinnan kuormaa ilman huonompaa identiteettikäyttäytymistä. Jos hyötyä ei tule, säilytetään worker kokeilukelpoisena ja jatketaan yksinkertaisemmalla kuvatulkinnalla. Ensimmäistä heikkoa tulosta ei korjata laajalla mallimatriisilla tai hienosäädöllä.

Suunnittelun ajokatto: yksi enintään 30 minuutin lämmin mallisessio olemassa olevan valtuutetun kapasiteetin ja budjetin sisällä. Koko GPU-varauksen aika, myös lataus, lasketaan; kahden GPU:n 30 minuuttia on 60 GPU-minuuttia. Tämä katto ei myönnä uutta kulutusoikeutta. Todelliset hinnat ja nykyinen quota ovat tässä tuntemattomia.

## 8. Mitä seuraa toimivan jakson jälkeen

**Ensimmäiset 1–2 viikkoa:** mitatut todelliset jaksot, luotettava keskeytys/paluu ja käyttäjän korjaus. Lisätään Valmetin ehdokasyhdistely vain, jos samannäköisten esineiden tapaukset osoittavat tarpeen. Tallennetut maskit ja rajaukset kytketään DAM-tyyppiseen lähdehistoriaan.

**Seuraavat 2–6 viikkoa:** käyttäjän opettamat esineet ja tehtävät, epävarman havainnon korjaaminen sekä tehtävän siirtäminen toiselle suostuneelle käyttäjälle. Muisti vanhenee ja poistuu lähteensä mukana. Kolmen työnkulun mittaus etenee yhteisen nykyisen hostin kautta.

**6–12 viikkoa:** sama tehtävä muuttuu puhelimen tai XR:n harjoitteluksi. SAVI antaa valmiin hahmopohjan, Reality Twin sopivan tallenteen ja Valmet-historia korjattavan kohdemallin. SAM 3D ja Omniverse tutkitaan vasta, jos oikean ympäristön harjoittelurekonstruktio tuo käyttäjäarvoa. 2D-videota ei markkinoida valmiina 3D-maailmamallina.

Pitkälle viety mahdollisuus on “näytä kerran, auta myöhemmin”: käyttäjä opettaa toimenpiteen, keskeyttää sen ja saa seuraavalla kerralla apua juuri muuttuneeseen kohtaan. Sen edellytykset ovat lähteeseen sidottu muisti, selvä epävarmuus ja käyttäjän hallitsema tehtävätila. Pelkkä näyttävä maski tai avatar ei vielä toteuta tätä.

## 9. Todennettu tila ja avoimet riippuvuudet

Kolme tutkimusworkeria teki tässä työssä lähdeauditoinnin; koordinaattori tarkisti ratkaisevat tiedostot ja viralliset lähteet. NVIDIA Skills -katalogi luettiin. Junctionin tuore main oli 12eae05966445c9c596f8465389763e2970227e9; aiemmat suunnitelma-PR104 ja UI-PR108 ovat yhdistettyjä. Aiempi H1-domain on yhdistetty yksityiseen Chibiin. Vanhan execution.jsonin historiallisia suoritustiloja ei kirjoiteta takautuvasti uusiksi.

Uusi SAM 3.1 -ajo, nykyinen NVIDIA hosted -avain/quota, Verdan tämänhetkinen GPU/cache-saatavuus ja live-kamera→host-ketju jäivät todentamatta. Nykyinen lähde riittää sovitinten toteutuksen suunnitteluun. Aiemman native-ajon levykapasiteettieste on historiallinen havainto, ei tämän työn uusi Mac-tarkistus.

Suunnitelmatyö ei asentanut uusia NVIDIA-taitoja, ladannut malleja, käynnistänyt inferenssiä tai muuttanut tuotantoa. Seuraavan työn konkreettinen aloitus on I0:n yhteinen havaintosopimus ja sen jälkeen W1/W2. Runtime-jatko kuuluu nykyisille omistajille ja olemassa olevaan työnkulkuun.

## Lähdeliite: tarkistetut versiot

- Junction, 12eae05966445c9c596f8465389763e2970227e9: [Nemotron-palvelu](https://github.com/SalesSquad/junction-pets/blob/12eae05966445c9c596f8465389763e2970227e9/services/nemotron-vl/index.mjs), [Stoa-sovitin](https://github.com/SalesSquad/junction-pets/tree/12eae05966445c9c596f8465389763e2970227e9/services/stoa-nvidia), [koerekisteri](https://github.com/SalesSquad/junction-pets/tree/12eae05966445c9c596f8465389763e2970227e9/services/experiment-registry).
- Agents, 4ecdc4c085f4bc50b5af9cf0240abe85a10d8f9b: [aiempi SuperVL-ajo](https://github.com/SalesSquad/agents/blob/4ecdc4c085f4bc50b5af9cf0240abe85a10d8f9b/cloud-services/verda/experiments/nemotron-local-20261114/README.md), [ohjain](https://github.com/SalesSquad/agents/blob/4ecdc4c085f4bc50b5af9cf0240abe85a10d8f9b/cloud-services/verda/runner.py), [MCP-havainto](https://github.com/SalesSquad/agents/blob/4ecdc4c085f4bc50b5af9cf0240abe85a10d8f9b/cloud-services/verda/mcp-and-skills.md).
- Valmet Truth Engine, 21f2cc44bb3d05aeebf481a7a5e5c3f878a1222e: [tunnistusehdokkaat](https://github.com/SalesSquad/valmet-truth-engine/blob/21f2cc44bb3d05aeebf481a7a5e5c3f878a1222e/ecre/scale/recognition.py), [yhdistely](https://github.com/SalesSquad/valmet-truth-engine/blob/21f2cc44bb3d05aeebf481a7a5e5c3f878a1222e/ecre/scale/matching.py).
- Valmethack, c86c02f78df8871215f42bfa885220bfcd106904: [identiteettitilat](https://github.com/SalesSquad/valmethack/blob/c86c02f78df8871215f42bfa885220bfcd106904/companion/src/equipment-identity.mjs), [Evidence Twin](https://github.com/SalesSquad/valmethack/blob/c86c02f78df8871215f42bfa885220bfcd106904/contracts/evidence-twin/v1/README.md).
- Reality Twin, def12f935299a203f440b9273503a944ad32c5e2: [kuvaus](https://github.com/SalesSquad/reality-twin/blob/def12f935299a203f440b9273503a944ad32c5e2/Sources/RealityTwinCapture/CaptureController.swift). CaptureArchivea muuttava [PR25](https://github.com/SalesSquad/reality-twin/pull/25) oli avoin headissa 3a1e62bb29c8af0f679124c787c25fd59d74e4ce; koordinoi poiminta nykyisen omistajan kanssa.
- MacAssetDAM, 864af2c22c55df1dcc5295b0b6ad11f1d28e7947: [materiaalihistoria](https://github.com/SalesSquad/MacAssetDAM/blob/864af2c22c55df1dcc5295b0b6ad11f1d28e7947/metadata_ledger_v3.py).
- SAVI, baseline/round2, cd74ce55dc057e44ebffb12173b7ae648ebd5cf1: [AR-hahmo](https://github.com/SalesSquad/savi/blob/cd74ce55dc057e44ebffb12173b7ae648ebd5cf1/apple/Sources/SaviKit/AR/ARCompanion.swift). Liikevideoita sisältävä [PR40](https://github.com/SalesSquad/savi/pull/40) oli avoin headissa 670294e23bf0e8026dbc20a78d9cc899bf832288; sen sisältöä ei lasketa oletushaaran toteutukseksi.
- Meta SAM: lähde eef6839bcfc3458dd52ea80535dc6bd62aea86b1, painorevisio daa63191845a41281374e725f4c9e51c7a824460, checkpoint sam3.1_multiplex.pt. [Rakentaja](https://github.com/facebookresearch/sam3/blob/eef6839bcfc3458dd52ea80535dc6bd62aea86b1/sam3/model_builder.py).
- NVIDIA SuperVL NVFP4: aiemmin ajettu painorevisio 3acb09951cff50cda7be0200ebbad2c15a3e63ba. [Virallinen mallikortti](https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Super-VL-120B-A12B-NVFP4), [hosted API](https://build.nvidia.com/nvidia/nemotron-3.5-super-vl-120b-a12b).
- NVIDIA Skills, 894f2d7dfee49085e84e21c1aad2513bc44a5b6d: [katalogi](https://github.com/NVIDIA/skills/blob/894f2d7dfee49085e84e21c1aad2513bc44a5b6d/skills.sh.json), [nemotron-customize](https://github.com/NVIDIA/skills/blob/894f2d7dfee49085e84e21c1aad2513bc44a5b6d/skills/nemotron-customize/SKILL.md), [DeepStream-rajaukset](https://github.com/NVIDIA/skills/blob/894f2d7dfee49085e84e21c1aad2513bc44a5b6d/skills/deepstream-import-vision-model/SKILL.md), [VSS-taito](https://github.com/NVIDIA/skills/blob/894f2d7dfee49085e84e21c1aad2513bc44a5b6d/skills/vss-build-vision-ai/SKILL.md).

