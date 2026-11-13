# Fictional DNS snapshot review

`reviewDnsSnapshot(text)` from `dns-review.mjs` is a synchronous, deterministic,
source-only Node helper. It compares a small **supplied fictional extract**. It
does not query DNS, read hPanel, authenticate a server, diagnose a live site,
change records, perform model evaluation or activate the skills-only plugin.

## Exact input contract

Input is a primitive UTF-8 JSON string of at most 32,768 bytes. The root has
exactly `schemaVersion:1`, `scenario:"fictional"`, `owner`, `authoritative` and
`recursive`. Both views must be present: each is `null` (not supplied) or an
array of 0–16 records for that one owner. An empty array is an empty extract,
**not** NXDOMAIN, NODATA or proof of a missing live record.

Each record has exactly `type`, `value` and `ttlSeconds`. Only `A` and `CNAME`
are supported. Names use canonical lowercase ASCII hostname labels (1–63
characters, letters/digits/hyphens, no leading/trailing hyphen), total length
at most 253, with a nonempty label before `.example`. No trailing dot, URL,
wildcard, IDN or implicit normalization. A values are canonical dotted decimal
within `192.0.2.0/24`, `198.51.100.0/24` or `203.0.113.0/24`; no leading zeros.
TTL is a required integer from 0 through 2,147,483,647, or explicit `null`
(unknown). Missing TTL is invalid; unknown is never treated as zero.

Ordinary `JSON.parse` behavior applies, including last-value handling for
duplicate JSON member names; this is not a canonical JSON/signature validator.
Unknown fields, executable objects, unsupported record types and malformed
values throw `TypeError`. This restricted fixture format is not a zone-file,
wire-DNS or comprehensive hostname validator. No data is evaluated as code.

## Output and interpretation

`observations` retains view state, supplied count, sorted unique type/value
identities, duplicate count, known TTL values and unknown TTL count. Duplicate
identities are counted even when their TTL differs. TTL does not participate
in **cross-view** identity matching: a countdown difference is not a mismatch.

`findings` marks CNAME/address co-occurrence, multiple CNAME targets, a
self-referencing CNAME or conflicting known TTLs within a supplied RRset.
These are inconsistencies in the extract, not a verified production fault.
No other CNAME chains, DNSSEC records or record families are inspected.
Findings take precedence as `comparison:"input-conflict"`. Otherwise two
supplied views with at least one record yield `matching-supplied-records` or
`different-supplied-records`; a missing view or two empty views yields `unknown`.

Hypotheses always remain `unconfirmed`. A view difference cannot distinguish
time, resolver, split-view, copying or configuration differences. Two fixed
read-only next checks are **proposals**, not executed operations. `diagnosis`
stays `not-established`; live DNS, network and account flags remain false.
Even matching records cannot establish complete DNS, HTTPS or hosting health.
`example.json` deterministically produces `different-supplied-records`.

## Standards basis and scope

The small consistency rules are informed by [RFC 2181 §§5.2, 8 and
10.1](https://www.rfc-editor.org/rfc/rfc2181.html): equal TTLs within an RRset,
the TTL numeric range, and CNAME alias restrictions. This helper only compares
A/CNAME extracts; DNSSEC exceptions and complete DNS semantics are out of scope.
[RFC 5737 §3](https://www.rfc-editor.org/rfc/rfc5737.html#section-3) identifies
the three documentation IPv4 ranges; [RFC 2606 §2](https://www.rfc-editor.org/rfc/rfc2606.html#section-2)
identifies `.example` for examples. Primary references read 13 November 2026;
none establishes a Hostinger account, current product behavior or endorsement.

Run `node --test tests/pet-hostinger.test.mjs` from the repository root. All
fixtures are invented and the six authored model eval cases remain unchanged.
