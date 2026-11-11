# Chibi-integraatio

Tämä repo omistaa 34 yrityspetin versionoidut sisällöt ja tapahtumakatalogin. `SalesSquad/chibi` omistaa käyttäjätilin, profiilin, markkinapaikan, adoption, käyttöoikeudet ja keskustelun. QR on julkinen navigointilinkki; se ei sisällä kirjautumistunnusta, kutsun salaista tokenia tai tilin käyttöoikeutta.

## Lähdesopimus

Sovitin perustuu Chibin lähteeseen `243c272c13668418decd67af3a9b88566927d5ee`. Tarkastetut ensisijaiset lähteet:

- `docs/adr/0008-source-contract.md`
- `crates/chibi-manifest/src/lib.rs` ja `schemas/chibi-manifest.schema.json`
- `crates/chibi-api/src/maker.rs`, `schemas/openapi.json`
- `web/features/customer-journey.tsx`, `first-adoption-consumer.tsx`, `den.tsx` ja `selected-conversation.tsx`

Upstream-manifestiskeeman muuttamaton kopio on `schemas/chibi-manifest.upstream.schema.json`. Sen lähde on [Chibin pinattu skeema](https://github.com/SalesSquad/chibi/blob/243c272c13668418decd67af3a9b88566927d5ee/schemas/chibi-manifest.schema.json). Skeema- ja paikalliset testit eivät todista palvelimen hyväksyntää.

## Julkinen kokoelma

`npm run build --workspace @chibi/junction-catalog -- --base=/junction/` tuottaa staattisen sovelluksen. Aja ensin `npm run catalog` samalla puhtaalla commitilla. `node scripts/package-chibi.mjs` kokoaa tiedostot polkuun `dist/chibi/web/public/junction/` ja kirjoittaa `collection.lock.json`-tiedoston. Lukko sisältää lähdecommitin, 34 paketin tiivisteet ja jokaisen julkaistavan tiedoston tiivisteen.

Kopioi tämä hakemisto Chibin erillisen integraatiohaaran `web/public/junction/`-hakemistoksi. Chibin Marketplaceen lisätty Junction-kokoelmalinkki avaa `/junction/index.html`. Linkki näkyy myös markkinapaikan palveluvirheen aikana. Näin vierailija voi tutustua yritysten profiileihin ja ohjeisiin ilman näennäisiä julkaistuja backend-tuotteita.

Katalogin `host-config.json` on julkaisijan ei-salainen konfiguraatio. Sen `runtimeStatus` on nyt `unverified`, `publishedSlugs` on tyhjä ja `verifiedAt` on null. Vastaanottajan painike pysyy pois käytöstä. Pelkkä konfiguraation syntaksi ei ole julkaisu- tai käyttöoikeusnäyttöä. Varmennustilaa saa päivittää vasta saman palvelinjulkaisun todellisten vastaanottajatestien jälkeen.

## Yrityspaketti Makeriin

Täytä `config/host-bindings.example.json`-mallin kentät olemassa olevan Chibi-isännän todennetuilla **ei-salaisilla** mallin, providerin, alueen, tietosuojakäytännön ja säilytysajan sidonnoilla. Tyhjät oletukset estävät tuonnin. Älä siirrä avaimia tähän repoon.

```sh
npm run prepare:import -- /absolute/path/verified-host-bindings.json
```

Komento tuottaa 34 tarkastettavaa ehdokasta `dist/import-candidates/`-hakemistoon. Se ei lähetä pyyntöjä. Ehdokas sisältää yritysidentiteetin, paketin tiivisteen, manifestin tarkat JSON-tavut ja koko Maker-pyynnön tiivisteen. Manifestiin ei lisätä toteuttamattomia yritysliittymiä: `tools` on tyhjä. Kukin järjestelmäohje saa vain kyseisen yrityksen ohjeet ja päivätyt lähdemuistiinpanot.

Isännän autentikoitu sovitin voi käyttää `createMakerDraft(candidate, {request})`-funktiota yhden nimenomaisen `POST /v1/maker/products`-pyynnön tekemiseen. Sitä ennen tarkistetaan koko ehdokas ja otetaan muuttumaton kopio. Vastaus merkitään ainoastaan `draft-response-received`-tilaan; sen sisältöä ei väitetä todennetuksi julkaisu- tai runtime-kuitiksi. Epäselvä lopputulos jää `unknown`-tilaan ilman automaattista uusintaa. Rekonsiloi palvelimelta ennen uutta luontia.

Olemassa oleva Maker-submit ja julkaisuputki ovat erilliset. Allekirjoitus, hyväksytty versio, käyttöoikeus, palvelimen sallima malli ja käynnissä oleva worker tarvitaan Chibissä. Katalogin synteettisiin testiriveihin lisääminen ei julkaise pettiä.

## Vastaanottajan polku

| Vaihe | Olemassa oleva Chibi-raja | Todiste, joka tarvitaan |
|---|---|---|
| QR | `/en/chibi/junction-<company>` | Sama yritys ja julkaistu versio avautuvat |
| Kirjautuminen | `/en/signin?next=<same-origin-detail>` | Paluu säilyttää valitun yrityksen |
| Oma profiili | `GET/PATCH /v1/me` | Palvelimen vahvistama käyttäjä ja tenant |
| Tarjous | `POST /v1/adoption-offers` | Tarkat ehdot, hinta ja versiotiiviste |
| Oma petti | `POST /v1/adoptions` | Käyttäjä hyväksyy juuri näytetyn tarjouksen alkuperäisellä idempotency-avaimella |
| Oikean petin avaus | `/en/den?adoption=<id>` | Tuore tenant-rajattu detail GET palauttaa täsmälleen saman adoption |
| Aktivointi | activation-readiness ja activate | Nykyinen revision ja palvelimen todelliset oikeudet |
| Keskustelu | olemassa oleva SelectedConversation | Mallivastaus valmistuu ja säilyy historiassa |

`202 admitted_pending` on työn vastaanottokuitti, ei mallin vastaus. Käyttäjä-, profiili-, lataus- tai petinvaihto mitätöi vanhat vastaukset. Väärä tai puuttuva adoption tunniste ei saa avata listan ensimmäistä pettiä. Yrityksen julkinen QR ei ole yksityinen kertakäyttökutsu.

## Avoin julkaisuportti

Nykyinen lähdesopimus tukee nollahintaista, erikseen määritettyä 1–90 päivän kokeilutarjousta. Se ei vahvista pysyvää ilmaista omistusoikeutta. Tapahtumapetin käyttöaika ja rahoitus on sidottava oikeaan palvelimen entitlement-politiikkaan ennen tarjousten julkaisua.

Tässä työssä ei ole varmennettu 34 tuotteen julkaisuja, tapahtumavieraan tiliä, mallin live-vastausta, provider-kuluja tai julkista käyttöoikeutta. Nykyisen Sites-isännän ulkopuoliset HTTP-pyynnöt pysähtyivät pääsynvalvontaan. Koodin yhdistäminen ja tuotantojulkaisu tarvitsevat erillisen käyttäjän valtuutuksen; niitä ei korvata asiakkaan konfiguraatiobitillä.
