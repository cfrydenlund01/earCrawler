# earCrawler

A lightweight project for retrieving data from Trade.gov and the Federal Register.

This repository assumes a Windows installation path of `C:\Users\cfrydenlund\Projects\earCrawler` and targets **Python 3.11**.

## Setup

Install dependencies and run the test suite:

```bash
python -m pip install -r requirements.txt
pytest
```

The Trade.gov API key is read from the Windows Credential Manager entry `earCrawler:tradegov_api`.
