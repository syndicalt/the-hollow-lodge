import json
import stat

from hollow_lodge.client.config import ClientConfig, save_config, load_config


def test_client_config_round_trips_with_owner_only_permissions(tmp_path):
    path = tmp_path / "config.json"
    config = ClientConfig(
        server_url="http://127.0.0.1:8000",
        player_id="player_ada",
        token="secret-token",
    )

    save_config(path, config)

    assert load_config(path) == config
    mode = stat.S_IMODE(path.stat().st_mode)
    assert mode == 0o600


def test_client_config_loads_legacy_file_without_display_name(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "server_url": "http://127.0.0.1:8000",
                "player_id": "player_ada",
                "token": "secret-token",
            }
        ),
        encoding="utf-8",
    )

    assert load_config(path) == ClientConfig(
        server_url="http://127.0.0.1:8000",
        player_id="player_ada",
        token="secret-token",
        display_name=None,
    )
