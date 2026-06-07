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

