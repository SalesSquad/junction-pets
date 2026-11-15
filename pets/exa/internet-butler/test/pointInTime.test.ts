import assert from "node:assert/strict";
import { test } from "node:test";
import { isPointInTimeUrl, lawOn, officialFetch, pointInTimeUrl } from "../src/warrant/pointInTime.ts";

test("point-in-time URLs for eCFR and legislation.gov.uk", () => {
  const e = pointInTimeUrl({ source: "ecfr", title: 14, part: 250, section: "250.5" }, "2021-04-13");
  assert.equal(e, "https://www.ecfr.gov/api/versioner/v1/full/2021-04-13/title-14.xml?part=250&section=250.5");
  const u = pointInTimeUrl({ source: "ukleg", path: "uksi/2015/621/regulation/4" }, "2019-04-02");
  assert.equal(u, "https://www.legislation.gov.uk/uksi/2015/621/regulation/4/2019-04-02/data.xml");
  assert.ok(isPointInTimeUrl(e) && isPointInTimeUrl(u));
  assert.equal(isPointInTimeUrl("https://www.legislation.gov.uk/uksi/2015/621/regulation/4"), false);
  assert.throws(() => pointInTimeUrl({ source: "ecfr", title: 14, part: 250, section: "250.5" }, "2021-4-13"));
});

test("legislation.gov.uk: only the Body is law text; metadata is dropped", async () => {
  const xml = `<Legislation><Metadata><dc:title>The National Minimum Wage Regulations 2015</dc:title><Note>Expert Participation 2019-04-01</Note></Metadata><Body><P1group><Title>The national living wage</Title><P1><Pnumber>4</Pnumber><Text>The single hourly rate ... is &#163;8.21<CommentaryRef Ref="c1"/>.</Text></P1></P1group></Body></Legislation>`;
  const raw = async () => new Response(xml, { status: 200 });
  const law = await lawOn({ source: "ukleg", path: "uksi/2015/621/regulation/4" }, "2019-04-02", raw as any);
  assert.equal(law.text, "The national living wage 4 The single hourly rate ... is £8.21.");
  assert.ok(!law.text.includes("Expert Participation"));
  await assert.rejects(officialFetch(raw as any)("https://example.com/page"), /not an official point-in-time URL/);
});
