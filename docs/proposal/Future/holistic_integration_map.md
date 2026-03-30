# Holistic Integration Map For Future earCrawler Projects

Date: 2026-03-30
Status: Proposal-only planning map

## Planning Premise

earCrawler should remain an export-control-first system until the production CLI
for crawling and normalizing export-control laws is complete and stable.

That means the future proposals in this folder should be treated as
capabilities layered around the current core, not as a replacement for it.
The useful idea in the existing scaffold is the module inventory; the part that
should not drive implementation is the proposal to retire the export-control
domain and rebuild the product as a generic research-compliance tool.

## Recommended North Star

Build earCrawler into an export-control control plane with adjacent
research-security and research-compliance modules.

The system should answer five connected questions:

1. What do the governing export-control and research-security authorities say?
2. Which people, organizations, sponsors, projects, publications, and assets
   are connected to that guidance?
3. Which of those connections create screening, disclosure, ethics, training,
   cybersecurity, or audit obligations?
4. What evidence supports each flag or clearance decision?
5. What operator action is required next?

## Holistic Architecture Map

```text
                    +--------------------------------------+
                    |  Authoritative Law And Policy Layer  |
                    |  EAR, FR, CSL, NDAA, OFAC, BIS, UTS  |
                    +-------------------+------------------+
                                        |
                                        v
                    +--------------------------------------+
                    |  Ingestion And Normalization Layer   |
                    |  jobs/corpus/kg pipelines, identity  |
                    |  resolution, provenance, manifests    |
                    +-------------------+------------------+
                                        |
        +-------------------------------+-------------------------------+
        |                               |                               |
        v                               v                               v
+---------------+             +-------------------+            +-------------------+
| Screening KG  |             | Research Intel KG |            | Institutional KG  |
| entities,     |             | journals, papers, |            | IRB, training,    |
| lists, rules, |             | coauthors, ORCID, |            | grants, COI,      |
| jurisdictions |             | affiliations      |            | data classes      |
+-------+-------+             +---------+---------+            +---------+---------+
        |                               |                                |
        +-------------------------------+--------------------------------+
                                        |
                                        v
                    +--------------------------------------+
                    |  Risk And Review Engine              |
                    |  screening, graph expansion,         |
                    |  evidence scoring, case assembly     |
                    +-------------------+------------------+
                                        |
                                        v
                    +--------------------------------------+
                    |  Delivery Surfaces                   |
                    |  earctl, API, reports, audit, queue  |
                    +--------------------------------------+
```

## The Right Implementation Order

### Tier 0: Strengthen The Core Export-Control Program

This is the gating tier. It should stay first.

- Finish the production-ready CLI path for crawling and normalizing
  export-control laws.
- Add the NDAA list gap called out in `Short Comings.txt`.
- Keep the supported baseline narrow: deterministic corpus, KG emission,
  read-only API, operator scripts, and audit evidence.
- Promote new modules only when they can reuse those same contracts.

Without this tier, the future modules become disconnected side projects.

### Tier 1: Expand Restricted-Party And Authority Coverage

This is the first future tier because it directly strengthens the current
product mission.

- Add additional screening authorities beyond current Trade.gov CSL coverage:
  NDAA-related lists, BIS Entity List, OFAC sanctions, and other restricted
  party sources.
- Normalize all screened subjects into a canonical identity model:
  person, organization, sponsor, country, program, publication, project.
- Store source provenance and match confidence for every screening hit.
- Expose operator-facing CLI and report surfaces before adding UI-heavy work.

Primary value:

- closes the current export-control coverage gap,
- creates the subject graph required by every later module,
- keeps the roadmap anchored to export compliance.

### Tier 2: Add Collaboration And Publication Intelligence

This tier operationalizes the journal-search and collaborator ideas in the
future proposals.

- Add scholarly metadata adapters for CrossRef, PubMed, ORCID, and optionally
  Scopus where licensing permits.
- Build publication, author, affiliation, and coauthor nodes in the KG.
- Add first-hop and multi-hop collaborator expansion with explicit depth limits.
- Screen collaborators-of-collaborators against the restricted-party graph.
- Capture journal metadata, funding disclosures, acknowledgements, DOI, and
  affiliation history as evidence, not just text blobs.

Primary value:

- fills missing context around who is connected to whom,
- supports foreign-influence and collaborator-risk review,
- creates the evidence base for journal and publication screening.

### Tier 3: Link Institutional Compliance Systems

This is where earCrawler becomes a working research-security program rather
than just a law-and-publication intelligence engine.

- Ingest internal sources such as Cayuse, IRBManager, training systems, COI
  disclosures, inventory systems, and data-classification records.
- Model projects, protocols, disclosures, training certifications, data
  classes, equipment, and controlled substances as first-class graph entities.
- Join those records to people, sponsors, publications, and export-control
  authorities already in the graph.
- Generate missing-link findings such as:
  publication without protocol,
  foreign collaboration without screening,
  project without current training,
  sponsored work without COI disclosure,
  controlled technology without classification.

Primary value:

- moves from data retrieval to obligation tracking,
- turns isolated records into case-ready compliance evidence,
- makes later audit and reporting modules possible.

### Tier 4: Add Evidence-Based Review And Reporting

This tier should come after the graph and integration work, not before.

- Create a finding model with severity, confidence, evidence, owner, status,
  and remediation fields.
- Add review queues for human triage instead of auto-determinations.
- Produce scheduled reports:
  unscreened foreign collaborators,
  publications with questionable journal signals,
  projects missing IRB/IACUC links,
  lapsed training,
  funding or COI mismatches,
  restricted-party matches requiring escalation.
- Emit audit bundles that show the exact source records used for each finding.

Primary value:

- gives compliance staff one operator workflow,
- preserves defensibility,
- turns the KG into an auditable program system.

## Module Map By Dependency

| Module | What It Adds | Earliest Safe Tier | Depends On |
| --- | --- | --- | --- |
| Restricted-party screening | Screening against CSL, NDAA, BIS, OFAC, sponsors, vendors, collaborators | Tier 1 | Core export-law CLI, identity resolution |
| Collaboration network analysis | Multi-hop coauthor and collaborator graph expansion | Tier 2 | Restricted-party graph, scholarly metadata |
| Journal metadata and publication screening | Journal quality signals, DOI metadata, funding acknowledgements, affiliations | Tier 2 | Scholarly metadata adapters, person/org graph |
| Conflict-of-interest and funding | Grant, sponsor, disclosure, and publication cross-checks | Tier 3 | Person/project/publication graph, institutional feeds |
| Ethics / IRB / IACUC / IBC | Approval coverage for human, animal, and biosafety work | Tier 3 | Project graph, institutional protocol data |
| Data classification and security | Data sensitivity, storage controls, security posture | Tier 3 | Project and asset graph, institutional records |
| Training and certification | RCR, export-control, biosafety, cyber training status | Tier 3 | Person/project graph, training feeds |
| IP and controlled substance tracking | Patent, equipment, controlled material oversight | Tier 3 | Asset/project graph, institutional inventory |
| Cybersecurity monitoring | Incident linkage to projects and sensitive assets | Tier 4 | Data classification, asset graph, incident feeds |
| Audit and reporting | Dashboards, periodic reports, external evidence packs | Tier 4 | All prior tiers |

## Proposed Product Shape

The future program should not be one monolithic "compliance engine." It should
be four bounded subsystems that reuse the same graph and evidence contracts.

### 1. Authority Ingestion

Owns laws, regulations, watchlists, policy statements, and updates.

Likely repo fit:

- `api_clients/`
- `earCrawler/corpus/`
- `earCrawler/cli/jobs.py`
- `earCrawler/cli/corpus.py`

### 2. Entity And Relationship Intelligence

Owns identity resolution and the people/org/project/publication graph.

Likely repo fit:

- `earCrawler/corpus/entities.py`
- `earCrawler/corpus/records.py`
- `earCrawler/transforms/`
- `earCrawler/loaders/`
- `earCrawler/kg/`

### 3. Compliance Evaluation

Owns findings, evidence scoring, rule matching, and case assembly.

Likely repo fit:

- new `earCrawler/compliance/`
- new SHACL and rule shapes under `kg/`
- new scheduled job surfaces under `earCrawler/cli/`

### 4. Delivery And Governance

Owns operator workflows, audit logs, health, and reporting.

Likely repo fit:

- `service/api_server/`
- `earCrawler/cli/`
- `earCrawler/audit/`
- `earCrawler/observability/`

## Immediate Recommendations

1. Keep the current export-control baseline as the system of record and do not
   retire Trade.gov, EAR, or other export-law domain logic.
2. Treat the future scaffold as a module inventory, not as the target product
   architecture.
3. Make restricted-party expansion plus the NDAA gap the first future work
   package after the production CLI baseline is complete.
4. Build publication and collaborator intelligence next, because that is the
   cleanest path to "collaborators of collaborators" review.
5. Defer institutional-system integrations until the person/org/project graph
   is stable; otherwise every integration will invent its own identifiers.
6. Require every future module to emit provenance, match confidence, and audit
   artifacts from day one.

## Notes From The Proposal Files

- `future_project_scaffold.md` is useful for describing a three-pipeline shape,
  but it assumes earCrawler should become a generic research-compliance tool.
  That conflicts with the current supported product boundary and with the
  stated priority of a production-ready export-law crawler.
- `Proposed Compliance Modules for earCrawler.docx` is the strongest source for
  module ideas. Its best contribution is the module inventory, especially the
  restricted-party, collaboration, journal, COI, ethics, training, data, and
  audit modules.
- `Journal Search/searchS.txt` and `Journal Search/searchPM.txt` are useful as
  proof-of-concept source ideas, but not as implementation assets. They contain
  hardcoded credentials and should be reworked into normal `api_clients/`
  adapters with secret-backed configuration, retries, typed degraded states,
  and tests.
- `Short Comings.txt` identifies the most concrete immediate gap: NDAA list
  coverage is missing from the production CLI search path.

## Recommended Next Planning Artifact

Create one follow-on roadmap that breaks the future program into these work
packages:

1. Export authority expansion
2. Canonical subject graph
3. Publication and collaborator intelligence
4. Institutional compliance connectors
5. Findings, case management, and reporting

That roadmap should assign each package:

- source systems,
- graph entities,
- CLI/API surfaces,
- verification tests,
- operator evidence outputs,
- explicit non-goals.
