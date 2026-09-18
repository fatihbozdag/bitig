"""The Corpus collection — an ordered bag of Documents with metadata-aware operations."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from bitig.corpus.document import Document
from bitig.plumbing.hashing import hash_mapping


@dataclass
class Corpus:
    """An ordered collection of Documents that share a metadata schema.

    Iteration yields Documents in the order provided. Equality and hashing ignore order — two
    Corpora with the same documents in different orders hash identically.
    """

    documents: list[Document] = field(default_factory=list)
    language: str = "en"

    def __len__(self) -> int:
        return len(self.documents)

    def __iter__(self) -> Iterator[Document]:
        return iter(self.documents)

    def __getitem__(self, index: int | slice | Sequence[int] | np.ndarray) -> Document | Corpus:
        """Index by int → Document; by slice or array-like → Corpus.

        The array-like branch is needed for sklearn's cross-validation splitters, which
        slice `X` with an ndarray of fold indices.
        """
        if isinstance(index, int | np.integer):
            return self.documents[int(index)]
        if isinstance(index, slice):
            return Corpus(documents=self.documents[index], language=self.language)
        return Corpus(
            documents=[self.documents[int(i)] for i in index],
            language=self.language,
        )

    def filter(self, **query: Any) -> Corpus:
        """Return a new Corpus containing documents whose metadata matches every key in `query`.

        Values may be scalars (exact match) or lists (membership).
        """

        def matches(doc: Document) -> bool:
            for key, expected in query.items():
                actual = doc.metadata.get(key)
                if isinstance(expected, list | tuple | set):
                    if actual not in expected:
                        return False
                elif actual != expected:
                    return False
            return True

        return Corpus(
            documents=[d for d in self.documents if matches(d)],
            language=self.language,
        )

    def groupby(self, field_name: str) -> dict[Any, Corpus]:
        """Group documents by a metadata field value.

        Raises KeyError if any document lacks the field.
        """
        groups: dict[Any, list[Document]] = {}
        for doc in self.documents:
            if field_name not in doc.metadata:
                raise KeyError(f"document {doc.id!r} has no metadata field {field_name!r}")
            groups.setdefault(doc.metadata[field_name], []).append(doc)
        return {k: Corpus(documents=v, language=self.language) for k, v in groups.items()}

    def metadata_column(self, field_name: str) -> list[Any]:
        """Return the list of metadata values at `field_name`, in document order.

        Missing values become None; use `filter` first if you want to exclude them.
        """
        return [d.metadata.get(field_name) for d in self.documents]

    def hash(self) -> str:
        """Stable hash — sorted document hashes + sorted metadata + language."""
        records = sorted((d.id, d.hash, hash_mapping(d.metadata)) for d in self.documents)
        return hash_mapping({"schema": 2, "documents": records, "language": self.language})

    @classmethod
    def from_iterable(cls, docs: Iterable[Document], *, language: str = "en") -> Corpus:
        return cls(documents=list(docs), language=language)
