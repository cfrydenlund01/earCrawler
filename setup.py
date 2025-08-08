from setuptools import setup, find_packages

setup(
    name="earCrawler",
    version="0.4.0",
    description="EAR AI ingestion, RAG, and analytics pipeline",
    author="Your Name",
    author_email="you@example.com",
    packages=find_packages(),
    install_requires=[
        "click>=8.0",
        "requests>=2.31.0",
        "fastapi>=0.85.0",
        "SPARQLWrapper>=1.8.5",
        "tabulate>=0.8.9",
        "beautifulsoup4>=4.12.3",
        "lxml>=5.2.2",
        "python-dateutil>=2.9.0.post0",
    ],
    entry_points={
        "console_scripts": [
            "earcrawler=earCrawler.cli.reports_cli:main"
        ],
    },
    license="MIT",
)
