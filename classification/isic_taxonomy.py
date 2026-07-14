"""
classification/isic_taxonomy.py
Loads the ISIC Rev. 5 taxonomy (sections + divisions only, i.e. two levels
down as required by the project description) from isic_rev5.csv.

Source: official ISIC Rev. 5 structure CSV published by UN Stats
(https://unstats.un.org/unsd/classifications/Econ/isic), trimmed to the
1-letter section codes and 2-digit division codes.
"""

import csv
import pathlib
from dataclasses import dataclass
from typing import List

CSV_FILE = pathlib.Path(__file__).parent / "isic_rev5.csv"


@dataclass
class Division:
    code: str          # e.g. "62"
    name: str          # e.g. "Computer programming, consultancy..."
    section_code: str  # e.g. "J"
    section_name: str  # e.g. "Information and communication"

    @property
    def full_name(self) -> str:
        """Full class name used as histogram bin labels, e.g. 'J62 - ...'."""
        return f"{self.section_code}{self.code} {self.name}"


def load_divisions(csv_file: pathlib.Path = CSV_FILE) -> List[Division]:
    """Read isic_rev5.csv and pair each division with its parent section."""
    divisions: List[Division] = []
    current_section_code = None
    current_section_name = None

    with open(csv_file, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            if row["level"] == "SECTION":
                current_section_code = row["code"]
                current_section_name = row["name"]
            elif row["level"] == "DIVISION":
                divisions.append(Division(
                    code=row["code"],
                    name=row["name"],
                    section_code=current_section_code,
                    section_name=current_section_name,
                ))

    return divisions
