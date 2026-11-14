# J26 ROBOTICS / MIT SOURCE RADAR — SkillProof, 14.11.2026

**Työ-ID:** `J26-ROBOTICS-MIT-RADAR-20261114`  
**Tarkasteltu repo:** `SalesSquad/junction-pets`, autentikoitu `main=51ac807d03fe5c37d1fdf8518ef32830ff50ac2b` (lähdehetken checkpoint, tarkista ennen tuotekirjoitusta).  
**Junction-lähderajaus:** `START_HERE.md`, `AGENTS.md`, `docs/AGENT_SOURCE_INDEX.json`, `docs/challenge-research/CURRENT_SOURCES.md`, `current-source-catalog.json` luettu nykyisestä mainista; 2026-11-14 snapshot, 38 briefiä, 35 partner-avainta. Relevantit `rokoko/M326`, `aalto/M320`, `ignite-next-and-intel/M330`, `arduino/M356,T45`. Lue aina myöhempi `latestClarification` ennen aikaisempaa ohjetta.  
**Tila:** tutkimus ja itsenäinen tuotekonsepti, **EI malli-, paino-, SDK-, koulutus-, laite-, sponsoripalvelu- tai GPU-integraation suoritus**. Ei kolmannen osapuolen koodin kopiointia eikä uusia riippuvuuksia. Lähdereferenssit ja lupaehdot tallennettu koneellisesti tiedostoon `J26_ROBOTICS_MIT_LEDGER_20261114.json`.

## Päätelmä: markkinoille ei tarvita taas yhtä VLA-politiikkaa

Nykyinen avoimen robotiikan kenttä kattaa jo demonstraatioista oppimisen (robomimic), manipulaatiosimulaation (robosuite), diffuusiopolitiikat ja action chunking -mallit (Diffusion Policy, ACT), kieli–kuva–toiminta-mallin (OpenVLA), muokattavat toimintapuut (BehaviorTree.CPP) ja kamerahavaintojen seurannan (Supervision). Arkkitehtuurin uusi kaupallinen kohta on näiden välissä: **onko opetettu taito riittävän todennettava, jotta se voidaan käyttää tässä nimenomaisessa tilanteessa ja siirtää toiseen laitteeseen?**

**Ehdotus: SkillProof — Counterfactual Robot Skill Passport.** Robotille ei toimiteta vain toiminnon koodia tai painoja, vaan *taidon käyttökelpoisuusalueen, koetellut rajatapaukset, ehdolliset palautumismallit, turvallisen kieltäytymisen ja lähteisiin sidotun episode-kuitin*. Uusi mekanismi ei ole väite ensimmäisestä maailmassa eikä patentoitavuudesta, vaan ehdotus kilpailullisesti hyödylliseksi todennettavaksi yhdisteeksi.

> **Näytettävä 60 sekunnin tilanne:** Ihminen opettaa Rokokolla poimimaan kappaleen; sama liikesarja korjataan simulaatiossa ja jaetaan kahdelle erilaiselle robottimallille. Ensimmäisessä tavallinen kappale onnistuu. Toisessa kappale on siirtynyt ja kamera on epävarma: perinteinen toistaja jatkaa, SkillProof tunnistaa edeltävien testien rajojen ylittyneen ja **kieltäytyy** tai ehdottaa uutta kuvausta. Intelin tarkastustulos muuttaa valintaa (hyvä / viallinen / uudelleen tarkastettava). Näytöllä on kolme erillistä totuutta: `SIMULATED`, `OFFLINE_REPLAY` ja `PHYSICAL_VERIFIED`. Niitä ei sekoiteta.

## 11 tarkistettua MIT-repoa — täsmälliset lähde-SHA:t

Koodilisenssi tarkistettiin kunkin **juuri nimetyn commitin** `LICENSE`-tiedostosta. Taulukon lyhyt tunniste on osa koneellista täydellistä SHA:ta. **Tämä ei vahvista mukana olevien mallipainojen, datan, riippuvuuksien eikä robottien käyttöoikeuksia.**

| Repo | Pinattu commit | Tarkistettu lisenssi / blob | Mitä hyödynnämme | Tuotteet |
|---|---|---|---|---|
| [1. BehaviorTree/BehaviorTree.CPP](https://github.com/BehaviorTree/BehaviorTree.CPP/tree/365b2e499d34ba1220588188a7aa045158909b0f) | `365b2e499d` | [MIT · LICENSE](https://github.com/BehaviorTree/BehaviorTree.CPP/blob/365b2e499d34ba1220588188a7aa045158909b0f/LICENSE) (`e55a7557fd`) | Keskeytettävät ehtopuut, palautuminen ja lokitus | Intel, Aalto, Rokoko |
| [2. ARISE-Initiative/robomimic](https://github.com/ARISE-Initiative/robomimic/tree/d309eaecc18acf4152a830a895a6984b8ac71b05) | `d309eaecc1` | [MIT · LICENSE](https://github.com/ARISE-Initiative/robomimic/blob/d309eaecc18acf4152a830a895a6984b8ac71b05/LICENSE) (`934eaa87bb`) | Demonstraatioista oppiminen ja laadun arviointi | Rokoko, Aalto, Intel |
| [3. ARISE-Initiative/robosuite](https://github.com/ARISE-Initiative/robosuite/tree/5ce6643f3092639d08f7b0f90ed1c6a84f50552c) | `5ce6643f30` | [MIT · LICENSE](https://github.com/ARISE-Initiative/robosuite/blob/5ce6643f3092639d08f7b0f90ed1c6a84f50552c/LICENSE) (`e20189628c`) | Manipuloinnin simulaatiot, satunnaistettu ympäristö ja teleoperaation toisto | Rokoko, Aalto, Intel |
| [4. real-stanford/diffusion_policy](https://github.com/real-stanford/diffusion_policy/tree/5ba07ac6661db573af695b419a7947ecb704690f) | `5ba07ac666` | [MIT · LICENSE](https://github.com/real-stanford/diffusion_policy/blob/5ba07ac6661db573af695b419a7947ecb704690f/LICENSE) (`a2eb6cb62c`) | Ehdollisen toimintosarjan oppiminen diffuusiolla | Aalto, Intel |
| [5. tonyzhaozh/act](https://github.com/tonyzhaozh/act/tree/742c753c0d4a5d87076c8f69e5628c79a8cc5488) | `742c753c0d` | [MIT · LICENSE](https://github.com/tonyzhaozh/act/blob/742c753c0d4a5d87076c8f69e5628c79a8cc5488/LICENSE) (`35e5f5e277`) | Action chunking / bimanuaalisen tehtävän sujuvuus | Aalto, Rokoko |
| [6. openvla/openvla](https://github.com/openvla/openvla/tree/c8f03f48af692657d3060c19588038c7220e9af9) | `c8f03f48af` | [MIT · LICENSE](https://github.com/openvla/openvla/blob/c8f03f48af692657d3060c19588038c7220e9af9/LICENSE) (`04f26a7d0b`) | Kuva+ohje -> toiminta -arkkitehtuuri ja koodiesimerkki | Aalto, Intel |
| [7. roboflow/supervision](https://github.com/roboflow/supervision/tree/5f9e21ef2d186da02a7fe65b20488337c04370b1) | `5f9e21ef2d` | [MIT · LICENSE](https://github.com/roboflow/supervision/blob/5f9e21ef2d186da02a7fe65b20488337c04370b1/LICENSE.md) (`ab7110e8f2`) | Havaintojen seuranta, zone-/ID-pohjaiset mittarit | Intel, Arduino |
| [8. HumanCompatibleAI/imitation](https://github.com/HumanCompatibleAI/imitation/tree/e5ef18806c449ca47153b494a02471c5e2ae3a14) | `e5ef18806c` | [MIT · LICENSE](https://github.com/HumanCompatibleAI/imitation/blob/e5ef18806c449ca47153b494a02471c5e2ae3a14/LICENSE) (`c97e117016`) | BC/DAgger ja ihmiskorjausten tuominen oppimiseen | Rokoko, Aalto |
| [9. petercorke/robotics-toolbox-python](https://github.com/petercorke/robotics-toolbox-python/tree/879fb363580840e19ee70b6b175e8cd3543e2b38) | `879fb36358` | [MIT · LICENSE](https://github.com/petercorke/robotics-toolbox-python/blob/879fb363580840e19ee70b6b175e8cd3543e2b38/LICENSE) (`3a7f69f9de`) | Kinematiikka, URDF, SE(3), IK, liikeradat | Rokoko, Aalto, Intel |
| [10. DLR-RM/stable-baselines3](https://github.com/DLR-RM/stable-baselines3/tree/0cdcd200deef06b9ad0af72f6ddfb07c06c6df39) | `0cdcd200de` | [MIT · LICENSE](https://github.com/DLR-RM/stable-baselines3/blob/0cdcd200deef06b9ad0af72f6ddfb07c06c6df39/LICENSE) (`0951e29b4f`) | PPO/SAC-baselinet simulaatiotutkimuksessa | Aalto, Intel |
| [11. Farama-Foundation/Gymnasium](https://github.com/Farama-Foundation/Gymnasium/tree/68c3f95def1b9d91922db5363a28dc1d4a83a960) | `68c3f95def` | [MIT · LICENSE](https://github.com/Farama-Foundation/Gymnasium/blob/68c3f95def1b9d91922db5363a28dc1d4a83a960/LICENSE) (`ac10bf4437`) | Yhtenäinen askel/reward/termination-rajapinta ja siemenet | Aalto, Intel, Rokoko |

**Erityishuomiot:** `robosuite` ilmoittaa MIT-otsakkeen alla myös kolmannen osapuolen MuJoCo/Apache-2.0-koodista. `OpenVLA`n **MIT-koodi ei tee sen Llama-2-pohjaisista painoista MIT-lisensoituja**. `huggingface/lerobot` on **Apache-2.0**, ei MIT, ja sen data-/laiterajapintoja voi käyttää vain erikseen arvioitujen ehtojen mukaan. `MimicGen`in koodi-/derivaattaehdot sisältävät ei-kaupallisen rajoitteen — jätä pois automaattisesta MIT-uudelleenkäytöstä. MIT:n mukainen tekijänoikeus- ja lisenssi-ilmoitus on säilytettävä kopioiduissa olennaisissa osissa; jokainen paketti, data ja painot tulee inventoida erikseen ennen vendoroimista.

## Viisi konkreettista uutta tuotekyvykkyyttä

### 1. Skill DNA / taitopassi

Opetusjakson tulos ei ole pelkkä HDF5/CSV- tai LeRobot-episodi. Se sisältää `skill_id`, version, robotin/työkalun kinematiikka- ja kalibrointitunnukset, koordinattikehykset ja yksiköt, lähteen oikeudet, syötteiden tiivisteet, sallitun tehtävän, ennakkoehdot, voima-/nopeus-/tarttumarajat, epäonnistumisesimerkit, ihmisen keskeytyspisteet, onnistumiset **ja nollat** sekä evaluoinnin otoskoon/epävarmuuden. Tämä on taidon *siirrettävyyden sopimus*, ei turvallisuussertifikaatti.

### 2. Counterfactual Skill Lab: robotin punainen joukkue

Järjestelmä generoi **ennalta määritellyn** haastematriisin eikä arvioi itseään vain onnistuneilla demoilla: kappaleen paikka ±5/10 cm, kierto, näkymän peittyminen, tahallinen väärä väri, puuttuva kuva, käsineen pakettikato, kalibroinnin ryömintä, havaintomallin väärä luokka, uusi sanamuoto ja keskeytys. Jokainen koe tallentaa siemenen ja riippumattoman hyväksymiskriteerin. Taito pääsee kokeeseen vain niiden ehtojen puitteissa, joissa rajoitettu siirto on onnistunut; muualla se pidättäytyy. **Väärä onnistumisväite tai vaarallinen liike on pahempi kuin dokumentoitu kieltäytyminen.**

### 3. Failure-to-Skill / taito oppii korjauksesta

Robomimic + MIT-lisensoitu imitation/DAgger tarjoavat pohjan ihmisen korjaamien jaksojen käyttämiseen. Virhekorpus ei merkitse vain "epäonnistui", vaan *miksi*: väärä havainto, muuttunut kohde, eri koordinaatisto, viive, huono tartunta, ylärajan ylitys. Oppimisen valinta ei tapahdu autonomisesti oikeassa laitteessa; laboratoriossa vertaillaan alkuperäistä, virheestä täydennettyä ja ihmisen korjaamaa politiikkaa samalla holdout-matriisilla.

### 4. Inspection-to-Intervention — poikkeama muuttaa teon

Intel-työasemalla Anomalib-tyyppinen signaali ei saa päätyä vain punaiseksi ruuduksi. Se muuttuu **todistettavaksi ehdotukseksi**: tarkasta uudelleen, aseta toiseen kulhoon, vapauta ihmisen hyväksyttäväksi tai pysähdy. Roboflow Supervision on havaintojen rajaus/seuranta, **ei itse virheiden tunnistusmalli**. BehaviorTree.CPP on näkyvän toimintaketjun rakenne, **ei mekaanisen turvallisuuden varmistin**. Todellisen SO-101:n alasajo, nopeusrajat ja hätäpysäytys ovat laitekerroksen vastuulla.

### 5. Embodied Change Detection + local-first energy truth

Arduino/UNO Q tai Intelin alusta näkee ajan myötä muuttuneen työympäristön: "vanhan havainnon perusteella ei enää saa toimia". Verkkokatko, kuvaepävarmuus ja ristiin menevät kellot näkyvät datassa, eikä syötetystä "confidence"-luvusta rakenneta oikeuksia. UNO Q:n Linux+MCU-tasot pidetään erillään; fyysinen virrankatkaisu, turvallisuus ja paikallinen ohitus tarvitsevat todellisen riippumattoman ohjaimen. **Energia per onnistunut tehtävä** on mitattava laitteesta; arvioitu säästö ja anturin oma energiankulutus raportoidaan erikseen.

## Yhteinen ohut sopimus — ei megakerneliä

Taitopassin lähteen ja episodin rakennetta voi ehdottaa näin (vain esimerkkiskeema, ei ajettua rajapintaa):

```json
{
  "schema": "skillproof.passport.v0",
  "skill_id": "sort-duplo-color",
  "source_kind": "SYNTHETIC",
  "source_digest_sha256": "<SHA256 of exact approved source>",
  "rights_ref": "fixture-only",
  "actor_device": "G1/SIMULATED",
  "robot_frame": "base_link",
  "sensor_frame": "camera_overhead",
  "transform_version": "calibration:v1",
  "device_monotonic_time_ns": "<integer as string>",
  "clock_uncertainty_ms": 2.4,
  "task_constraints": {"instruction": "red:left yellow:center blue:right", "recovery": "ABSTAIN_OR_REVIEW"},
  "policy": {"name": "reviewed_baseline", "source_sha": "<model-or-script-sha>"},
  "eval": {"split": "shifted-heldout-v1", "n": 0, "successes": 0, "unsafe_actions": 0, "abstentions": 0},
  "safety": {"upstream_hardware_filter_verified": false, "physical_e_stop_verified": false},
  "claim": "NOT_HARDWARE_QUALIFIED"
}
```

**Sopimusten raja:** Robotiikan kolme linjaa (Rokoko/Aalto/Intel) voivat jakaa vain koordinaattien ja kuittien konvention sekä riippumattoman testiaineistorakenteen. **Ei** yhteistä credential vaultia, maksullista ajuria, suurta Rust-kerneliä tai yleistä kytkentää Chibiin. Aallon Beyond the Clinic pysyy erillisenä: mitään terveys-/hyvinvointitietoa ei virtaa robotin dataputkeen. AstraZenecan julkinen aggregaattidata pysyy erillisessä data- ja päättelymallissa.

## Mihin toteutuksiin idea viedään

| Linja | Jo olemassa / rehellinen status | Ensimmäinen omistettu koodiviipale tämän tutkimuksen jälkeen | Vaikuttava myöhempi demo |
|---|---|---|---|
| **Rokoko M326** | PR #110: synteettinen MotionBridge-turvatilan replay, 11/11 kohdennettua testiä aiemmalla SHA:lla; SDK ja suora liikekaappaus varmistamatta | Laadi oikeuksien varmistamisen jälkeen **kalibroitu raaka-Rokoko→tarjottu simulaattoritoiminto→taidon laadun kuitti**, säilytä duplikaattiotsakkeet. Tee semantiikkakartoitus ilman väitettyä laiteajoa. | Yksi käsineellä opetettu tehtävä, jonka toisinto ja rajoitukset näkyvät usealla robottimallilla. |
| **Aalto Humanoid M320** | Yhteinen aalto-evidence key: LeRobot v3:n 20 episodia / 11 720 kehystä, osa huonolaatuisia; RTX/Isaac ja fyysinen G1 eivät ole tässä todistettuja | Kilpailun **30 Hz policy-server** ja väriohjeen kuusi permutaatiota; eksplisiittinen epävarmuus/STOP, lähdepinnatut offline-havainnot. Kokeile ACT vs yksinkertainen sääntöpohjainen baseline myöhemmin. | Uusi lajitteluohje, eri esinesijainti → perusteltu toiminta tai rehellinen keskeytys G1:n turvasuodattimen kanssa. |
| **Intel × Ignite M330** | PR #116 M1: 6 synteettistä inspect-to-action-skenaariota, SHA-ketjutettu kuitti, 15/15 Node-testiä; **ei Anomalib/VLA/OpenVINO/rautaa**. Sponsorin eri rubriikit edelleen ristiriidassa. | **M2:** sovita lisensoidut Anomalib-viitehavainnot ei-aktuoivaan veto/reimage/stop/re-sort -päätöslokiin; erota väri ja vika. Älä kopioi M1-simulaattoria uudelleen. | Todellinen SO-101 erottelee vialliset ja hyvät; väärän kappaleen keskeytys ja mitattu sykli. |
| **Arduino M356/T45** | PR #117 M1: consent/watchdog/hysteresis- ja energia-olettamussimulaattori, 13/13 Node-testiä; **ei UNO Q -rautaa, eikä mitattua energiavaikutusta**. | **M2:** oikealla luvallisella UNO Q+Modulinolla App Lab/Bridge-pinnattu sensori → paikallinen malli → todellinen merkkisignaali; mittaa watit, älä toista synteettistä M1:tä. | Offline edge -tarkastus, fyysisesti havaittava tilamuutos ja todellinen energiankulutus/vaikutus. |

**HUOM:** Intel- ja Arduino-tuotteilla oli issue #80:ssa jo erilliset aktiiviset kirjoittajavaateet  älä ota niiden `solutions/**`-polkuja päällekkäiselle tutkimusworkerille. Tämä dokumentti kuuluu omaan uuteen `docs/product-factory/`-tiedostoon. Aallon Beyond Clinic M343 -omistajuus pitää edelleen tarkistaa ennen M320:n kirjoittajaa.

## Kolme puolustettavaa kokeellista innovaatiota

1. **Transferability score, ei pelkkä success-rate.** Mittaa toteutunutta onnistumista nähtyjen ja muutettujen olosuhteiden yli. `accepted_successes / accepted_attempts` yksin ei kelpaa: jos robotti kieltäytyy kaikesta, näennäinen turvallisuus voi näyttää hyvältä. Raportoi myös *acceptance coverage*, väärien hyväksyntöjen määrä sekä luottamusväli ja turvallisuusrikkeet.
2. **Failure-conditioned adaptation.** Kerää erillinen failure taxonomy ja korjatut demonstroinnit; vertaile saman siemenen terveitä ja stressattuja koejaksoja. Palkitse mallia siitä, että se muuttaa toimintoa **vain syystä**, joka näkyy alkuperäisessä datassa.
3. **Skill swap marketplace -siemen.** Taitopassi on myöhemmin siirrettävissä eri robottien ja organisaatioiden välillä, mutta jakelu sallitaan vain datan, teoskoodin, painojen ja laiteajurin erilliset lisenssi-/oikeustarkastukset suorittamalla. Ei markkinapaikkatransaktioita tai hankintaa hackathonissa.

## Tarkat hyväksymiskriteerit — ei vanity demoja

**Offline-first P0 (ei GPU eikä uutta palvelua):**
- Replaylla on versioitu tallenteen lisenssi/kind, kello/koordinaatit ja syötehash; puuttuvat tai ristiriitaiset muodot torjutaan. Ei teeskentelyä "real robot".
- Ennalta valitut 12 olosuhdemuutosta (3 objektin paikkaa × 2 valaistusta × 2 näkyvyyttä) ja 4 turvallisuuspoikkeusta (stale/deadman/calibration/unknown instruction) tuottavat **vasta sitten** raportoidut onnistumis-/kieltäytymisasteet; mitään tulosta ei arvata.
- Vähintään 2 vertailupolitiikkaa (yksinkertainen scripted replay ja rajoitettu planner) samoille siemenille; koulutuspolitiikka vasta asianmukaisessa ympäristössä.

**Simulaatio P1 (todellinen käynnistetty runtime):**
- Robosuite-simulaation työtapaus, rekisteröity kalibrointi, 50+ holdout-episodia, n/epävarmuus/latenssi/pysäytykset; simulatorin ja sponsorin Isaac-sopimuksen eroa ei peitetä.
- Aallon *27/30 Hz* -ehto mitataan varsinaisessa järjestäjän policy-runnerissa, ei tavallisesta Node-ajastimesta.

**Fyysinen P2 (vain virallisen hyväksynnän jälkeen):**
- Ensimmäinen dokumentoitu turvallinen liike/poistotila, valvottu toiminta, oikea e-stop, operaattorin keskeytys ja tarkasti eritelty laitepolku.
- Intelin todellinen kolmen kulhon onnistumisprosentti sekä Intel-CPU/GPU/NPU-kohteen mitattu kulutus, älä kuvaa tavallista Mac-inferenssiä Intelin NPU:nä.
- Rokokon live-latenssi mitataan oikeasta Device SDK -virrasta vasta myönnetyllä lisenssillä ja laitteella.

**90 päivän tuotekiila:** oppivan robotin *audit trail + skill quality gate* datankeruuyrityksille, tutkimusroboteille ja pienille teollisuusintegraattoreille. Myyjän väite, että palvelu säästää aikaa/rahaa tai siirtää taidon kahden eri robotin välille, pitää validoida vertaamalla ihmisminuutit per hyväksytty onnistunut tehtävä ja regressioina holdout-skenaarioissa.

## 48 h suunnitelma, joka ei sotke nykyisiä kirjoittajia

**Päivä 0:** nyt varmistettujen MIT-lähteiden SHA+LICENSE-havainnot tähän lukittuun katalogiin; päätös konseptista ja minimoitu `skillproof.passport.v0`. Ei uusia root-kirjastoriippuvuuksia.

**Päivä 1:** Intel #116 ja Arduino #117 ovat jo M1-prototyyppejä; **ei uutta samansisältöistä M1-koodia**. Anna näiden omistajille M2-ideat ja hanki oikea sponsorin data/laite vasta todetuilla käyttöoikeuksilla. Rokokon PR110:n nykyinen HEAD ja integraatio tarkistetaan ennen M2-koodausta. Aalto Humanoidin ensimmäinen offline-policy-rajapinta vain vapaan Aalto-kirjoittajan toimesta. Ei lupaamattomia laitteita.

**Päivä 2:** hyväksyttyyn simulaattoriin kytke vain yksi lähdevaatimukset täyttävä liikesarja ja yksi havaintolähde. Mittaa negatiiviset skenaariot ensin, älä laajenna kaikkia skriptejä kerralla. Jos oikea robotti on saavuttamattomissa, demo on **SIMULATED** eikä sponsorihyväksytty.

**Sääntö:** kaksi toisistaan riippumatonta toteutusviipaletta per olemassa oleva Product Factory -kierros. Ennen koodausta varmista current `main`, PR-head, haara, yhtiöomistaja, oikeudet ja sallittu suoritusympäristö; Portfolio PR Recovery jatkaa ainoana PR-integraattorina. Tämä tutkimus ei käynnistä workeria, luo uutta automaatiota, maksa GPU:sta tai tee FINAL #77 -submissiota.

## Lisenssien käyttöpolitiikka / avoin näyttö

- **Varmennettu:** 11 repositorion pääasiallisen koodin MIT-lisenssimerkintä kyseisellä commitilla; SHA ja `LICENSE` blob sekä suora URL. Varmennus ei ole koko dependency graphin lisenssiskannaus.
- **Ei tehty:** ulkopuolisen koodin kopiointi tai paketointiin lisääminen, benchmarkien suorittaminen, mallipainojen tai datasetin lataus, todellinen robotin liike, teollinen turvallisuussertifiointi.
- **Ennen ensimmäistä koodilainausta:** kirjaa lähdepolku/commit ja teoskoko, pidä alkuperäinen copyright+MIT notice tarvittavissa jakeluissa, pinnaa riippuvuudet, tarkista assetit/painot/datasetit/kolmannen osapuolen lisenssit ja tarkista kilpailun event-born- ja IP-säännöt. Suosi kirjastoja runtime-riippuvuuksina tai puhdasta itse toteutettua rajapintaa, ei suurta vendoroitua haarautumaa.
- **Testit:** tätä docs-only tutkimusta ei ajeta raskaita CI-, browser- tai GPU-sarjoja vastaan; seuraava pieni prototyyppi testataan sen omalla riskirajalla.
