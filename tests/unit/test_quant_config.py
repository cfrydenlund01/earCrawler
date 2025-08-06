import sys
from pathlib import Path

import pytest

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root))

quant_mod = pytest.importorskip("earCrawler.quant")


def _get_config():
    if hasattr(quant_mod, "QuantConfig"):
        return quant_mod.QuantConfig(bits=4)
    if hasattr(quant_mod, "get_quant_config"):
        return quant_mod.get_quant_config(bits=4)
    pytest.fail("Quantization config not found")


def test_quant_config_4bit():
    config = _get_config()
    assert config.bits == 4
    assert config.quant_type in ["nf4", "fp4"]
