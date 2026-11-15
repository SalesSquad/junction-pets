# Offline review evidence

The final 25-test file run against unchanged checker `6611a06799e009d35631941708cceece877ca27a`
produced RED: exit 1, tests 25, pass 3, fail 22, skipped 0. The improved checker
produced GREEN: exit 0, tests 25, pass 25, fail 0, skipped 0.

The mutation harness returned exit 0: its baseline 25 tests passed and all six
syntax-valid mutants caused their selected named assertion to fail (exit 1).
These cover duplicate pins, supply voltage, logic voltage, per-pin current,
total current and aggregate signal current. This is a finite sensitivity check,
not a claim of comprehensive correctness or real-device qualification.

Raw RED and mutation logs contain Node's whitespace-only assertion formatting.
Their byte-for-byte Base64 representations avoid altering that evidence or
introducing trailing whitespace into the source diff. GREEN remains plain text.

| Encoded artifact | Decoded bytes | Decoded SHA256 |
| --- | --- | --- |
| `input-hardening-red.log.b64` | 4087 | `49fbd0e8aa784751d2293fef1f77ab11c45cd9ce7314f65462c1f9f99050b6ec` |
| `review-v2-red.log.b64` | 25768 | `3ea884b3b2389b743686015c9df75c20f43b8b9de7646b4d3faf06d7eb4a007f` |
| `review-v2-mutations.log.b64` | 14173 | `ec04707864e05d200fd84d389c88c6ed09ae9c0162455b28b2fb98997e3b2956` |

Decode from repository root, substituting the desired artifact name:

```sh
python3 -c 'import base64,pathlib,sys; sys.stdout.buffer.write(base64.b64decode(pathlib.Path("pets/arduino/evidence/review-v2-red.log.b64").read_bytes()))'
```

These development logs precede the final committed-head qualification. The PR
handoff separately records the exact final SHA, command results and raw-log
hashes. Temporary paths in logs are historical scratch locations, not external
attachments. The earlier input-hardening RED log also uses Base64 to preserve
its whitespace byte-for-byte; its original remains in commit `6611a06`.
Other earlier evidence files remain unchanged.
