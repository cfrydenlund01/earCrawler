from pathlib import Path
import json
import shutil
import subprocess


def _ensure_java() -> None:
    java = shutil.which("java")
    if not java:
        raise RuntimeError("Java runtime not found. Install Temurin JDK ≥11.")
    out = subprocess.check_output(["java", "-version"], stderr=subprocess.STDOUT, text=True)
    major = int(out.split('"')[1].split(".")[0])
    if major < 11:
        raise RuntimeError(f"Java {major} detected, need ≥11")


def export_triples(
    data_dir: Path = Path("data"),
    out_ttl: Path = Path("kg/ear_triples.ttl"),
    live: bool = False,
) -> None:
    if live:
        _ensure_java()
    out_ttl.parent.mkdir(parents=True, exist_ok=True)
    with out_ttl.open("w", encoding="utf-8") as f:
        f.write(Path("kg/ear_ontology.ttl").read_text())
        for source in ("ear", "nsf"):
            fn = data_dir / f"{source}_corpus.jsonl"
            if not fn.exists():
                continue
            for line in fn.read_text(encoding="utf-8").splitlines():
                if not line:
                    continue
                rec = json.loads(line)
                pid = rec["identifier"].replace(":", "_")
                f.write(f"\nex:paragraph_{pid} a ex:Paragraph ;\n")
                f.write(f'    ex:hasText """{rec["text"].replace("\"", "\\\"")}""" ;\n')
                if source == "ear":
                    part = rec["identifier"].split(":")[0]
                    f.write(f'    ex:part "{part}" ;\n')
                f.write("\n")
                for ent in rec.get("entities", {}).get("orgs", []):
                    eid = ent.replace(" ", "_")
                    f.write(f"ex:paragraph_{pid} ex:mentions ex:entity_{eid} .\n")
                    f.write(f"ex:entity_{eid} a ex:Entity ; rdfs:label \"{ent}\" .\n")

