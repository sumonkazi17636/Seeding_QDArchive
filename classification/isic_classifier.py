"""
classification/isic_classifier.py
ISIC Rev. 5 classifier for QDArchive projects (Part 2, Step 2).

Limitation (documented, see README "Part 2" section): the actual downloaded
research files (data/) are not available in this local checkout, only the
metadata captured in Part 1 (title, description, keywords). This classifier
therefore runs on metadata text only. If file text ever becomes available,
`ProjectDoc.extra_text` is the place to feed it in — the rest of the
pipeline does not need to change.

Approach: no labeled training data exists for this task, so we use an
offline, reproducible TF-IDF + cosine-similarity classifier rather than a
hand-rolled keyword list. Each ISIC division's (section name + division
name) is treated as a reference document; each project's metadata text is
compared against all 87 division documents, and the closest one becomes the
primary_class. A second class is only reported if it scores close enough to
the top match to be a genuine runner-up, otherwise secondary_class is left
empty (per the spreadsheet: "secondary_class // if any").
"""

from dataclasses import dataclass, field
from typing import List, Optional

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from classification.isic_taxonomy import Division, load_divisions

# Sentinel used only when a project's metadata is too sparse to produce any
# vocabulary overlap with the ISIC taxonomy at all (rare — see README).
UNCLASSIFIED_CODE = "ZZ"
UNCLASSIFIED_NAME = "Unclassified (insufficient metadata)"

# A second class is only reported if its score is within this fraction of
# the top score, so "secondary_class // if any" isn't populated with noise.
SECONDARY_MARGIN = 0.6


@dataclass
class ProjectDoc:
    project_id: int
    text: str


@dataclass
class ClassificationResult:
    project_id: int
    primary_code: str
    primary_name: str
    secondary_code: Optional[str] = None
    secondary_name: Optional[str] = None
    tags: List[str] = field(default_factory=list)


class IsicClassifier:
    def __init__(self, divisions: List[Division] = None):
        self.divisions = divisions or load_divisions()
        # Each division is represented by its enriched reference text
        # (section + division + all group/class names). Falls back to the
        # bare "section division" label if the enriched text is unavailable.
        self.division_docs = [
            d.reference_text or f"{d.section_name} {d.name}"
            for d in self.divisions
        ]
        self.vectorizer: TfidfVectorizer = None
        self.division_vectors = None
        self.feature_names = None

    def fit(self, project_docs: List[ProjectDoc]) -> None:
        self._project_docs = project_docs
        corpus = self.division_docs + [d.text for d in project_docs]
        self.vectorizer = TfidfVectorizer(
            stop_words="english", ngram_range=(1, 2), min_df=1
        )
        matrix = self.vectorizer.fit_transform(corpus)
        n_div = len(self.division_docs)
        self.division_vectors = matrix[:n_div]
        self.project_vectors = matrix[n_div:]
        self.feature_names = self.vectorizer.get_feature_names_out()

    def classify_all(self, top_tags: int = 5) -> List[ClassificationResult]:
        """Must call fit() first. Returns one result per project, in the
        same order as the project_docs passed to fit()."""
        sims = cosine_similarity(self.project_vectors, self.division_vectors)

        results = []
        for row_idx, scores in enumerate(sims):
            project_id = self._project_docs[row_idx].project_id
            order = scores.argsort()[::-1]
            top_idx = order[0]
            top_score = scores[top_idx]

            if top_score <= 0:
                primary_code, primary_name = UNCLASSIFIED_CODE, UNCLASSIFIED_NAME
                secondary_code = secondary_name = None
            else:
                top_div = self.divisions[top_idx]
                primary_code = f"{top_div.section_code}{top_div.code}"
                primary_name = top_div.full_name
                secondary_code = secondary_name = None

                second_idx = order[1]
                second_score = scores[second_idx]
                if second_score > 0 and second_score >= SECONDARY_MARGIN * top_score:
                    second_div = self.divisions[second_idx]
                    secondary_code = f"{second_div.section_code}{second_div.code}"
                    secondary_name = second_div.full_name

            results.append(ClassificationResult(
                project_id=project_id,
                primary_code=primary_code,
                primary_name=primary_name,
                secondary_code=secondary_code,
                secondary_name=secondary_name,
                tags=self._extract_tags(row_idx, top_tags),
            ))

        return results

    def _extract_tags(self, row_idx: int, top_n: int) -> List[str]:
        vector = self.project_vectors[row_idx]
        if vector.nnz == 0:
            return []
        cols = vector.indices
        data = vector.data
        order = data.argsort()[::-1][:top_n]
        return [self.feature_names[cols[i]] for i in order]


def build_project_text(title: str, description: str, keywords: List[str]) -> str:
    parts = [title or "", description or "", " ".join(keywords)]
    return " ".join(p for p in parts if p)
