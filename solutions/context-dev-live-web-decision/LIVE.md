# SupplyPulse live comparison design

The original synthetic lamp replay stays at `/`. `/live/` compares one Logitech
MX Master 3S Bluetooth Edition, manufacturer part 910-007501 / GTIN
5099206129382, from two fixed Finnish public retailer pages (Gigantti and
Proshop). No arbitrary target URL, browser action, purchase or recurring job.

Context.dev supplies the page and its publisher-authored Product JSON-LD.
Deterministic code selects the exact GTIN and ordinary EUR offer; conditional
member prices are separate. Unknown shipping and delivery remain unknown, so
the result ranks **listed item prices**, never promises the cheapest delivered
order. A retrieved page is a retailer claim, not an independently verified fact.

The server reads an optional `CONTEXT_DEV_API_KEY` from its own environment;
it only sends it to the fixed Context.dev HTTPS API and never to the browser.
Refresh is explicit, same-origin POST, two calls maximum, bounded and single
flight. A keyless host can inspect an explicitly labelled MCP capture through
the same normalization code, without exporting the connected MCP credential.
MCP captures are historical once their five-minute freshness window expires.
Their local hashes bind content, not provider authenticity.

The original PR204 admission path is retained on its existing branch. Its
40-lamp contract requires operator-calibrated confidence, exact stock, tax and
shipping and does not accept the actual provider response. This comparison
uses the verified root response/cache/JSON-LD shape instead of inventing missing
metadata or relabelling real data as synthetic.
