## [0.1.0] – 2025-06-25
### Added
- Scaffolded `api_clients` modules for Trade.gov and Federal Register APIs.
- Unit tests in `tests/` with mocking and error-handling checks.
- GitHub Actions CI workflow targeting `windows-latest`.
- Comprehensive `README.md` with Windows setup instructions.
- Implement Trade.gov API client with paging, error handling, and pytest suite. [#VERSION]
- Add Federal Register API client for EAR text retrieval with pagination, error handling, and pytest suite. [#VERSION]
- Add core crawler orchestration to fetch entities and documents for ingestion. [#VERSION]
- Add ETL ingestion script with SHACL validation and Jena TDB2 loading. [#VERSION]
- Add FastAPI-based SPARQL query service for TDB2 data. [#VERSION]
- Add analytics ReportsGenerator module for SPARQL-based aggregate reporting. [#VERSION]
- Add CLI for fetching analytics reports via FastAPI service. [#VERSION]
- Package earCrawler as installable CLI with console-script entry-point (v0.1.0).
- Implement RAG Retriever using all-MiniLM-L12-v2 and FAISS. [#VERSION]
