from datetime import datetime
from pathlib import Path
import json

from earCrawler.monitor.state import update_state_and_write_delta, load_state
from earCrawler.kg.delta import json_to_ttl


def test_state_and_delta(tmp_path):
    state_path = tmp_path / "state.json"
    monitor_dir = tmp_path
    items = {"foo": {"name": "Foo"}}
    changed = update_state_and_write_delta(
        items, state_path, monitor_dir, timestamp=datetime(2024, 1, 1)
    )
    assert changed
    assert (monitor_dir / "delta-20240101.json").exists()
    # second run with same data should yield no change
    changed2 = update_state_and_write_delta(
        items, state_path, monitor_dir, timestamp=datetime(2024, 1, 2)
    )
    assert changed2 == {}
    # convert delta to TTL
    json_to_ttl(
        monitor_dir / "delta-20240101.json",
        tmp_path / "delta.ttl",
        tmp_path / "prov.ttl",
    )
    assert (tmp_path / "delta.ttl").read_text().strip()
