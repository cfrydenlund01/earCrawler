param(
  [string]$WheelPath = ""
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

function Invoke-CheckedCommand {
  param(
    [Parameter(Mandatory = $true)][string]$Executable,
    [Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments
  )

  & $Executable @Arguments
  if ($LASTEXITCODE -ne 0) {
    $joined = $Arguments -join " "
    throw "Command failed with exit code ${LASTEXITCODE}: $Executable $joined"
  }
}

function Resolve-PythonInterpreter {
  if ($env:EARCTL_PYTHON -and (Test-Path $env:EARCTL_PYTHON)) {
    return $env:EARCTL_PYTHON
  }
  if ($env:pythonLocation) {
    $candidate = Join-Path $env:pythonLocation "python.exe"
    if (Test-Path $candidate) {
      return $candidate
    }
  }
  foreach ($name in "python", "python.exe", "python3", "py") {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    if ($cmd) {
      return $cmd.Source
    }
  }
  throw "Python interpreter not found on PATH."
}

$python = Resolve-PythonInterpreter

if ($WheelPath) {
  if (-not (Test-Path $WheelPath)) {
    throw "Requested wheel does not exist: $WheelPath"
  }
  $wheel = Get-Item $WheelPath
}
else {
  Invoke-CheckedCommand $python -m pip install --disable-pip-version-check --upgrade build
  Invoke-CheckedCommand $python -m build --wheel
  $wheel = Get-ChildItem dist -Filter "*.whl" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
}

if (-not $wheel) {
  throw "Wheel build failed: no wheel found in dist/."
}

$smokeRoot = Join-Path $env:TEMP ("earcrawler-wheel-smoke-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $smokeRoot | Out-Null

$savedUnsafeOverride = $env:EARCTL_ALLOW_UNSAFE_ENV_OVERRIDES
$savedUser = $env:EARCTL_USER
$savedWheelSmokeRepoRoot = $env:EARCRAWLER_WHEEL_SMOKE_REPO_ROOT

try {
  Invoke-CheckedCommand $python -m venv (Join-Path $smokeRoot ".venv")

  $venvPython = Join-Path $smokeRoot ".venv\Scripts\python.exe"
  $venvScripts = Join-Path $smokeRoot ".venv\Scripts"
  $earctl = Join-Path $venvScripts "earctl.exe"
  $kgValidate = Join-Path $venvScripts "kg-validate.exe"

  if (-not (Test-Path $venvPython)) {
    throw "Virtualenv bootstrap failed: python executable not found."
  }

  Invoke-CheckedCommand $venvPython -m pip install --disable-pip-version-check --upgrade pip
  Invoke-CheckedCommand $venvPython -m pip install --disable-pip-version-check $wheel.FullName

  if (-not (Test-Path $earctl)) {
    throw "Packaging smoke failed: earctl entrypoint was not installed."
  }
  if (-not (Test-Path $kgValidate)) {
    throw "Packaging smoke failed: kg-validate entrypoint was not installed."
  }

  $workspace = Join-Path $smokeRoot "workspace"
  New-Item -ItemType Directory -Force -Path $workspace | Out-Null
  Push-Location $workspace
  try {
    $env:EARCRAWLER_WHEEL_SMOKE_REPO_ROOT = $repoRoot
    $resourceCheck = @"
import importlib.resources as resources
from pathlib import Path
import os
import earCrawler

repo_root = Path(os.getenv("EARCRAWLER_WHEEL_SMOKE_REPO_ROOT", "")).resolve()
module_path = Path(earCrawler.__file__).resolve()
if str(module_path).lower().startswith(str(repo_root).lower()):
    raise SystemExit(f"clean-room smoke failed: imported earCrawler from source checkout ({module_path})")

required = [
    ("earCrawler.kg", "shapes.ttl"),
    ("earCrawler.kg", "shapes_prov.ttl"),
    ("earCrawler.sparql", "prefixes.sparql"),
    ("earCrawler.sparql", "kg_expand_by_section_id.rq"),
    ("service", "openapi/openapi.yaml"),
    ("service", "templates/registry.json"),
    ("service", "config/observability.yml"),
]
for package, relative_path in required:
    candidate = resources.files(package).joinpath(relative_path)
    if not candidate.is_file():
        raise SystemExit(f"packaged resource missing: {package}:{relative_path}")
    if not candidate.read_bytes():
        raise SystemExit(f"packaged resource is empty: {package}:{relative_path}")

# Prove the installed KG expansion runtime can read and execute the packaged .rq template.
from earCrawler.rag.kg_expansion_fuseki import SPARQLTemplateGateway

class _StubClient:
    def select(self, _query: str) -> dict[str, object]:
        return {"results": {"bindings": []}}

template_path = resources.files("earCrawler.sparql").joinpath("kg_expand_by_section_id.rq")
with resources.as_file(template_path) as materialized_template:
    gateway = SPARQLTemplateGateway(
        endpoint="http://localhost:3030/ear/query",
        template_path=materialized_template,
        client=_StubClient(),
    )
    rows = gateway.select(
        "kg_expand_by_section_id",
        {"section_iri": "https://example.test/resource/ear/section/EAR-736.2%28b%29"},
    )
    if rows != []:
        raise SystemExit("unexpected KG expansion smoke result")
"@
    $resourceCheckPath = Join-Path $workspace "resource_check.py"
    Set-Content -Path $resourceCheckPath -Value $resourceCheck -Encoding UTF8
    Invoke-CheckedCommand $venvPython $resourceCheckPath

    $seedCorpus = @"
from pathlib import Path
import hashlib
import json

text = "Smoke corpus paragraph for clean-room packaging validation."
digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
record = {
    "source": "ear",
    "id": "ear:SMOKE-001:0",
    "record_id": "ear:SMOKE-001:0",
    "identifier": "SMOKE-001:0",
    "sha256": digest,
    "content_sha256": digest,
    "paragraph": text,
    "text": text,
    "source_url": "https://example.test/smoke",
    "date": "2026-01-01",
    "provider": "example.test",
    "identifiers": ["SMOKE-001:0"],
}
data_dir = Path("data")
data_dir.mkdir(parents=True, exist_ok=True)
(data_dir / "ear_corpus.jsonl").write_text(json.dumps(record, sort_keys=True) + "\n", encoding="utf-8")
"@
    $seedCorpusPath = Join-Path $workspace "seed_corpus.py"
    Set-Content -Path $seedCorpusPath -Value $seedCorpus -Encoding UTF8
    Invoke-CheckedCommand $venvPython $seedCorpusPath

    $env:EARCTL_ALLOW_UNSAFE_ENV_OVERRIDES = "1"
    $env:EARCTL_USER = "test_operator"

    Invoke-CheckedCommand $earctl --version
    Invoke-CheckedCommand $venvPython -m earCrawler.cli --version
    Invoke-CheckedCommand $kgValidate --help
    Invoke-CheckedCommand $earctl corpus validate --dir data
    Invoke-CheckedCommand $venvPython -m earCrawler.cli corpus validate --dir data
  }
  finally {
    Pop-Location
  }
}
finally {
  $env:EARCTL_ALLOW_UNSAFE_ENV_OVERRIDES = $savedUnsafeOverride
  $env:EARCTL_USER = $savedUser
  $env:EARCRAWLER_WHEEL_SMOKE_REPO_ROOT = $savedWheelSmokeRepoRoot
  Remove-Item -Recurse -Force $smokeRoot -ErrorAction SilentlyContinue
}
