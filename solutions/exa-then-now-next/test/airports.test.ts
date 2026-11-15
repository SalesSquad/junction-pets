import assert from "node:assert/strict";
import { test } from "node:test";
import { flightNote, flightRoute } from "../src/timetravel/airports.ts";

test("flight distance from the two places named, in English, Finnish and German", () => {
  const hp = flightRoute("My flight from Helsinki to Paris was cancelled yesterday")!;
  assert.equal(hp.from, "Helsinki"); assert.equal(hp.to, "Paris");
  assert.ok(hp.km > 1850 && hp.km < 1950, String(hp.km));
  assert.equal(hp.intraEu, true);
  const fi = flightRoute("Lentoni Helsingistä Roomaan peruttiin")!;
  assert.ok(fi.km > 2150 && fi.km < 2300, String(fi.km));
  const de = flightRoute("Mein Flug von Berlin nach München wurde annulliert")!;
  assert.ok(de.km > 450 && de.km < 520, String(de.km));
  const ny = flightRoute("I was denied boarding on a flight from Paris to New York")!;
  assert.equal(ny.intraEu, false); assert.ok(ny.km > 5700 && ny.km < 5950, String(ny.km));
  assert.equal(flightRoute("My flight from Helsinki to Las Palmas was cancelled")!.to, "Gran Canaria");
  // Not a flight, one place, or three places: nothing is assumed.
  assert.equal(flightRoute("I moved from Helsinki to Paris for work"), undefined);
  assert.equal(flightRoute("My flight to Paris was late"), undefined);
  assert.equal(flightRoute("My flight from Helsinki to Rome via Frankfurt was cancelled"), undefined);
  // A stated distance wins; a route near a tier boundary is named but not given a number.
  assert.equal(flightNote("My flight from Helsinki to Paris (1,900 km) was cancelled"), "");
  assert.match(flightNote("My flight from Helsinki to Paris was cancelled"), /about 19\d0 km; both airports are within the EU/);
  assert.match(flightNote("My flight from Helsinki to Amsterdam was cancelled"), /close to a distance tier boundary/);
});
