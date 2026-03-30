# Research Compliance Tool - Project Scaffold & Transformation Plan

**Date:** March 20, 2026  
**Project:** earCrawler → Research Compliance Tool  
**Status:** Architecture & Requirements Definition

---

## Executive Summary

Transform earCrawler from an export regulation crawler into a **Research Compliance Tool** that checks and reports findings based on:
- **Laws & Regulations** (ingested from legal databases)
- **Research Reports** (uploaded by users)
- **Peer-Reviewed Literature** (sourced from academic APIs)

Removes grant/proposal tracking entirely. Reuses the robust Fuseki/RDF infrastructure and FastAPI architecture.

---

## Current Architecture (Reusable Foundation)

Your project has a solid infrastructure well-suited for this transformation:

| Component | Status | Role in New System |
|-----------|--------|-------------------|
| **Apache Jena Fuseki** + RDF KG | Production | Compliance rules KB + finding relationships |
| **FastAPI Service** | Production | Compliance endpoint host + auth/middleware |
| **RAG System** | Production | Literature review queries |
| **CLI (earctl)** | Production | Compliance workflow commands |
| **Audit/Telemetry** | Production | Compliance audit trails |
| **Policy Enforcement** | Production | Role-based access to findings |

**What to Retire:**
- Trade.gov crawling (replace with legal sources)
- Export regulation domain logic
- Grant/proposal tracking
- Trade-specific data models

---

## Transformation Components

### 1. Data Sources (Replace Current Crawlers)

| Component | Current | Target |
|-----------|---------|--------|
| **Regulations** | Trade.gov, Federal Register | Legal databases, OpenLaw, government APIs |
| **Research Input** | External crawls | File uploads (PDF, DOCX, TXT, DOCX) |
| **Literature** | None | CrossRef API, PubMed, SSRN, arXiv, Google Scholar |
| **Standards** | None | ISO, IEEE, domain-specific standards |

**Example Legal Data Sources:**
- OpenLaw.io (open legal documents)
- Government Regulation APIs (USCODE, CFR)
- Cornell Legal Institute (LII) API
- Unjust Enrichment / Research Ethics Guidelines

**Example Academic Sources:**
- CrossRef API (DOI + metadata)
- PubMed Central API
- SSRN
- OpenAlex (free open science DB)
- arXiv

---

### 2. Core Capabilities

#### **Compliance Checking**
- Rules-based violation detection (laws vs. research)
- Ethical review framework
- Literature gap analysis
- Conflict detection across regulations

#### **Finding Detection & Classification**
- Categorize findings by severity (critical, high, medium, low, informational)
- Finding types: violation, warning, gap, recommendation
- Linked evidence (regulation + research passage)
- Remediation suggestions

#### **Report Generation**
- Compliance audit reports (executive summary + detailed findings)
- Literature review reports (relevant sources linked to compliance rules)
- Trend analysis (violations over time)
- Comparison reports (versions of research)

#### **Literature Integration**
- Cross-reference research against peer-reviewed sources
- Pull supporting/conflicting evidence
- Citation tracking
- Gap identification

---

## Three Key Processing Pipelines

### **Pipeline 1: Laws Registry**
```
Step 1: Ingest legal sources
   ↓
Step 2: Normalize regulations (extract articles, sections, requirements)
   ↓
Step 3: Create RDF compliance rules entities
   ↓
Step 4: Store in Fuseki + Index for search
```

**Output:** Queryable compliance rule KB in graph database

### **Pipeline 2: Research Scanning**
```
Step 1: Upload research document (PDF/DOCX/TXT)
   ↓
Step 2: Extract text + metadata (author, date, DOI if available)
   ↓
Step 3: Cross-reference against compliance rules
   ↓
Step 4: Report matching findings + severity
   ↓
Step 5: Suggest remediation + related literature
```

**Output:** Compliance findings + recommendations

### **Pipeline 3: Literature Review**
```
Step 1: User queries for research on topic/regulation
   ↓
Step 2: Query academic APIs (CrossRef, PubMed, etc.)
   ↓
Step 3: Fetch peer-reviewed sources
   ↓
Step 4: Link to compliance findings
   ↓
Step 5: Return annotated bibliography
```

**Output:** Curated peer-reviewed literature linked to compliance context

---

## Data Model & RDF Schema

### New Ontology Entities

```
Core Compliance Entities:
├── Law (regulation, statute, standard)
│   ├── jurisdiction (country, region)
│   ├── effectiveDate
│   ├── applicableScope (sector, context)
│   └── requirements (linked to Requirement entities)
│
├── Requirement (atomic compliance rule)
│   ├── text (the actual requirement)
│   ├── severity (must/should/may)
│   ├── enforcementMechanism
│   └── exemptions (edge cases)
│
├── ResearchArtifact (document, dataset, project)
│   ├── title
│   ├── authors
│   ├── datePublished
│   ├── doi
│   ├── uploadedDate
│   └── content (full text)
│
├── Finding (compliance assessment result)
│   ├── artifact (linked ResearchArtifact)
│   ├── requirement (linked Requirement)
│   ├── severity (critical|high|medium|low|info)
│   ├── type (violation|warning|gap|recommendation)
│   ├── evidence (matching text snippets)
│   ├── remediation
│   └── confidence (0-1)
│
├── Literature (peer-reviewed source)
│   ├── doi
│   ├── title
│   ├── authors
│   ├── abstract
│   ├── publicationDate
│   ├── journal
│   └── relevantToFinding (linked Finding entities)
│
└── ComplianceReport
    ├── artifact
    ├── generatedDate
    ├── findings (list of Finding entities)
    ├── executiveSummary
    ├── recommendedActions
    └── relatedLiterature
```

### Shape Definitions (SHACL)

Create SHACL shapes validation at `earCrawler/kg/shapes_compliance.ttl`:
- Require Law to have at least one Requirement
- Validate Finding has evidence text
- Enforce Finding severity from controlled vocabulary
- Link Literature to Finding with confidence score

---

## Implementation Phases

### **Phase 1: Foundation (Week 1-2)**
**Goal:** Establish compliance data model

- [ ] Design RDF ontology for compliance entities (extend existing shapes.ttl)
- [ ] Create `earCrawler/compliance/ontology.ttl`
- [ ] Build SHACL validation shapes
- [ ] Document entity relationships

**Deliverables:**
- `earCrawler/schema/compliance_ontology.ttl`
- `earCrawler/kg/shapes_compliance.ttl`
- Documentation in `docs/compliance_data_model.md`

---

### **Phase 2: Ingestion Layer (Week 2-3)**
**Goal:** Support three data sources with uniform ingestion

#### **2a. Legal Source Client**
Create: `api_clients/legal_source_client.py`
- Start with static JSON law definitions (minimal API overhead)
- Or integrate OpenLaw API / CFR API
- Extract & normalize regulations into RDF

#### **2b. Research Document Handler**
Create: `earCrawler/compliance/document_ingestion.py`
- Accept PDF, DOCX, TXT uploads
- Extract text using pdfplumber, python-docx
- Parse metadata (title, authors, date)
- Try to extract DOI if available
- Store in Fuseki as ResearchArtifact

#### **2c. Academic Literature Client**
Create: `api_clients/literature_client.py`
- Query CrossRef API by title, DOI, keywords
- Query PubMed Central for biomedical research
- Fetch & normalize metadata
- Store as Literature entities in KG

**Deliverables:**
- `api_clients/legal_source_client.py`
- `api_clients/literature_client.py`
- `earCrawler/compliance/document_ingestion.py`
- Integration tests

---

### **Phase 3: Compliance Engine (Week 3-5)**
**Goal:** Core checking logic

#### **3a. Rules Engine**
Create: `earCrawler/compliance/rules_engine.py`
- Load requirements from KG
- Match requirement text against research content
- Use semantic similarity (embeddings or regex patterns)
- Calculate confidence scores

#### **3b. Finding Detector**
Create: `earCrawler/compliance/finding_detector.py`
- Classify finding type (violation, warning, gap, etc.)
- Assign severity based on rule + context
- Extract evidence snippets (matching passages)
- Generate remediation suggestions

#### **3c. Report Generator**
Create: `earCrawler/compliance/report_generator.py`
- Aggregate findings into structured report
- Create executive summary
- Link findings to relevant literature
- Format output (JSON, markdown, PDF options)

**Deliverables:**
- `earCrawler/compliance/rules_engine.py`
- `earCrawler/compliance/finding_detector.py`
- `earCrawler/compliance/report_generator.py`
- Unit tests with sample research + regulations

---

### **Phase 4: APIs & CLI (Week 5-6)**
**Goal:** User-facing tools

#### **4a. New API Endpoints**
Create: `service/api_server/routers/compliance.py`

```python
POST /compliance/check
  - Input: research_artifact_id or document_file
  - Output: findings[] with severity, evidence, remediation
  
POST /compliance/upload
  - Input: multipart file (PDF/DOCX/TXT)
  - Output: artifact_id, extracted_metadata
  
GET /compliance/findings
  - Query: filter by severity, type, artifact
  - Output: paginated findings list
  
GET /compliance/reports/{artifact_id}
  - Output: full compliance report
  
GET /compliance/sources/regulations
  - Output: list of loaded regulations
  
POST /compliance/sources/regulations
  - Input: law definition
  - Output: regulation_id
  
GET /literature/search
  - Query: keyword, topic, artifact_id
  - Output: matching peer-reviewed sources
```

#### **4b. CLI Commands**
Extend `earCrawler/cli/__main__.py` with compliance group:

```bash
earctl compliance check <artifact>
earctl compliance report <artifact>
earctl compliance sources add-law <json_file>
earctl compliance sources list
earctl literature search <keyword>
earctl compliance config validate
```

**Deliverables:**
- `service/api_server/routers/compliance.py`
- Extended CLI commands
- OpenAPI documentation
- Postman collection for testing

---

### **Phase 5: Documentation & Examples (Week 6)**
**Goal:** Operators can deploy and use the tool

- [ ] User guide: How to upload research & interpret findings
- [ ] Administrator guide: How to load regulations & configure rules
- [ ] API documentation (auto-generated from OpenAPI)
- [ ] Deploy guide (Windows service, Fuseki setup)
- [ ] Example research artifacts + expected findings
- [ ] Compliance report samples

---

## Folder Structure (Post-Transformation)

```
earCrawler/
├── compliance/                 # NEW: Core compliance engine
│   ├── __init__.py
│   ├── ontology.ttl           # NEW: RDF compliance schema
│   ├── rules_engine.py        # NEW: Requirement matching
│   ├── finding_detector.py    # NEW: Finding classification
│   ├── report_generator.py    # NEW: Report creation
│   ├── document_ingestion.py  # NEW: Upload/parse pipeline
│   └── templates/             # NEW: Report templates
│
├── kg/
│   ├── shapes.ttl             # EXISTING
│   ├── shapes_compliance.ttl  # NEW: Compliance validation
│   └── ...
│
├── schema/
│   ├── compliance_ontology.ttl  # NEW: Full compliance schema
│   └── ...
│
├── cli/
│   ├── __main__.py            # MODIFIED: Register compliance group
│   ├── compliance_commands.py # NEW: CLI for compliance tools
│   └── ...
│
├── transforms/
│   ├── compliance_rules.py    # NEW: Transform requirements to RDF
│   └── ...
│
├── observability/
│   ├── compliance_metrics.py  # NEW: Track compliance checks
│   └── ...
│
├── security/
│   ├── default_policy.yml     # MODIFIED: Compliance roles
│   └── ...
│
└── (retirement queue - to remove)
    ├── ingestion/*            # OLD: EAR-specific crawler
    ├── tradegov/              # OLD: Trade.gov integration
    ├── models/ear_*           # OLD: Export regulation models
    └── audit/*trade*          # OLD: Trade-specific audit

api_clients/
├── legal_source_client.py     # NEW: Regulations API
├── literature_client.py       # NEW: Academic literature APIs
├── tradegov_client.py         # MARK FOR REMOVAL
└── ...

service/api_server/routers/
├── compliance.py              # NEW: Compliance endpoints
├── entities.py                # MODIFY: Generic rename
├── rag.py                      # KEEP: Literature search
└── ...

docs/
├── compliance_data_model.md   # NEW
├── compliance_api.md          # NEW
├── deployment_guide.md        # MODIFY: Compliance focus
├── examples/
│   ├── sample_research_report.pdf   # NEW
│   ├── compliance_output.json       # NEW
│   └── ...
└── ...
```

---

## Key Differences from earCrawler

| Aspect | earCrawler | Research Compliance Tool |
|--------|-----------|---------------------------|
| **Primary Data** | Export regulations | Laws + Research documents |
| **Input Source** | Web crawlers | File upload + API calls |
| **Core Processing** | Classification + RAG | Compliance checking + matching |
| **Output** | Answers to compliance questions | Findings + remediation reports |
| **Users** | Export/trade compliance officers | Researchers + compliance auditors |
| **Rules Source** | Federal Register | Government + organizational policies |
| **Success Metric** | Accuracy of regulation retrieval | Reduction in compliance violations |

---

## Technology Stack (Proposed)

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Backend** | FastAPI + Python 3.11 | API server (reuse existing) |
| **Knowledge Base** | Apache Jena Fuseki + RDF | Rules + findings storage |
| **RAG** | Existing (sentence-transformers) | Literature similarity search |
| **Document Processing** | pdfplumber, python-docx, PyPDF2 | Extract text from uploads |
| **APIs** | CrossRef, PubMed, OpenAlex | Peer-reviewed literature |
| **Embeddings** | sentence-transformers or spaCy | Semantic matching (optional) |
| **Reporting** | Jinja2 templates | Report generation |
| **CLI** | Click (reuse existing) | Command-line tool |
| **Testing** | pytest (reuse existing) | Unit + integration tests |

---

## Risk & Mitigation

| Risk | Mitigation |
|------|-----------|
| Large PDF parsing failures | Implement fallback text extraction; test with diverse formats |
| Literature API rate limits | Cache results; batch queries; document rate limit practices |
| False positive findings | Implement confidence scoring; require manual review for low-confidence |
| Scalability (Fuseki overload) | Start with small rule sets; profile KG queries; consider sharding |
| Jurisdiction/applicability | Store jurisdiction metadata; allow rule filtering by scope |
| Maintaining law updates | Implement change tracking; schedule quarterly updates |

---

## Success Metrics

- ✅ Tool can ingest 10+ regulations without crashes
- ✅ Upload + check cycle < 30 seconds for typical research (< 50 pages)
- ✅ Finding accuracy > 85% (validated against manual review)
- ✅ Generate compliance report in < 5 seconds
- ✅ Literature search returns relevant sources (manual validation)
- ✅ Support 100+ concurrent RDF queries without timeout
- ✅ API uptime > 99.5%

---

## Next Steps

1. **Review & Refine:** Validate data model with compliance domain experts
2. **Legal Source Selection:** Identify 3-5 priority regulations to ingest first
3. **Prototype Upload:** Build minimal document ingestion proof-of-concept
4. **Compliance Rules:** Define 5-10 sample requirements for initial testing
5. **MVP Sprint:** Implement Phase 1-2 in 2-week iteration

---

## References & Resources

### Legal/Compliance Sources
- https://www.law.cornell.edu/ (free legal research)
- https://www.openlaw.io/ (machine-readable laws)
- https://www.regulations.gov/ (US federal regulations)

### Academic APIs
- https://www.crossref.org/services/metadata-retrieval/ (CrossRef API)
- https://www.ncbi.nlm.nih.gov/pmc/tools/textmining/ (PubMed API)
- https://openalex.org/ (Open science database)

### Related Projects
- https://github.com/PublicLaw/legal-nlp (legal NLP tools)
- https://github.com/openai/gpt-3-doc-search (semantic search patterns)

---

**Document Version:** 1.0  
**Last Updated:** March 20, 2026  
**Author:** Research Compliance Tool Team
