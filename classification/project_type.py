"""
classification/project_type.py
Derives PROJECT_TYPE from a project's FILES rows, per the project
description (Part 2, Step 1):

    QDA_PROJECT   if there is a file with a QDA file extension
    QD_PROJECT    if not a QDA_PROJECT and there are primary data files
    OTHER_PROJECT if not a QD_PROJECT and there are (other) valid data files
    NOT_A_PROJECT if nothing can be derived about file types
"""

from typing import Iterable

from classification.file_types import (
    QDA_EXTENSIONS,
    PRIMARY_DATA_EXTENSIONS,
    is_metadata_sidecar,
)

QDA_PROJECT = "QDA_PROJECT"
QD_PROJECT = "QD_PROJECT"
OTHER_PROJECT = "OTHER_PROJECT"
NOT_A_PROJECT = "NOT_A_PROJECT"


def classify_project_type(files: Iterable) -> str:
    """
    files: iterable of objects/rows with 'file_name' and 'file_type' fields
    (sqlite3.Row or dict both work).
    """
    real_files = [f for f in files if not is_metadata_sidecar(f["file_name"])]

    if not real_files:
        return NOT_A_PROJECT

    extensions = {f["file_type"].lower() for f in real_files if f["file_type"]}

    if extensions & QDA_EXTENSIONS:
        return QDA_PROJECT
    if extensions & PRIMARY_DATA_EXTENSIONS:
        return QD_PROJECT
    if extensions:
        return OTHER_PROJECT
    return NOT_A_PROJECT
