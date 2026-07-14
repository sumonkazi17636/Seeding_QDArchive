"""
classification/file_types.py
Shared file-extension categories used to derive PROJECT_TYPE (part 2, step 1)
and to pick which files get individually classified (part 2, step 3).
"""

# Analysis Data (QDA) files: structured output of qualitative analysis software.
# qdpx is the REFI-QDA interchange format (https://www.qdasoftware.org/); the
# others are the native project-bundle formats of the major CAQDAS tools.
QDA_EXTENSIONS = {
    "qdpx",            # REFI-QDA
    "nvp", "nvpx",      # NVivo
    "mx24", "mx23", "mx22", "mx20", "mx18", "mx12", "mx5",  # MAXQDA
    "atlproj", "hpr7x", "hpr7",  # ATLAS.ti
    "qrk",              # Quirkos
}

# Primary data files: raw qualitative data such as interview transcripts or
# research articles, per the project description's examples.
PRIMARY_DATA_EXTENSIONS = {
    "txt", "pdf", "rtf", "docx", "doc", "odt",
}

# Filenames our own scrapers generate as metadata sidecars (see
# scrapers/datafirst_scraper.py and scrapers/dataverse_no_scraper.py). These
# are not part of the actual research project's data and must be excluded
# before deriving PROJECT_TYPE, otherwise every project would trivially
# appear to have a "data file".
_SIDECAR_SUFFIXES = ("_metadata.json",)
_SIDECAR_NAMES = {"dataset_metadata.json"}


def is_metadata_sidecar(file_name: str) -> bool:
    if file_name in _SIDECAR_NAMES:
        return True
    return any(file_name.endswith(suffix) for suffix in _SIDECAR_SUFFIXES)
