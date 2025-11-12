from setuptools import setup, find_packages

setup(
    name="earCrawler",
    version="0.1.0",
    description="EAR AI ingestion, RAG, and analytics pipeline",
    author="Your Name",
    author_email="you@example.com",
    packages=find_packages(),
    package_data={
        "": ["docs/privacy/telemetry_policy.md", "docs/privacy/redaction_rules.md"]
    },
    install_requires=[
        "click>=8.0",
        "requests>=2.31.0",
        "fastapi>=0.85.0",
        "SPARQLWrapper>=1.8.5",
        "tabulate>=0.8.9",
    ],
    entry_points={
        "console_scripts": ["earCrawler=earCrawler.cli.reports_cli:main"],
    },
    license="MIT",
)
