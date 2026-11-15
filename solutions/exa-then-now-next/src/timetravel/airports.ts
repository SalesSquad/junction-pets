/**
 * Flight distance from the places a person names, so "my flight from Helsinki to Paris was cancelled" can be
 * placed in a distance tier without the person knowing the kilometres. Great-circle distance between the
 * cities' main airports, which is the method Regulation 261/2004 prescribes (Art. 7(4)).
 *
 * Conservative on purpose: used only when exactly two known places are named, and not when the distance is
 * within 4 % of a tier boundary (1,500 or 3,500 km), where the exact airports decide.
 */
// [name stems (lower case; a stem may be followed by a case ending), latitude, longitude, EU/EEA/Switzerland (Regulation 261/2004 applies as to a Member State)]
const PLACES: Array<[string[], number, number, boolean, string]> = [
  [["helsinki", "helsingi", "helsingfors"], 60.317, 24.963, true, "Helsinki"], [["oulu"], 64.930, 25.355, true, "Oulu"], [["rovaniem"], 66.565, 25.830, true, "Rovaniemi"], [["tampere"], 61.414, 23.604, true, "Tampere"], [["turku", "turu"], 60.514, 22.263, true, "Turku"],
  [["stockholm", "tukholma"], 59.652, 17.919, true, "Stockholm"], [["gothenburg", "göteborg"], 57.663, 12.280, true, "Gothenburg"], [["copenhagen", "kööpenhamina", "kopenhagen", "københavn"], 55.618, 12.656, true, "Copenhagen"], [["oslo"], 60.194, 11.100, true, "Oslo"], [["reykjav", "keflav"], 63.985, -22.606, true, "Reykjavik"],
  [["tallinn"], 59.413, 24.833, true, "Tallinn"], [["riga", "riika"], 56.924, 23.971, true, "Riga"], [["vilnius", "vilna"], 54.634, 25.286, true, "Vilnius"], [["warsaw", "varsova", "warschau", "warszaw"], 52.166, 20.967, true, "Warsaw"], [["krak"], 50.078, 19.785, true, "Kraków"], [["gda"], 54.378, 18.466, true, "Gdańsk"],
  [["london", "lontoo"], 51.470, -0.454, false, "London"], [["manchester"], 53.354, -2.275, false, "Manchester"], [["edinburgh", "edinburg"], 55.950, -3.373, false, "Edinburgh"], [["dublin"], 53.421, -6.270, true, "Dublin"],
  [["paris", "pariisi"], 49.010, 2.548, true, "Paris"], [["nice", "nizza"], 43.658, 7.216, true, "Nice"], [["lyon"], 45.726, 5.091, true, "Lyon"], [["amsterdam"], 52.308, 4.764, true, "Amsterdam"], [["brussels", "bryssel", "brüssel", "bruxelles"], 50.901, 4.484, true, "Brussels"],
  [["frankfurt"], 50.033, 8.570, true, "Frankfurt"], [["munich", "münchen", "munchen"], 48.354, 11.786, true, "Munich"], [["berlin", "berliini"], 52.366, 13.503, true, "Berlin"], [["hamburg", "hampuri"], 53.630, 9.988, true, "Hamburg"], [["düsseldorf", "dusseldorf"], 51.289, 6.767, true, "Düsseldorf"],
  [["vienna", "wien"], 48.110, 16.570, true, "Vienna"], [["zurich", "zürich"], 47.458, 8.555, true, "Zurich"], [["geneva", "geneve", "genf"], 46.238, 6.109, true, "Geneva"], [["prague", "praha", "prag"], 50.101, 14.260, true, "Prague"], [["budapest"], 47.437, 19.256, true, "Budapest"], [["bucharest", "bukarest"], 44.572, 26.102, true, "Bucharest"], [["sofia"], 42.697, 23.411, true, "Sofia"],
  [["madrid"], 40.472, -3.561, true, "Madrid"], [["barcelona"], 41.297, 2.078, true, "Barcelona"], [["malaga", "málaga"], 36.675, -4.499, true, "Málaga"], [["alicante"], 38.282, -0.558, true, "Alicante"], [["palma", "mallorca"], 39.552, 2.739, true, "Palma"], [["las palmas", "gran canaria"], 27.932, -15.387, true, "Gran Canaria"], [["tenerife", "teneriffa"], 28.045, -16.572, true, "Tenerife"],
  [["lisbon", "lissabon", "lisboa"], 38.774, -9.134, true, "Lisbon"], [["porto"], 41.248, -8.681, true, "Porto"], [["faro"], 37.014, -7.966, true, "Faro"],
  [["rome", "rooma", "roma"], 41.800, 12.239, true, "Rome"], [["milan", "milano", "mailand"], 45.630, 8.723, true, "Milan"], [["venice", "venetsia", "venedig", "venezia"], 45.505, 12.352, true, "Venice"], [["athens", "ateena", "athen"], 37.936, 23.944, true, "Athens"], [["malta"], 35.857, 14.478, true, "Malta"], [["larnaca", "larnaka"], 34.875, 33.625, true, "Larnaca"], [["zagreb"], 45.743, 16.069, true, "Zagreb"], [["dubrovnik"], 42.561, 18.268, true, "Dubrovnik"],
  [["istanbul"], 41.275, 28.752, false, "Istanbul"], [["antalya"], 36.899, 30.800, false, "Antalya"], [["tel aviv"], 32.011, 34.887, false, "Tel Aviv"], [["cairo", "kairo"], 30.122, 31.406, false, "Cairo"], [["dubai"], 25.253, 55.366, false, "Dubai"], [["doha"], 25.273, 51.608, false, "Doha"],
  [["new york", "nyc"], 40.641, -73.778, false, "New York"], [["boston"], 42.366, -71.010, false, "Boston"], [["washington"], 38.953, -77.457, false, "Washington"], [["chicago"], 41.974, -87.907, false, "Chicago"], [["miami"], 25.796, -80.287, false, "Miami"], [["los angeles"], 33.942, -118.409, false, "Los Angeles"], [["san francisco"], 37.619, -122.375, false, "San Francisco"], [["toronto"], 43.677, -79.625, false, "Toronto"],
  [["tokyo", "tokio"], 35.772, 140.393, false, "Tokyo"], [["seoul", "soul"], 37.460, 126.441, false, "Seoul"], [["beijing", "peking", "pekin"], 40.080, 116.585, false, "Beijing"], [["shanghai"], 31.143, 121.805, false, "Shanghai"], [["hong kong", "hongkong"], 22.308, 113.918, false, "Hong Kong"], [["singapore", "singapur"], 1.364, 103.991, false, "Singapore"], [["bangkok"], 13.690, 100.750, false, "Bangkok"], [["delhi"], 28.556, 77.100, false, "Delhi"], [["sydney"], -33.940, 151.175, false, "Sydney"],
];
const rad = (d: number) => (d * Math.PI) / 180;
const km = (a: [number, number], b: [number, number]) => {
  const h = Math.sin(rad(b[0] - a[0]) / 2) ** 2 + Math.cos(rad(a[0])) * Math.cos(rad(b[0])) * Math.sin(rad(b[1] - a[1]) / 2) ** 2;
  return 2 * 6371 * Math.asin(Math.sqrt(h));
};

export interface FlightRoute { from: string; to: string; km: number; intraEu: boolean; nearBoundary: boolean }

/** The route of a flight named in the text, when exactly two known places are named; otherwise undefined. */
export function flightRoute(text: string): FlightRoute | undefined {
  const t = text.toLowerCase();
  if (!/flight|flew|fly|plane|airline|airport|boarding|bumped|lento|lennon|lensin|kone|flug|flieg|flughafen/.test(t)) return undefined;
  const found: Array<{ at: number; i: number }> = [];
  // Longest names first, and a matched span is blanked, so "Las Palmas" is not also read as "Palma".
  let rest = t;
  const stems = PLACES.flatMap(([ss], i) => ss.map((s) => ({ s, i }))).sort((a, b) => b.s.length - a.s.length);
  for (const { s, i } of stems) {
    if (found.some((f) => f.i === i)) continue;
    const m = new RegExp(`(^|[^\\p{L}])${s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\p{L}{0,6}(?=$|[^\\p{L}])`, "u").exec(rest);
    if (m) {
      found.push({ at: m.index, i });
      rest = rest.slice(0, m.index) + " ".repeat(m[0].length) + rest.slice(m.index + m[0].length);
    }
  }
  if (found.length !== 2) return undefined;
  found.sort((a, b) => a.at - b.at);
  const [A, B] = [PLACES[found[0]!.i]!, PLACES[found[1]!.i]!];
  const d = Math.round(km([A[1], A[2]], [B[1], B[2]]) / 10) * 10;
  return { from: A[4], to: B[4], km: d, intraEu: A[3] && B[3], nearBoundary: [1500, 3500].some((x) => Math.abs(d - x) / x < 0.04) };
}

/** The sentence added to the situation for code and judges, or "" when no route is recognised or the person already states a distance. */
export function flightNote(text: string): string {
  if (/\d\s*(km|kilomet|miles?\b|mi\b)/i.test(text)) return "";
  const r = flightRoute(text);
  if (!r) return "";
  return r.nearBoundary
    ? ` (Computed: ${r.from} to ${r.to} is close to a distance tier boundary; the exact airports decide.${r.intraEu ? " Both are within the EU/EEA." : ""})`
    : ` (Computed from airport coordinates: the flight distance ${r.from} to ${r.to} is about ${r.km} km${r.intraEu ? "; both airports are within the EU/EEA, so it is an intra-Community flight" : "; not an intra-Community flight"}.)`;
}
