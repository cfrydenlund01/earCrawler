# --- START MODIFIED process_entities.py ---

# process_entities.py

import csv
import json
import logging
from pathlib import Path
from datetime import datetime
import argparse
import xml.etree.ElementTree as ET
from typing import Optional, List, Dict, Any

# Define a type hint for the namespace map
NsMap = Dict[str, str]

class BaseProcessor:
    """
    Base class for processing files into versioned JSON.
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
                # Handle potential variations in naming if needed
                if "_v" in f.stem:
                    v_str = f.stem.split("_v")[-1]
                    # Ensure it's purely numeric before casting
                    if v_str.isdigit():
                         v = int(v_str)
                         versions.append(v)
                    else:
                         self.logger.debug(f"Ignoring file with non-numeric version part: {f.name}")
                else:
                    self.logger.debug(f"Ignoring non-versioned file: {f.name}")

            except Exception as e:
                self.logger.warning(f"Error parsing version from file {f.name}: {e}")
        next_version = max(versions) + 1 if versions else 1
        self.logger.debug(f"Next version for {self.source_name}: v{next_version}")
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

    # --- Helper function for XML parsing ---
    def _get_element_text(self, element: Optional[ET.Element]) -> Optional[str]:
        """Safely get stripped text from an element."""
        if element is not None and element.text:
            return element.text.strip()
        return None

    def _get_element_attrib(self, element: Optional[ET.Element]) -> Dict[str, str]:
        """Safely get attributes from an element."""
        if element is not None:
            return element.attrib
        return {}

    def _parse_xml_element(self, element: Optional[ET.Element]) -> Optional[Dict[str, Any]]:
        """Parse an XML element into a dict, handling text and attributes."""
        if element is None:
            return None
        data = self._get_element_attrib(element)
        text = self._get_element_text(element)
        if text:
            # If there are attributes, store text under a 'text' key
            if data:
                data['text'] = text
            else:
                # If no attributes, the element value *is* the text
                return text
        # If only attributes, return the dict; if neither, return None or {}? Let's return attributes or None
        return data if data else (text if text else None) # Return None if completely empty


class CSLProcessor(BaseProcessor):
    """
    Processor for CSV-based CSL entity lists.
    Parses CSV rows into JSON records.
    """
    def __init__(self, input_path: Path, output_dir: Path):
        name = input_path.stem # Use stem for consistent source naming
        super().__init__(source_name=name, input_path=input_path, output_dir=output_dir)

    def process(self) -> Path:
        self.logger.debug(f"Reading CSV from {self.input_path}")
        records = []
        try:
            with self.input_path.open(newline='', encoding='utf-8-sig') as csvfile: # Use utf-8-sig for potential BOM
                reader = csv.DictReader(csvfile)
                for i, row in enumerate(reader):
                    # Basic check for empty rows
                    if not any(row.values()):
                        self.logger.warning(f"Skipping potentially empty row {i+1} in {self.input_path.name}")
                        continue
                    records.append(row)
            self.logger.info(f"Successfully parsed {len(records)} records from {self.input_path.name}")
        except FileNotFoundError:
            self.logger.error(f"Input file not found: {self.input_path}")
            raise
        except Exception as e:
            self.logger.error(f"Error processing CSV file {self.input_path}: {e}")
            raise

        version = self.get_next_version()
        payload = {
            "source_name": self.source_name,
            "version": version,
            "processed_date_utc": datetime.utcnow().isoformat() + "Z",
            "record_count": len(records),
            "records": records
        }
        return self.save_json(payload, version)

class ConsolidatedXMLProcessor(BaseProcessor):
    """
    Processor for OFAC Enhanced Consolidated (CSL) XML entity lists.
    Parses <entity> entries into JSON records.
    """
    def __init__(self, input_path: Path, output_dir: Path):
        name = input_path.stem # Use stem for consistent source naming
        super().__init__(source_name=name, input_path=input_path, output_dir=output_dir)
        self.ns = {} # Namespace map will be populated during processing

    def _get_ns_tag(self, tag_name: str) -> str:
        """Helper to get the tag name with the default namespace prefix."""
        # Assumes the default namespace is mapped to 'def'
        return f'def:{tag_name}'

    def _parse_list(self, parent_element: ET.Element, list_tag: str, item_tag: str) -> List[Dict[str, Any]]:
        """Helper to parse lists of items within the XML."""
        items = []
        list_element = parent_element.find(self._get_ns_tag(list_tag), self.ns)
        if list_element is not None:
            for item_element in list_element.findall(self._get_ns_tag(item_tag), self.ns):
                parsed = self._parse_xml_element(item_element)
                if parsed:
                    items.append(parsed)
        return items

    def _parse_names(self, parent_element: ET.Element) -> List[Dict[str, Any]]:
        """Parse the complex <names> structure."""
        names_list = []
        names_element = parent_element.find(self._get_ns_tag('names'), self.ns)
        if names_element is not None:
            for name_element in names_element.findall(self._get_ns_tag('name'), self.ns):
                name_data = self._get_element_attrib(name_element) # Get attributes like isPrimary, isLowQuality, aliasType refId
                translations = []
                for trans_element in name_element.findall(self._get_ns_tag('translations') + '/' + self._get_ns_tag('translation'), self.ns):
                    trans_data = self._get_element_attrib(trans_element) # Get attributes like isPrimary, script refId
                    trans_data['formattedFirstName'] = self._get_element_text(trans_element.find(self._get_ns_tag('formattedFirstName'), self.ns))
                    trans_data['formattedLastName'] = self._get_element_text(trans_element.find(self._get_ns_tag('formattedLastName'), self.ns))
                    trans_data['formattedFullName'] = self._get_element_text(trans_element.find(self._get_ns_tag('formattedFullName'), self.ns))

                    name_parts = []
                    parts_element = trans_element.find(self._get_ns_tag('nameParts'), self.ns)
                    if parts_element is not None:
                         for part_element in parts_element.findall(self._get_ns_tag('namePart'), self.ns):
                              part_data = self._get_element_attrib(part_element) # Get type refId
                              part_data['value'] = self._get_element_text(part_element.find(self._get_ns_tag('value'), self.ns))
                              if part_data['value']: # Only add if there's a value
                                   name_parts.append(part_data)
                    if name_parts:
                         trans_data['nameParts'] = name_parts

                    # Add translation only if it has some content
                    if trans_data.get('formattedFullName') or trans_data.get('nameParts'):
                         translations.append(trans_data)

                if translations:
                     name_data['translations'] = translations
                     names_list.append(name_data)
        return names_list

    def _parse_addresses(self, parent_element: ET.Element) -> List[Dict[str, Any]]:
         """Parse the <addresses> structure."""
         address_list = []
         addresses_element = parent_element.find(self._get_ns_tag('addresses'), self.ns)
         if addresses_element is not None:
            for address_element in addresses_element.findall(self._get_ns_tag('address'), self.ns):
                address_data = self._get_element_attrib(address_element) # Get attributes like id
                country_ref_id = self._get_element_attrib(address_element.find(self._get_ns_tag('country'), self.ns)).get('refId')
                if country_ref_id:
                     address_data['country_refId'] = country_ref_id

                translations = []
                for trans_element in address_element.findall(self._get_ns_tag('translations') + '/' + self._get_ns_tag('translation'), self.ns):
                    trans_data = self._get_element_attrib(trans_element) # Get attributes like isPrimary, script refId
                    address_parts = []
                    parts_element = trans_element.find(self._get_ns_tag('addressParts'), self.ns)
                    if parts_element is not None:
                        for part_element in parts_element.findall(self._get_ns_tag('addressPart'), self.ns):
                              part_data = self._get_element_attrib(part_element) # Get type refId
                              part_data['value'] = self._get_element_text(part_element.find(self._get_ns_tag('value'), self.ns))
                              if part_data['value']: # Only add if there's a value
                                   address_parts.append(part_data)
                    if address_parts:
                        trans_data['addressParts'] = address_parts
                        translations.append(trans_data) # Only add translation if it has parts

                if translations:
                    address_data['translations'] = translations
                address_list.append(address_data)
         return address_list

    def _parse_features(self, parent_element: ET.Element) -> List[Dict[str, Any]]:
        """Parse the <features> structure."""
        feature_list = []
        features_element = parent_element.find(self._get_ns_tag('features'), self.ns)
        if features_element is not None:
            for feature_element in features_element.findall(self._get_ns_tag('feature'), self.ns):
                feature_data = self._get_element_attrib(feature_element) # Get id
                feature_data['type_featureTypeId'] = self._get_element_attrib(feature_element.find(self._get_ns_tag('type'), self.ns)).get('featureTypeId')
                feature_data['versionId'] = self._get_element_text(feature_element.find(self._get_ns_tag('versionId'), self.ns))
                feature_data['value'] = self._get_element_text(feature_element.find(self._get_ns_tag('value'), self.ns))
                feature_data['isPrimary'] = self._get_element_text(feature_element.find(self._get_ns_tag('isPrimary'), self.ns)) == 'true'

                value_date_element = feature_element.find(self._get_ns_tag('valueDate'), self.ns)
                if value_date_element is not None:
                     date_data = self._get_element_attrib(value_date_element) # get id
                     date_data['fromDateBegin'] = self._get_element_text(value_date_element.find(self._get_ns_tag('fromDateBegin'), self.ns))
                     date_data['fromDateEnd'] = self._get_element_text(value_date_element.find(self._get_ns_tag('fromDateEnd'), self.ns))
                     date_data['toDateBegin'] = self._get_element_text(value_date_element.find(self._get_ns_tag('toDateBegin'), self.ns))
                     date_data['toDateEnd'] = self._get_element_text(value_date_element.find(self._get_ns_tag('toDateEnd'), self.ns))
                     date_data['isApproximate'] = self._get_element_text(value_date_element.find(self._get_ns_tag('isApproximate'), self.ns)) == 'true'
                     date_data['isDateRange'] = self._get_element_text(value_date_element.find(self._get_ns_tag('isDateRange'), self.ns)) == 'true'
                     feature_data['valueDate'] = date_data

                value_ref_id = self._get_element_attrib(feature_element.find(self._get_ns_tag('valueRefId'), self.ns)).get('refId')
                if value_ref_id:
                     feature_data['valueRefId'] = value_ref_id

                reliability_ref_id = self._get_element_attrib(feature_element.find(self._get_ns_tag('reliability'), self.ns)).get('refId')
                if reliability_ref_id:
                    feature_data['reliability_refId'] = reliability_ref_id

                comments = self._get_element_text(feature_element.find(self._get_ns_tag('comments'), self.ns))
                if comments:
                     feature_data['comments'] = comments

                feature_list.append(feature_data)
        return feature_list

    def _parse_identity_documents(self, parent_element: ET.Element) -> List[Dict[str, Any]]:
         """Parse the <identityDocuments> structure."""
         docs_list = []
         docs_element = parent_element.find(self._get_ns_tag('identityDocuments'), self.ns)
         if docs_element is not None:
            for doc_element in docs_element.findall(self._get_ns_tag('identityDocument'), self.ns):
                doc_data = self._get_element_attrib(doc_element) # Get id
                doc_data['type_refId'] = self._get_element_attrib(doc_element.find(self._get_ns_tag('type'), self.ns)).get('refId')
                # The name element here seems redundant if linked to a primary name elsewhere, TBC
                # doc_data['name_nameId'] = self._get_element_attrib(doc_element.find(self._get_ns_tag('name'), self.ns)).get('nameId')
                # doc_data['name_nameTranslationId'] = self._get_element_attrib(doc_element.find(self._get_ns_tag('name'), self.ns)).get('nameTranslationId')
                doc_data['documentNumber'] = self._get_element_text(doc_element.find(self._get_ns_tag('documentNumber'), self.ns))
                doc_data['isValid'] = self._get_element_text(doc_element.find(self._get_ns_tag('isValid'), self.ns)) == 'true'
                doc_data['issuingLocation'] = self._get_element_text(doc_element.find(self._get_ns_tag('issuingLocation'), self.ns))
                issuing_country_element = doc_element.find(self._get_ns_tag('issuingCountry'), self.ns)
                if issuing_country_element is not None:
                     doc_data['issuingCountry_refId'] = self._get_element_attrib(issuing_country_element).get('refId')
                     doc_data['issuingCountry_text'] = self._get_element_text(issuing_country_element)

                docs_list.append(doc_data)
         return docs_list

    def _parse_relationships(self, parent_element: ET.Element) -> List[Dict[str, Any]]:
        """Parse the <relationships> structure."""
        rels_list = []
        rels_element = parent_element.find(self._get_ns_tag('relationships'), self.ns)
        if rels_element is not None:
            for rel_element in rels_element.findall(self._get_ns_tag('relationship'), self.ns):
                rel_data = self._get_element_attrib(rel_element) # Get id
                rel_data['type_refId'] = self._get_element_attrib(rel_element.find(self._get_ns_tag('type'), self.ns)).get('refId')
                rel_entity = rel_element.find(self._get_ns_tag('relatedEntity'), self.ns)
                if rel_entity is not None:
                     rel_data['relatedEntity_entityId'] = self._get_element_attrib(rel_entity).get('entityId')
                     rel_data['relatedEntity_text'] = self._get_element_text(rel_entity)
                quality_ref_id = self._get_element_attrib(rel_element.find(self._get_ns_tag('quality'), self.ns)).get('refId')
                if quality_ref_id:
                    rel_data['quality_refId'] = quality_ref_id

                rels_list.append(rel_data)
        return rels_list

    def map_entity(self, entity_element: ET.Element) -> Dict[str, Any]:
        """Convert an XML <entity> element into a dictionary."""
        record = self._get_element_attrib(entity_element) # Get entity id

        # General Info
        general_info = entity_element.find(self._get_ns_tag('generalInfo'), self.ns)
        if general_info is not None:
            record['identityId'] = self._get_element_text(general_info.find(self._get_ns_tag('identityId'), self.ns))
            record['entityType_refId'] = self._get_element_attrib(general_info.find(self._get_ns_tag('entityType'), self.ns)).get('refId')
            remarks = self._get_element_text(general_info.find(self._get_ns_tag('remarks'), self.ns))
            if remarks:
                record['remarks'] = remarks

        # Simple Lists (using helper)
        record['sanctionsLists'] = self._parse_list(entity_element, 'sanctionsLists', 'sanctionsList')
        record['sanctionsPrograms'] = self._parse_list(entity_element, 'sanctionsPrograms', 'sanctionsProgram')
        record['sanctionsTypes'] = self._parse_list(entity_element, 'sanctionsTypes', 'sanctionsType')
        record['legalAuthorities'] = self._parse_list(entity_element, 'legalAuthorities', 'legalAuthority')

        # Complex Structures (using dedicated helpers)
        record['names'] = self._parse_names(entity_element)
        record['addresses'] = self._parse_addresses(entity_element)
        record['features'] = self._parse_features(entity_element)
        record['identityDocuments'] = self._parse_identity_documents(entity_element)
        record['relationships'] = self._parse_relationships(entity_element)


        # Remove empty lists for cleaner output
        keys_to_clean = ['sanctionsLists', 'sanctionsPrograms', 'sanctionsTypes', 'legalAuthorities', 'names', 'addresses', 'features', 'identityDocuments', 'relationships']
        for key in keys_to_clean:
            if key in record and not record[key]:
                del record[key]

        return record

    def process(self) -> Path:
        self.logger.info(f"Parsing OFAC Consolidated XML from {self.input_path}")
        try:
            tree = ET.parse(self.input_path)
            root = tree.getroot()

            # Extract default namespace URI from the root element tag
            if '}' in root.tag:
                ns_uri = root.tag.split('}')[0][1:] # Get the URI part inside {}
                self.ns = {'def': ns_uri} # Map it to a prefix like 'def'
                self.logger.debug(f"Detected XML namespace: {ns_uri}")
            else:
                # Handle case where there might not be a default namespace (unlikely for OFAC)
                self.logger.warning("No default namespace found on root element. Parsing might fail.")
                self.ns = {} # No namespace to use


            records = []
            # Find entities using the namespace map
            entity_elements = root.findall('.//def:entity', self.ns) if self.ns else root.findall('.//entity')
            self.logger.debug(f"Found {len(entity_elements)} <entity> elements.")

            for i, elem in enumerate(entity_elements):
                try:
                    rec = self.map_entity(elem)
                    records.append(rec)
                except Exception as e:
                    entity_id = elem.get('id', f'index_{i}')
                    self.logger.warning(f"Failed mapping entity {entity_id}: {e}", exc_info=True)

            self.logger.info(f"Successfully parsed {len(records)} entity records from XML")

        except ET.ParseError as e:
             self.logger.error(f"XML Parse Error in {self.input_path}: {e}")
             raise
        except FileNotFoundError:
            self.logger.error(f"Input file not found: {self.input_path}")
            raise
        except Exception as e:
            self.logger.error(f"Error processing XML file {self.input_path}: {e}")
            raise


        version = self.get_next_version()
        payload = {
            "source_name": self.source_name,
            "version": version,
            "processed_date_utc": datetime.utcnow().isoformat() + "Z",
            "record_count": len(records),
            "records": records
        }
        return self.save_json(payload, version)


# --- Original OFACProcessor kept for potential other OFAC formats ---
class OFACProcessor(BaseProcessor):
    """
    Processor for *simple* OFAC XML lists (e.g., focusing on referenceValue).
    Parses <referenceValue> entries into JSON records.
    NOTE: Use ConsolidatedXMLProcessor for cons_enhanced.xml
    """
    def __init__(self, input_path: Path, output_dir: Path):
        name = input_path.stem
        super().__init__(source_name=name, input_path=input_path, output_dir=output_dir)

    def map_reference(self, elem: ET.Element) -> dict:
        """Convert an XML <referenceValue> element into a dict."""
        record = {"refId": elem.get("refId")}
        for child in elem:
            # Simplified parsing assuming simple tag=text or tag={attribs+text}
            tag = child.tag.split('}')[-1] # Simple tag name without namespace
            parsed_child = self._parse_xml_element(child)
            if parsed_child is not None:
                record[tag] = parsed_child
        return record

    def process(self) -> Path:
        self.logger.info(f"Parsing generic OFAC XML (referenceValues) from {self.input_path}")
        try:
            tree = ET.parse(self.input_path)
            root = tree.getroot()

            # Handle potential default namespace if present
            ns = {}
            if '}' in root.tag:
                ns_uri = root.tag.split('}')[0][1:]
                ns = {'def': ns_uri}
                self.logger.debug(f"Detected XML namespace: {ns_uri}")

            records = []
            # Find referenceValue using the namespace map if available
            ref_elements = root.findall('.//def:referenceValue', ns) if ns else root.findall('.//referenceValue')
            self.logger.debug(f"Found {len(ref_elements)} <referenceValue> elements.")

            for i, elem in enumerate(ref_elements):
                try:
                    rec = self.map_reference(elem)
                    records.append(rec)
                except Exception as e:
                    ref_id = elem.get('refId', f'index_{i}')
                    self.logger.warning(f"Failed mapping referenceValue {ref_id}: {e}", exc_info=True)

            self.logger.info(f"Successfully parsed {len(records)} reference entries from XML")

        except ET.ParseError as e:
             self.logger.error(f"XML Parse Error in {self.input_path}: {e}")
             raise
        except FileNotFoundError:
            self.logger.error(f"Input file not found: {self.input_path}")
            raise
        except Exception as e:
            self.logger.error(f"Error processing XML file {self.input_path}: {e}")
            raise

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
        level=logging.INFO, # Changed default to INFO for cleaner output, DEBUG is very verbose
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    # Set requests logger level higher if it's too noisy
    logging.getLogger("urllib3").setLevel(logging.WARNING)


    parser = argparse.ArgumentParser(description="Process various entity lists into JSON")
    parser.add_argument(
        "--input-dir", required=True,
        help="Directory containing raw entity list files"
    )
    parser.add_argument(
        "--output-dir", default="processed/entities",
        help="Directory where JSON outputs will be saved"
    )
    parser.add_argument(
        "--debug", action="store_true",
        help="Enable DEBUG level logging"
    )
    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        for handler in logging.getLogger().handlers:
            handler.setLevel(logging.DEBUG)
        logging.debug("DEBUG logging enabled.")


    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    main_logger = logging.getLogger('process_entities')

    if not input_dir.is_dir():
        main_logger.error(f"Input directory not found: {input_dir}")
        return

    processed_files = 0
    skipped_files = 0
    failed_files = 0

    for file_path in sorted(input_dir.rglob("*")):
        if not file_path.is_file():
            continue

        main_logger.info(f"Found file: {file_path.name}")
        suffix = file_path.suffix.lower()
        processor = None

        if suffix == '.csv':
            # Assuming all CSVs are CSL-like for now
            processor = CSLProcessor(file_path, output_dir)
        elif suffix == '.xml':
            # Differentiate based on filename for specific XML types
            if '.xml' in file_path.name.lower():
                 processor = ConsolidatedXMLProcessor(file_path, output_dir)
            # Add elif checks here for other known XML formats if needed
            # elif 'some_other_format' in file_path.name.lower():
            #     processor = SomeOtherXMLProcessor(file_path, output_dir)
            else:
                 # Fallback to the original simple OFAC processor or skip
                 main_logger.warning(f"Unknown XML format for {file_path.name}. Attempting with generic OFACProcessor.")
                 # processor = OFACProcessor(file_path, output_dir) # Optionally try generic
                 # OR skip:
                 main_logger.warning(f"Skipping unknown XML file type: {file_path.name}")
                 skipped_files += 1
                 continue

        else:
            main_logger.info(f"Skipping unsupported file type: {file_path.name}")
            skipped_files += 1
            continue

        if processor:
            try:
                main_logger.info(f"Processing {file_path.name} with {processor.__class__.__name__}...")
                output_path = processor.process()
                print(f"✅ Processed {file_path.name} -> {output_path.name}")
                processed_files += 1
            except Exception as e:
                main_logger.error(f"❌ Failed to process {file_path.name}: {e}", exc_info=args.debug) # Show traceback if debug
                failed_files += 1

    main_logger.info("="*20 + " Processing Summary " + "="*20)
    main_logger.info(f"Processed: {processed_files}")
    main_logger.info(f"Skipped:   {skipped_files}")
    main_logger.info(f"Failed:    {failed_files}")
    main_logger.info("="*58)


if __name__ == "__main__":
    main()

# --- END MODIFIED process_entities.py ---