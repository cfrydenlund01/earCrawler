param([string]$ProjectRoot = '.')

$projectName = 'earCrawler'
$proj = Join-Path $ProjectRoot $projectName
if (!(Test-Path $proj)) {
    New-Item -ItemType Directory -Path $proj | Out-Null
}

$dirs = @(
    'api_clients',
    'ingestion',
    'kg',
    'retrieval',
    'fine_tuning',
    'evaluation',
    'deployment',
    'tests'
)

foreach ($d in $dirs) {
    $p = Join-Path $proj $d
    if (!(Test-Path $p)) {
        New-Item -ItemType Directory -Path $p | Out-Null
    }
}

@" 
requests==2.28.1
rdflib==6.2.0
python-dotenv==0.21.0
pytest==7.3.1
"@ | Set-Content (Join-Path $proj 'requirements.txt')

$readme = @" 
# $projectName

## Installation
```PowerShell
python -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
```

## Usage
```Python
from api_clients.tradegov_client import TradeGovClient
from api_clients.federalregister_client import FederalRegisterClient

tg = TradeGovClient()
countries = tg.list_countries()

fr = FederalRegisterClient()
docs = fr.list_documents({'per_page': 5})
```

Store API keys in Windows Credential Manager or your OS vault. Never hardcode them.
"@
$readme | Set-Content (Join-Path $proj 'README.md')

$changelog = @" 
# Changelog

## v0.1.0
- Initial project structure and dependencies.
"@
$changelog | Set-Content (Join-Path $proj 'CHANGELOG.md')

$gitignore = @" 
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
share/python-wheels/
*.egg-info/
.installed.cfg
*.egg
MANIFEST

# Unit test / coverage reports
htmlcov/
.tox/
.nox/
.coverage
.cache
nosetests.xml
coverage.xml
*.cover
*.py,cover
.hypothesis/
.pytest_cache/

# Environments
.env
.venv
env/
venv/
ENV/
venv.bak/

# Editors
.vscode/
.idea/
"@
$gitignore | Set-Content (Join-Path $proj '.gitignore')

Write-Output 'Reminder: tag the initial commit as v0.1.0 and create a test stub under tests/'

