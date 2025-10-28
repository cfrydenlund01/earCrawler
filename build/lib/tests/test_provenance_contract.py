"""Integration test for provenance contract.

Requires PowerShell 7 (``pwsh``) and a Java runtime to be installed and on
the PATH. The Apache Jena and Fuseki tools are downloaded on demand.
"""

import json
import os
import pathlib
import subprocess
import shutil
import sys

import pytest

from .java_utils import JAVA_VERSION_OK
from .tooling import require_jena_and_fuseki

if sys.platform != "win32":
    pytest.skip("Windows-only", allow_module_level=True)

if shutil.which("pwsh") is None:
    pytest.fail(
        "PowerShell 7 (pwsh) is required to run the provenance contract test. "
        "Install pwsh and ensure it is on the PATH.",
        pytrace=False,
    )

if not JAVA_VERSION_OK:
    pytest.fail(
        "Java 17 or newer is required to run the provenance contract test. "
        "Update the installed Java runtime and try again.",
        pytrace=False,
    )

from rdflib import ConjunctiveGraph

from earCrawler.kg.emit_ear import emit_ear
from earCrawler.kg.triples import emit_tradegov_entities
from earCrawler.kg.prov import new_prov_graph, write_prov_files

# Requires SHACL/OWL tooling; see README.md#setup-for-shaclowl-validation.

KG_DIR = pathlib.Path('kg')
SCRIPT_SHACL = KG_DIR / 'scripts' / 'ci-shacl-owl.ps1'
SCRIPT_PROV = KG_DIR / 'scripts' / 'ci-provenance.ps1'
MISSING_TOOLS_MSG = (
    "The Apache Jena and Fuseki tools must be downloaded before running "
    "the provenance contract test."
)


def test_provenance_contract(tmp_path):
    jena_dir, fuseki_dir = require_jena_and_fuseki(MISSING_TOOLS_MSG)
    prov_g = new_prov_graph()
    fixture_dir = pathlib.Path('tests/kg/fixtures')
    emit_ear(fixture_dir, KG_DIR, prov_graph=prov_g)
    records = [
        {
            'id': 'acme',
            'name': 'ACME Corp',
            'country': 'US',
            'source_url': 'https://trade.gov/api/acme',
            'date': '2024-01-01',
            'sha256': '0' * 64,
        }
    ]
    emit_tradegov_entities(records, KG_DIR, prov_graph=prov_g)
    write_prov_files(prov_g, KG_DIR / 'prov')
    # combine domain TTLs
    domain = KG_DIR / 'ear_triples.ttl'
    with domain.open('w', encoding='utf-8') as out:
        out.write((KG_DIR / 'ear.ttl').read_text())
        out.write((KG_DIR / 'tradegov.ttl').read_text())

    env = {
        **os.environ,
        "JENA_HOME": str(jena_dir),
        "FUSEKI_HOME": str(fuseki_dir),
    }
    subprocess.run(['pwsh', str(SCRIPT_SHACL)], check=True, env=env)
    conf = (KG_DIR / 'reports' / 'shacl-conforms.txt').read_text().strip()
    assert conf == 'true'

    subprocess.run(['pwsh', str(SCRIPT_PROV)], check=True, env=env)
    info = json.loads(
        (KG_DIR / 'reports' / 'lineage-min-required.srj').read_text()
    )
    assert int(info['results']['bindings'][0]['cnt']['value']) == 0
    info2 = json.loads(
        (KG_DIR / 'reports' / 'lineage-activity-integrity.srj').read_text()
    )
    assert info2['boolean'] is False
    sample = json.loads(
        (KG_DIR / 'reports' / 'lineage-source-consistency.srj').read_text()
    )
    assert sample['results']['bindings'], 'expect sample rows'

    g = ConjunctiveGraph()
    g.parse(domain, format='turtle')
    g.parse(KG_DIR / 'prov' / 'prov.ttl', format='turtle')
    q = open(KG_DIR / 'queries' / 'lineage_min_required.rq').read()
    res = list(g.query(q))
    assert int(res[0][0]) == 0
