# Paikallinen Arduino-suunnitelman tarkistus

Tämä sovellus tarkistaa **kuvitteelliset, käyttäjän ilmoittamat tiedot**.
Se ei muodosta yhteyttä Arduinoon, mittaa antureita, ohjelmoi laitetta eikä
varmenna lähteiden tai lähtötietojen oikeellisuutta. Tulos ei ole lupa kytkeä
virtaa eikä fyysisen turvallisuuden todistus.

## Käynnistä

Aja repon juuressa:

```sh
node pets/arduino/app/server.mjs
```

Avaa selaimessa `http://127.0.0.1:4177`. Palvelin on paikallinen ja kuuntelee
oletuksena vain tämän koneen loopback-osoitteessa. Lopeta palvelin painamalla
terminaalissa **Ctrl+C**. Sovellusta ei tarvitse julkaista tai liittää
ulkopuoliseen palveluun.

## Viisi työvaihetta

1. **Muokkaa suunnitelmaa.** Ilmoita kortin ja anturien käyttöjännite ja
   logiikkajännite erikseen, pinnit, tilat, yhteinen maa sekä virtarajat.
   Esimerkit ovat keksittyjä; älä tulkitse niiden arvoja oikean kortin tiedoiksi.
2. **Tarkista ongelmat ja virtabudjetit.** Tarkistus näyttää ongelman kentän,
   ilmoitetun arvon, odotetun ehdon ja ehdotetun korjauksen. Virtabudjetit näyttävät
   ilmoitetun kuorman, rajan ja jäljelle jäävän marginaalin.
3. **Liitä kenttäkohtainen lähdemerkintä.** Kirjaa tietyn kentän alkuperä,
   lähdeosoite, revisio, lyhyt ote ja huomio. Merkinnät ovat käyttäjän väitteitä;
   sovellus ei nouda sivua tai vahvista sitä.
4. **Vertaa kahta suunnitelmaa.** Vertailu näyttää lisätyt ja poistuneet ongelmat
   sekä kokonais- ja signaalivirtamarginaalin muutoksen. Suurempi marginaali on
   laskennallinen ero ilmoitetuissa arvoissa, ei mitattu parannus.
5. **Vie tarkistusraportti.** Säilytä suunnitelma, tarkistuksen tulos,
   lähdemerkinnät, tarkistimen versio ja rajoitukset JSON- tai tekstimuodossa.
   Raportti ei sisällä käyttövaltuutusta tai turvallisuussertifikaattia.

## Suunnitelman JSON

Kopioitavat esimerkit ovat [`example-v2.json`](example-v2.json) ja vanhan
syöttömuodon [`example.json`](example.json). Uusi muoto käyttää
`schemaVersion: 2` -kenttää sekä erillisiä `supplyVoltageMv`- ja
`logicVoltageMv`-kenttiä kortille ja jokaiselle anturille. Tarkka sopimus ja
laskuesimerkki ovat tiedostossa [COMPATIBILITY.md](COMPATIBILITY.md).

Jännitteet annetaan kokonaisina millivoltteina ja virrat kokonaisina
milliampeereina. Esimerkiksi `5000` mV tarkoittaa 5 V:tä; sovellus ei muunna
merkkijonoja tai muita yksiköitä. `null` tarkoittaa tuntematonta vain kolmessa
virtarajakentässä. `0` on tunnettu nollaraja, eikä puuttuva kenttä vastaa kumpaakaan.
Negatiivinen virtamarginaali kertoo ilmoitetun rajan ylityksestä. Tuntemattoman
rajan marginaali ja sen muutos pysyvät `null`-arvoina.

JSON-tuontiin kuuluu vain dokumentoitu tietorakenne. Tuntemattomat kentät,
virheelliset lukumäärät ja yksiköt sekä ristiriitaiset jännite- tai pinnitiedot
estävät myönteisen tarkistustuloksen. Älä tuo tunnuksia, henkilötietoja tai
yksityisiä laite- tai asiakastietoja; käytä keksittyä tai redaktoitua aineistoa.

## Lähdemerkinnät

Merkintä kohdistetaan olemassa olevaan yksittäiseen kenttään, esimerkiksi
`board.supplyVoltageMv` tai `sensors[0].pins[0].currentMa`. Pelkkä `board` ei kelpaa,
koska se on kokonainen tietue. Merkkijonot, luvut, totuusarvot ja sallittu `null`
voivat olla kohdekenttiä. Merkinnässä on täsmälleen seuraavat kuusi kenttää:

```json
{
  "path": "board.supplyVoltageMv",
  "status": "fictional",
  "url": "",
  "revision": "",
  "excerpt": "",
  "note": "Keksitty harjoitusarvo, ei oikean laitteen määrittely."
}
```

| Kenttä | Enimmäispituus |
| --- | --- |
| `path` | 160 merkkiä |
| `url` | 2048 merkkiä |
| `revision` | 160 merkkiä |
| `excerpt` | 2000 merkkiä |
| `note` | 1000 merkkiä |

Merkintöjä voi olla enintään 100. Tila on `fictional`, `supplied` tai `reviewed`.
`reviewed` edellyttää ei-tyhjää HTTPS-osoitetta, revisiota, otetta ja huomiota.
Osoitteessa ei saa olla käyttäjätunnusta tai salasanaa. Muiden tilojen URL voi
olla tyhjä; jos se annetaan, samat HTTPS- ja tunnusrajat koskevat sitä.

Tuloksessa näkyvät erilliset merkinnät `FICTIONAL declaration`,
`USER-SUPPLIED unverified` ja `USER-ASSERTED reviewed`. Viimeinenkin on
**käyttäjän ilmoitus omasta tarkistuksestaan**, ei sovelluksen suorittama
verifiointi. Sovellus ei avaa lähdeosoitteita eikä nouda tietoja niistä.

## Raportin sisältö ja vertailu

Työtilan tietosyöte on `{design, evidence}`: `design` sisältää suunnitelman,
`evidence` yllä kuvatut kuusikenttäiset merkinnät. Tarkistustulos sisältää
`checkerVersion`, `review`, `evidence`, `reportText` ja `report`.
Raportin JSON:ssa on `schemaVersion: 1`, tarkistimen versio, koko suunnitelma,
tarkistustulos, lähdemerkinnät ja `limitations`. Rajat tallennetaan myös kenttiin
`synthetic: true`, `authorization: false` ja `safetyCertification: false`.
Tekstiraportti on ihmiselle luettava Markdown-yhteenveto samoista ilmoituksista.
Palautettu `attribution` on tulosteen lisäkenttä; jos kopioit merkinnän takaisin
syötteeksi, säilytä vain kuusi dokumentoitua syöttökenttää.

Vertailun syöte on `{baseline, candidate}`, jossa molemmat ovat kokonaisia
suunnitelmia. `addedIssues` ja `resolvedIssues` näyttävät ongelmakoodien eron.
`budgetChanges.total` ja `budgetChanges.signal` sisältävät lähtötilan marginaalin,
ehdotuksen marginaalin ja niiden erotuksen milliampeereina. Jos kumpi tahansa
marginaali on tuntematon, erotuskin pysyy `null`-arvona. Ristiriitojen poistuminen
ei vahvista suunnitelman todellista toimivuutta tai turvallisuutta.

## Kehitystarkistukset

Yksikkötesti: `node --test tests/pet-arduino.test.mjs`.
Selaimen läpimenotesti: `node pets/arduino/app/browser-smoke.mjs`.
Selaintesti tarvitsee repon Playwright-riippuvuuden sekä Chromiumin. Se käyttää
vain paikallista testipalvelinta ja keksittyä aineistoa. `ARDUINO_CHROMIUM_PATH`
voi osoittaa olemassa olevaan Chromiumiin. Kuvakaappaukset ja raportit tallentuvat
väliaikaishakemistoon tai `ARDUINO_BROWSER_OUTPUT`-muuttujan osoittamaan paikkaan.
Sovelluksen tavallinen käyttö tarvitsee vain Node.js:n; selaintesti ei ole sen
käynnistämisen edellytys.

## Rajat

Tämä on paikallinen suunnittelutyökalu ja synteettinen harjoitus. Se ei mallinna
johtimien tai virtalähteen todellista käyttäytymistä, toleransseja, lämpöä,
transientteja, jännitetason muunnosta tai laiteohjelmistoa. Myös `consistent`
tarkoittaa vain, että annetut ilmoitukset sopivat tämän mallin sääntöihin.
Lähdemerkinnän tila ei muuta tätä rajaa eikä myönnä työkalulle käyttöoikeuksia.
