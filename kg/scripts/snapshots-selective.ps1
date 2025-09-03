param(
    [string]$ChangedPath,
    [string]$TagMapPath = 'kg/queries/tag-map.json'
)

$python = 'python'
$py = @'
import json, sys
from pathlib import Path
from earCrawler.kg.delta import select_impacted_queries
changed = json.load(open(sys.argv[1]))
tag_map = json.load(open(sys.argv[2]))
impacted = select_impacted_queries(changed, tag_map)
Path('kg/snapshots/impacted.txt').write_text('\n'.join(impacted)+'\n', encoding='utf-8')
'@
& $python -c $py $ChangedPath $TagMapPath
