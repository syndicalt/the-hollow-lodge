# The Hollow Lodge

The Hollow Lodge is an asynchronous occult-heist multiplayer game for
LLM-native command-line clients.

The first implementation target is a vertical slice of the approved design:
invite-code identity, first-party brokered chat, two crews contesting
The Saint's False Finger, freeform-first action submission, proof dossiers,
phase resolution, and Eventloom-backed authoritative/local logs.

## Development

Run tests:

```bash
pytest
```

Show CLI help:

```bash
python -m hollow_lodge.client.cli --help
```

Start the development server:

```bash
uvicorn hollow_lodge.server.app:app --reload
```

## Starter Vertical Slice

The first playable slice is covered by an end-to-end test:

```bash
pytest tests/e2e/test_saints_and_ledgers_preview.py -q
```

It proves the current loop:

- two invited players register and create The Moth Choir and The Gilt Knives
- Saints & Ledgers / The Saint's False Finger appears on the contract board
- Moth transfers a copied ledger fragment to Gilt
- Gilt spends a provenance side action
- Moth sends a targeted crew-to-crew offer
- a local Handler deal draft is written only to the local perspective log
- both crews submit freeform actions and update proof dossiers
- Auction Preview locks and resolves with Gilt in a strong lead
- both players sync visible events into local JSONL perspective logs

Useful CLI commands while a dev server is running:

```bash
python -m hollow_lodge.client.cli register --server http://127.0.0.1:8000 --invite <code> --name <name>
python -m hollow_lodge.client.cli contracts
python -m hollow_lodge.client.cli inbox
python -m hollow_lodge.client.cli sync
python -m hollow_lodge.client.cli replay --since 0
```
