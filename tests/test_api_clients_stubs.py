import pathlib, sys

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))
import inspect

from api_clients.tradegov_client import TradeGovClient
from api_clients.federalregister_client import FederalRegisterClient


def test_tradegov_client_has_lookup_entity():
    assert hasattr(TradeGovClient, "lookup_entity")
    sig = inspect.signature(TradeGovClient.lookup_entity)
    assert "query" in sig.parameters


def test_federalregister_client_has_get_ear_text():
    assert hasattr(FederalRegisterClient, "get_ear_text")
    sig = inspect.signature(FederalRegisterClient.get_ear_text)
    assert "citation" in sig.parameters
