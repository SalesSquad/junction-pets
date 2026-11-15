"""Unit tests for the vague-time rule. Constructed Finnish strings only (no stress note, no model, no network).

    python3 -m unittest discover -s scribe/vague/tests -v
"""

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import rule as R  # noqa: E402

VAGUE = {
    # vague quantity
    "Oireet alkoivat pari viikkoa sitten.": "vague_quantity",
    "Potilas kävi terveysasemalla muutama päivä sitten.": "vague_quantity",
    "Lähete tehtiin useita kuukausia sitten.": "vague_quantity",
    "Yskä on vaivannut muutaman viime viikon ajan.": "vague_quantity",
    "Kipu alkoi puoli vuotta sitten.": "vague_quantity",
    "Hoito aloitettiin viikkoja sitten.": "vague_quantity",
    # approximate quantity
    "Oireet alkoivat noin kaksi viikkoa sitten.": "approximate_quantity",
    "Lähete lähti n. 2 vk sitten.": "approximate_quantity",
    "Kävi lääkärissä ~3 vk sitten.": "approximate_quantity",
    "Oireet alkoivat reilu viikko sitten.": "approximate_quantity",
    "Diagnoosi tehtiin vajaa kuukausi sitten.": "approximate_quantity",
    "Laihtunut kolmisen viikkoa.": "approximate_quantity",
    "Soitti ehkä viikko sitten.": "approximate_quantity",
    "Oireet jatkuneet yli kolme kuukautta.": "approximate_quantity",
    # range
    "Oireet alkoivat 2-3 viikkoa sitten.": "range",
    "Oireet alkoivat 2–3 viikkoa sitten.": "range",
    "Kävi päivystyksessä kaksi tai kolme viikkoa sitten.": "range",
    "Oireet alkoivat viikko pari sitten.": "range",
    "Lähete lähti viikko tai kaksi sitten.": "range",
    # relative period
    "Lähete lähti viime kuussa.": "relative_period",
    "Kävi vastaanotolla viime viikolla.": "relative_period",
    "Diagnoosi tehtiin viime vuonna.": "relative_period",
    "Oireet alkoivat viime viikonloppuna.": "relative_period",
    "Hoito alkoi tämän kuun alussa.": "relative_period",
    # part of period
    "Lähete saapui maaliskuun alussa.": "part_of_period",
    "Oireet alkoivat alkuvuodesta.": "part_of_period",
    "Kävi lääkärissä kuun vaihteessa.": "part_of_period",
    "Hoito alkoi vuodenvaihteessa.": "part_of_period",
    # season and holiday
    "Oireet alkoivat syksyllä.": "season",
    "Kipu alkoi alkukesästä 2025.": "season",
    "Lähete tehtiin joulun alla.": "holiday",
    "Kävi terveysasemalla juhannuksen jälkeen.": "holiday",
    "Oireet alkoivat kesälomalla.": "holiday",
    # around
    "Oireet alkoivat pääsiäisen tienoilla.": "holiday",
    "Kävi vastaanotolla helmikuun puolivälin tienoilla.": "around",
    # indefinite past
    "Kävi hiljattain terveysasemalla.": "indefinite_past",
    "Oireet alkoivat jokin aika sitten.": "indefinite_past",
    "Yskää on ollut jo pitkään.": "indefinite_past",
    "Oireillut viime päivinä.": "indefinite_past",
    # date unknown
    "Potilas ei muista tarkkaa päivää, jolloin oireet alkoivat.": "date_unknown",
    "Tarkka ajankohta on epäselvä.": "date_unknown",
    "Muistaakseen kävi lääkärissä keväällä.": "date_unknown",
}

PRECISE = [
    "Oireet alkoivat 3 viikkoa sitten.",
    "Oireet alkoivat 12 päivää sitten.",
    "Oireet alkoivat kolme viikkoa sitten.",
    "Lähete lähti seitsemän päivää sitten.",
    "Lähete lähti yhdeksän viikkoa sitten.",
    "Kävi päivystyksessä kaksitoista päivää sitten.",
    "Soitti toissapäivänä.",
    "Soitti eilen ja kävi tänään.",
    "Lähete saapui 3.2.2025.",
    "Lähete saapui 3.2.",
    "Hoito alkoi 3. marraskuuta 2025.",
    "Diagnoosi varmistui maaliskuussa 2025.",
    "Diagnoosi varmistui maaliskuussa viime vuonna.",
    "Kontrolli on keskiviikkona.",
    "Kävi vastaanotolla kesäkuussa 2025.",
    "Laihtunut noin 5 kg.",
    "Kuume yli 38 astetta.",
    "Ottaa lääkkeen parin päivän välein.",
    "Aiemmin terve, ei säännöllistä lääkitystä.",
    "Viikko sitten kävi laboratoriossa.",
    "Kuukausi sitten kävi kuvantamisessa.",
    "Asuu yksin, liikkuu kävellen, mieliala hyvä.",
    "Lähete erikoissairaanhoitoon tehtiin 14.10.2025 ja käynti oli 21.10.2025.",
    "",
]


class VagueRuleTest(unittest.TestCase):
    def test_vague_phrases_found_with_category(self):
        for text, category in VAGUE.items():
            with self.subTest(text=text):
                spans = R.find_vague(text)
                self.assertTrue(spans, text)
                self.assertIn(category, {s["category"] for s in spans}, (text, spans))
                self.assertTrue(R.is_vague(text))

    def test_precise_phrases_not_flagged(self):
        for text in PRECISE:
            with self.subTest(text=text):
                self.assertEqual(R.find_vague(text), [], text)
                self.assertFalse(R.is_vague(text))

    def test_span_maps_back_to_original_text(self):
        text = "Oireet alkoivat Pari Viikkoa sitten, ja lähete lähti viime kuussa."
        spans = R.find_vague(text)
        self.assertEqual([s["phrase"] for s in spans], ["Pari Viikkoa", "viime kuussa"])
        for s in spans:
            self.assertEqual(text[s["start"]:s["end"]], s["phrase"])

    def test_overlaps_merged(self):
        spans = R.find_vague("Oireet alkoivat noin pari viikkoa sitten.")
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0]["phrase"], "noin pari viikkoa")

    def test_relative_year_with_month_is_not_vague_but_alone_is(self):
        self.assertFalse(R.is_vague("Diagnoosi maaliskuussa viime vuonna."))
        self.assertTrue(R.is_vague("Diagnoosi viime vuonna."))

    def test_normalise_keeps_length(self):
        s = "2–3 viikkoa"
        self.assertEqual(len(R.normalise(s)), len(s))

    def test_rule_version(self):
        self.assertEqual(R.RULE_VERSION, "fi-vague-time-v1")


if __name__ == "__main__":
    unittest.main()
