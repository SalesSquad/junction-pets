# Independent Claude onboarding trial — 13 November 2026

Source: `5852fa406a7ea38ed02f0f83ab9b904ad427bccc` (clean isolated main checkout).
Reviewer: actual Claude Code 2.1.322, reported model `claude-sonnet-5-5`, medium effort.
Method: fresh noninteractive session, restricted Read/Glob/Grep tools, no network, shell execution, edits, MCP or prior conversation. The trial exercised repository discovery, not executable setup or live CI. Runtime was about 107 seconds, 21 model turns.

## Coordinator verification and limits

- Confirmed START_HERE, package scripts, contribution rules and Meta next-step text against the source. Meta executable service and Stoa-to-NVIDIA integration were documented as pending PR sources; their absence from main is a real integration boundary, not evidence that their branches are broken.
- The 7/10 and 4/10 scores are the reviewer's subjective assessment, not measured development throughput.
- **Do not interpret the review's CI paragraph as proof that automatic feedback is absent.** GitHub Actions is deliberately disabled; authorized Codex Cloud/local executors exist in the workflow. This read-only review did not query those systems or run tests. Their actual operation remains outside this trial.
- Only the listed file excerpts and searches were inspected. The reviewer did not read the full architecture/playbook or inspect pending runtime branches. Its conclusions are bounded accordingly.
- Resolved the reviewer's Meta SHA question: the exact diff from tested code commit `56b306b…` to source `fb90ab5…` contains only the following files:

```text
AGENTS.md
README.md
docs/META_START_HERE.md
docs/evidence/meta-source-index-20261113.json
docs/research/META_GLASSES_ARKIT_20261113.md
```

No implementation changes were made by this audit. Suggested follow-up: a five-minute role-specific start path, explicit PR dependency/integration table, concrete next-task cards, and one documented fast validation command per change type.

## Original Claude assessment

# Junction-monorepon onboarding-arvio (Finnish)

Lähdecommit on 5852fa4. Arvio perustuu vain tiedostoihin. En ajanut komentoja, en tarkistanut GitHubia enkä PR-tiloja.

## 1. Tuomio ja pisteet

**Tuomio:** Dokumentaatio on selvästi suunniteltu uudelle agentille, ja polku "mistä aloitan" löytyy. Kehitysvalmius on silti heikko kolmessa asiassa. Pyydetyt kaksi kehityskohdetta (Metan skannauskaista, Stoa→NVIDIA) eivät ole checkoutissa. Palautesilmukka on manuaalinen. Dokumentit sisältävät paljon vanhentuvia tilatietoja.

| Mittari | Pisteet | Perustelu |
|---|---|---|
| Selkeys | **7/10** | Aloituspolku on yksiselitteinen (`START_HERE.md:1-21`, `AGENTS.md:7`). Omistajuus ja luottamusrajat on kuvattu tarkasti (`AGENTS.md:20-33`). Tilan erottelu (toteutettu / ehdotettu / todistamaton) on poikkeuksellisen kurinalaista (`README.md:23-29`). Miinuksena on lukuvelvoite: kaksi tiedostoa ennen työtä, sitten ARCHITECTURE ja neljä muuta dokumenttia (`AGENTS.md:9-14`). |
| Kehitysvalmius (nopea iterointi) | **4/10** | Työ on pirstoutunut avoimiin PR-haaroihin. Yhteistä CI:tä ei ole tarkoituksella. Ympäristöä ei ole kiinnitetty. Dokumentit ovat hyvin pitkiä (ks. `README.md:19`). |

## 2. Onboarding-tehtävät

| Tehtävä | Tulos | Todiste |
|---|---|---|
| Suositeltu sisäänkäynti | ✅ Selvä | `START_HERE.md:1-21`; `README.md:11-13` ja `AGENTS.md:7` osoittavat samaan. Poikkeus: `AGENTS.md:11` käskee kuitenkin lukea ensin `README.md`:n. |
| Arkkitehtuuri ja agenttien omistajuus | ✅ Hyvä | Polkukartta `README.md:48-63`; yksi kirjoittaja per yritys ja integraattori jaetuille poluille `AGENTS.md:22-25`; ID-, haara- ja ympäristökonventio `README.md:67`. |
| Toteutettu vs. ehdotettu | 🟡 Osittain | Erottelu on selkeä, mutta tilataulukot on päivätty ja vanhenevat (`README.md:17-31`, `docs/DEVELOPMENT_QUEUE.md:5-18`). Ajantasaisuus vaatii GitHub-tarkistuksen (`START_HERE.md:10-12`). |
| Metan lasiskannauskaista ja seuraava tehtävä | 🟡 Löytyy, ei toteutusta | Aloitus on `docs/META_START_HERE.md:84-87`. Toteutus (`services/meta-spatial/`) ei ole checkoutissa. Se on PR #60:ssä (`META_START_HERE.md:7`, `docs/AGENT_SOURCE_INDEX.json:312-321`). Seuraava tehtävä on kuvattu vain yhdellä lauseella: yksi oikea DAT-kuva ja audiovastaus Lens-evidenssin vastaanottoon. Tarkempi lanetaulukko on `docs/META_SPATIAL_ARCHITECTURE.md:152-158`. |
| Stoa→NVIDIA-yhteistyöpolku | 🔴 Ei mainissa | Polku on vain PR #61:ssä (`START_HERE.md:51`, `docs/AGENT_SOURCE_INDEX.json:296-311`). PR #61 kohdistuu haaraan `codex/junction-video-resume-20261113`, ei mainiin, ja sisältää PR:t 56 ja 58. `pets/stoa/CHALLENGE_RESEARCH.md` ei mainitse NVIDIAa (haku ei tuottanut osumia). Mainissa on vain kuvitteellinen rakennusdokumentin kättelytarkistin (`pets/stoa/HANDOFF_CONTRACT.md:1-3`, `:105-108`) ja yleinen synteettinen kuvaus `docs/INTER_PET_COLLABORATION.md:19`. |
| Paikalliset komennot | ✅ Löytyy | `npm ci --ignore-scripts`, `npm run validate`, `npm test`, `npm run build` (`README.md:35-42`, `AGENTS.md:47-52`). Skriptit ovat `package.json:12-35`. Kohdennetut ajot: `test:wave2`, `plugins:check`, `node --test tests/pet-<company>.test.mjs` (`AGENTS.md:54`, `HANDOFF_CONTRACT.md:107`). |
| Turvallinen luovutustyönkulku | ✅ Hyvä | Task-haara, ei suoraa pushia mainiin, riippumaton katselmoija (`AGENTS.md:24`, `:41`). Luovutuspohja `AGENTS.md:62-75` ja `START_HERE.md:20`. |

## 3. Viisi tärkeintä parannusta (vaikutusjärjestyksessä)

1. **Tuo pyydetyt kehityskohteet mainiin tai kirjaa niiden riippuvuusketju yhteen paikkaan.**
   - Kaksi pääkaistaa on PR-haaroissa: Meta PR #60 ja Stoa→NVIDIA PR #61 (`START_HERE.md:49-55`, `docs/AGENT_SOURCE_INDEX.json:296-321`).
   - Metan komennot toimivat vain PR #60:n checkoutissa (`META_START_HERE.md:51-56`).
   - PR #61 on pino: se sisältää PR:t 56 ja 58 ja kohdistuu muuhun kuin mainiin. Yksittäistä "milloin mergataan ja missä järjestyksessä" -taulukkoa ei ole.
   - Lisää taulukko: PR → base → riippuu → seuraava ratkaisu.

2. **Lisää yksi konkreettinen, ajettava "seuraava tehtävä" -kortti Metalle ja Stoa→NVIDIAlle.**
   - Metalla on vain proosarivi (`META_START_HERE.md:84-87`) ja laaja lanetaulukko, jossa omistetut polut ja hyväksymisehdot ovat yleisiä (`META_SPATIAL_ARCHITECTURE.md:152-158`).
   - Kortin sisältö: work_id, omistetut polut, komento, hyväksymiskriteeri ja estäjä. Pohjana toimii luovutusmalli `AGENTS.md:62-75`.
   - Stoa→NVIDIA-tehtävästä ei löydy mainista vastaavaa kuvausta lainkaan.

3. **Vähennä vanhenevaa tilatietoa juuridokumenteissa.**
   - README sisältää päivättyjä tilakappaleita ja taulukoita (`README.md:15-31`).
   - Jonodokumentti toistaa niitä: "1 valmis, 2 käynnissä, 31 jonossa" (`docs/DEVELOPMENT_QUEUE.md:18`).
   - Samaa tilaa toistetaan kolmessa paikassa: README, START_HERE ja JSON-indeksi. Tämä lisää ristiriitariskiä.
   - Siirrä tila yhteen koneluettavaan lähteen (`ops/*.json`) ja viittaa siihen README:stä.
   - README:n alussa on myös muotoiluvirheitä, joissa välilyönnit puuttuvat: "—13 November2026", "recordings,19", "all34" (`README.md:7-9`).

4. **Kiinnitä ympäristö ja kerro palautesilmukan nopeus.**
   - Vaatimus on vain `node >=22` (`package.json:9-11`). Hakuni löysi lähdepuusta `package-lock.json`:n, mutta ei `.nvmrc`:tä eikä `.github/`-hakemistoa. Tämä on tarkoituksellista: GitHub Actions on kielletty oletuksena (`AGENTS.md:37`).
   - Tuloksena kukaan ei näe automaattisesti, rikkoiko muutos mitään.
   - Playwright-selaintestit (`package.json:18`, `:41`) ja Python Council -ympäristö (`README.md:46`) vaativat erillistä asennusta.
   - Lisää dokumenttiin arvio ajoajoista ja tarkka "minimiajo per muutostyyppi" -taulukko. Nyt ohje on hajallaan: `AGENTS.md:43-56`, `DEVELOPMENT_QUEUE.md:25`.

5. **Pienennä pakollista lukumäärää ja ohjaa yhteen aloituspolkuun.**
   - `AGENTS.md:9-14` listaa neljä lukuvaihetta, ja START_HERE lisää omat vaiheensa (`START_HERE.md:10-21`). Järjestys on silti eri: AGENTS sanoo README ensin, START_HERE sanoo AGENTS ja ARCHITECTURE.
   - Lisäksi osa lähdelinkeistä on absoluuttisia GitHub-URL:eja kiinnitettyihin SHA:ihin, jotka eivät ole checkoutissa (`META_START_HERE.md:17-20`). Ne vaativat yksityisen repon oikeudet.
   - Lisää "5 minuutin" ensimmäinen polku ja pidä loput syventävänä.

## 4. Mitä pystyin ja en pystynyt toteamaan

**Pystyin:**
- Dokumentoidun polun, komentojen ja omistajuussääntöjen sisällön.
- Tiedostojen olemassaolon: `.github/` puuttuu, `pets/stoa/` ja `pets/nvidia/` ovat mainissa, `services/meta-spatial/` puuttuu.
- Ristiriidat ja päällekkäisyydet dokumenttien välillä.

**En pystynyt:**
- Ajamaan testejä, joten en tiedä, menevätkö `validate`, `test` tai `build` läpi, enkä niiden kestoa. Luvut 252/252, 744/744 ja 208/208 ovat dokumentin omia väitteitä sidottuina vanhoihin SHA:ihin (`README.md:19`, `META_START_HERE.md:58`).
- Varmistamaan PR #55–61:n nykytilaa. Indeksin `observedState: open` on tilannekuva (`docs/AGENT_SOURCE_INDEX.json:296-361`).
- Varmistamaan, että README:n tai START_HERE:n linkit ovat täsmälleen oikeita kaikissa 34 pakettikuvauksessa. Tarkistin vain otoksen.
- Arvioimaan toimivatko koko `ops/`-, Cloud- tai Mission Control -ketjut käytännössä.

**Erillinen havainto, jota en voinut ratkaista:** Metan koodievidenssi on sidottu commitiin `56b306b…` (`META_START_HERE.md:58-61`), mutta indeksin `runtimeCommit` on `fb90ab5…` (`docs/AGENT_SOURCE_INDEX.json:20`, `:315`). Dokumentti väittää eron olevan vain dokumentaatiomuutoksia, mutta en voinut tarkistaa sitä ilman GitHubia.

## 5. Tarkastetut tiedostot

- `START_HERE.md`, `README.md`, `AGENTS.md`
- `docs/META_START_HERE.md`, `docs/META_SPATIAL_ARCHITECTURE.md` (rivit 140–180), `docs/DEVELOPMENT_QUEUE.md` (rivit 1–40)
- `docs/AGENT_SOURCE_INDEX.json` (rivit 1–120 ja 270–360)
- `package.json`, `pets/stoa/HANDOFF_CONTRACT.md`
- Hakutulokset: hakemistolistaukset, `tests/*.mjs`, `.github/**`, `pets/stoa/`, `pets/nvidia/`, `services/meta-spatial/**`, sekä Stoa-, NVIDIA- ja Meta-viittaukset `docs/`-, `ops/`- ja `pets/`-tiedostoissa.
