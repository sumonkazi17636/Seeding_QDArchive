"""
classification/isic_taxonomy.py
Loads the ISIC Rev. 5 taxonomy from the official UN Statistics Division
structure.

Two products are exposed for each of the 87 divisions (the two-levels-down
target required by the project description):

* ``code`` / ``name`` / ``section_*`` — the division itself and its parent
  section (used for reporting and as the class label);
* ``reference_text`` — an enriched bag of official ISIC vocabulary for the
  division, built from the division name plus the names of every group and
  class beneath it. Grounding each division in its own official sub-category
  vocabulary makes the TF-IDF match far more discriminative than matching on
  the short division title alone.

Source: ``ISIC_Rev_5_english_structure.csv`` (UN Statistics Division), shipped
in this repository as ``isic_rev5_full.csv`` (sections, divisions, groups and
classes). ``isic_rev5.csv`` (sections + divisions only) is kept for reference.
"""

import csv
import pathlib
from dataclasses import dataclass, field
from typing import List

FULL_CSV = pathlib.Path(__file__).parent / "isic_rev5_full.csv"
SLIM_CSV = pathlib.Path(__file__).parent / "isic_rev5.csv"


@dataclass
class Division:
    code: str
    name: str
    section_code: str
    section_name: str
    reference_text: str = ""
    _descendants: List[str] = field(default_factory=list)

    @property
    def full_name(self) -> str:
        """Label used in tables and histograms, e.g. 'R86 Human health activities'."""
        return f"{self.section_code}{self.code} {self.name}"


def load_divisions(csv_file: pathlib.Path = FULL_CSV) -> List[Division]:
    """Read the full ISIC structure and return the 87 divisions, each with a
    ``reference_text`` enriched by the names of its groups and classes."""
    if not csv_file.exists():
        csv_file = SLIM_CSV  # graceful fallback

    section_code = section_name = None
    divisions: List[Division] = []
    by_code = {}

    with open(csv_file, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            level, code, name = row["level"], row["code"], row["name"]
            if level == "SECTION":
                section_code, section_name = code, name
            elif level == "DIVISION":
                div = Division(code=code, name=name,
                               section_code=section_code,
                               section_name=section_name)
                divisions.append(div)
                by_code[code] = div
            elif level in ("GROUP", "CLASS"):
                parent = code[:2]  # division prefix
                if parent in by_code:
                    by_code[parent]._descendants.append(name)

    for div in divisions:
        parts = [div.section_name, div.name] + div._descendants
        div.reference_text = " ".join(parts)

    return divisions
