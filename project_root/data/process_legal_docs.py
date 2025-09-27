# process_legal_docs.py

import json
import logging
from pathlib import Path
from datetime import datetime
import argparse
import xml.etree.ElementTree as ET


class BaseProcessor:
    """
    Base class for processing legal documents.
    Handles input/output paths, versioning, and JSON export.
    """
    def __init__(self, source_name: str, input_path: Path, output_dir: Path):
        self.source_name = source_name
        self.input_path = Path(input_path)
        self.output_dir = Path(output_dir)
        self.logger = logging.getLogger(self.__class__.__name__)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def get_next_version(self) -> int:
        """Determine the next version number by scanning existing JSON files."""
        versions = []
        pattern = f"{self.source_name}_v*.json"
        for f in self.output_dir.glob(pattern):
            try:
                v = int(f.stem.split("_v", 1)[1])
                versions.append(v)
            except Exception:
                self.logger.debug(f"Ignoring non-versioned file: {f.name}")
        next_version = max(versions) + 1 if versions else 1
        self.logger.debug(f"Next version: v{next_version}")
        return next_version

    def save_json(self, payload: dict, version: int) -> Path:
        """Save payload as a versioned JSON file."""
        out_file = self.output_dir / f"{self.source_name}_v{version}.json"
        with out_file.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        self.logger.info(f"Saved JSON to {out_file}")
        return out_file

    def process(self) -> Path:
        raise NotImplementedError("Subclasses must implement process()")


class Title15Processor(BaseProcessor):
    """
    Processor for Title 15 XML legal documents.
    Parses <DIV5> (Parts) and <DIV8> (Sections) into JSON records.
    """
    def __init__(self, input_path: Path, output_dir: Path):
        # Use XML filename (without extension) as source_name
        name = input_path.stem
        super().__init__(source_name=name, input_path=input_path, output_dir=output_dir)

    def map_div(self, elem: ET.Element) -> dict:
        """Convert an XML <DIV5> or <DIV8> element into a dict record."""
        text_content = ''.join(elem.itertext()).strip()
        return {
            "id": elem.get("N"),
            "type": elem.get("TYPE"),
            "tag": elem.tag,
            "attributes": elem.attrib,
            "text": text_content
        }

    def process(self) -> Path:
        self.logger.debug(f"Parsing XML from {self.input_path}")
        tree = ET.parse(self.input_path)
        root = tree.getroot()

        records = []
        # Find both Part (<DIV5>) and Section (<DIV8>) elements
        for tag in ("DIV5", "DIV8"):
            for elem in root.findall(f".//{tag}"):
                rec = self.map_div(elem)
                records.append(rec)
                if len(records) <= 3:
                    self.logger.debug(f"Sample record: {rec}")

        version = self.get_next_version()
        payload = {
            "source_name": self.source_name,
            "version": version,
            "processed_date_utc": datetime.utcnow().isoformat() + "Z",
            "record_count": len(records),
            "records": records
        }
        return self.save_json(payload, version)


def main():
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    parser = argparse.ArgumentParser(description="Process Title 15 XML legal docs into JSON")
    parser.add_argument(
        "--input", required=True,
        help="Path to Title 15 XML file (e.g., title-15.xml or title-15-part-740.xml)"
    )
    parser.add_argument(
        "--output-dir", default="processed",
        help="Directory where versioned JSON will be saved"
    )
    args = parser.parse_args()

    processor = Title15Processor(
        input_path=Path(args.input),
        output_dir=Path(args.output_dir)
    )
    output_path = processor.process()
    print(f"➡️ Completed processing: {output_path}")


if __name__ == "__main__":
    main()
