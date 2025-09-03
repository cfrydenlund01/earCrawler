import json
import os
import time
from pathlib import Path

from earCrawler.telemetry import config
from earCrawler.telemetry.events import cli_run
from earCrawler.telemetry.sink_file import FileSink


def test_config_and_spool(tmp_path, monkeypatch):
    cfg_path = tmp_path / 'telemetry.json'
    monkeypatch.setenv('EAR_TELEMETRY_CONFIG', str(cfg_path))
    monkeypatch.setenv('APPDATA', str(tmp_path))
    monkeypatch.setenv('EAR_NO_TELEM_HTTP', '1')

    cfg = config.load_config()
    assert cfg.enabled is False
    assert not cfg_path.exists()

    cfg.enabled = True
    cfg.spool_dir = str(tmp_path / 'spool')
    cfg.max_file_mb = 0.0001
    cfg.max_spool_mb = 1
    config.save_config(cfg)
    assert cfg_path.exists()

    sink = FileSink(cfg)
    for _ in range(5):
        sink.write(cli_run('cmd', 1, 0))

    files = list(Path(cfg.spool_dir).glob('events-*.jsonl.gz'))
    assert files

    cfg.max_spool_mb = 0.0001
    sink.write(cli_run('cmd', 1, 0))
    assert not files[0].exists()
