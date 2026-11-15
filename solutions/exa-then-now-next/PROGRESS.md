# Progress

Imported from SalesSquad/internet-butler at 582bcfc99efd (15 Nov 2026); that repository stays the development home for now.
Run: `npm ci && npm run dev:live` (needs local keys, see README). Tests: `npm test` (99 tests, 96 pass, 3 skipped at import).
Not imported: model weights, datasets, local indexes (git-ignored; copies in iCloud `Events/Junction-2026/`).
15 Nov 2026: listwise clause judge synced from internet-butler #1 (d0e71d7) and #2 (ce48cc0): `gpu/train_list.py`, `gpu/train_group.py --dump-scores`, `gemma/mlx_list*.py`, `gemma/mlx_lk_eval.py`, `gpu/verda/`, `bench/situations/listwise/` (protocol, policy selection, results: test 77.9 % vs B0 73.2 %, on-device 77.5 %). Adapters and run outputs: iCloud `Events/Junction-2026/Models/gemma4b-judge3-20261115`.
Next: public address for the butler page; Chibi app slot is SalesSquad/chibi PR 139.
