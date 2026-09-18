"""High-level spaCy parsing wrapper, DocBin-cached."""

from __future__ import annotations

import hashlib
import zlib
from collections.abc import Iterator
from functools import cached_property
from pathlib import Path
from typing import Literal

import spacy
from spacy.language import Language
from spacy.tokens import Doc, DocBin

from bitig.corpus import Corpus, Document
from bitig.languages import get_language
from bitig.plumbing.logging import get_logger
from bitig.preprocess.cache import DocBinCache, cache_key

_log = get_logger(__name__)


class ParsedCorpus:
    """A corpus paired with its parsed spaCy `Doc` objects (index-aligned)."""

    def __init__(self, corpus: Corpus, docs: list[Doc]) -> None:
        if len(corpus) != len(docs):
            raise ValueError("corpus and docs must have the same length")
        self.corpus = corpus
        self._docs = docs

    def __len__(self) -> int:
        return len(self._docs)

    def spacy_docs(self) -> Iterator[Doc]:
        return iter(self._docs)

    def pairs(self) -> Iterator[tuple[Document, Doc]]:
        return zip(self.corpus.documents, self._docs, strict=True)


class SpacyPipeline:
    """Parse a `Corpus` into spaCy `Doc`s, caching results as `DocBin` blobs on disk.

    Supports two backends behind a single interface:
      - ``backend="spacy"``        — ``spacy.load(model)``
      - ``backend="spacy_stanza"`` — ``spacy_stanza.load_pipeline(lang=model)``

    Both produce native spaCy ``Doc`` objects so downstream extractors don't care which backend
    produced them. When ``language``/``backend``/``model`` are omitted, defaults come from the
    ``bitig.languages`` registry — English resolves to ``backend="spacy"`` with
    ``model="en_core_web_trf"``.
    """

    def __init__(
        self,
        *,
        language: str = "en",
        model: str | None = None,
        backend: Literal["spacy", "spacy_stanza"] | None = None,
        cache_dir: Path | str = ".bitig/cache/docbin",
        exclude: list[str] | None = None,
        reuse_cache: bool = True,
    ) -> None:
        spec = get_language(language)
        self.language = spec.code
        self.model = model if model is not None else spec.default_model
        self.backend = backend if backend is not None else spec.backend
        self.exclude = list(exclude or [])
        self.reuse_cache = reuse_cache
        self.cache = DocBinCache(Path(cache_dir))
        self._nlp: Language | None = None

    @property
    def nlp(self) -> Language:
        if self._nlp is None:
            if self.backend == "spacy_stanza":
                if self.exclude:
                    _log.warning(
                        "exclude=%s ignored on spacy_stanza backend "
                        "(Stanza attributes are set in the tokenizer, not pipeline components)",
                        self.exclude,
                    )
                try:
                    import spacy_stanza
                except ImportError as e:
                    raise ImportError(
                        "bitig requires spacy-stanza for the 'spacy_stanza' backend. "
                        "Install with: uv pip install 'bitig[turkish]'"
                    ) from e
                _log.info("loading Stanza pipeline via spacy-stanza: lang=%s", self.model)
                try:
                    self._nlp = spacy_stanza.load_pipeline(self.model)
                except FileNotFoundError as e:
                    raise RuntimeError(
                        f"Stanza model for language {self.model!r} not found. "
                        f"Run: python -c \"import stanza; stanza.download('{self.model}')\""
                    ) from e
            else:
                _log.info("loading spaCy model: %s", self.model)
                self._nlp = spacy.load(self.model, exclude=self.exclude)
        return self._nlp

    @property
    def spacy_version(self) -> str:
        return str(spacy.__version__)

    @property
    def backend_version(self) -> str:
        """Structured version string used in cache keys.

        Native backend: ``'spacy=<version>'`` — matches prior cache-key format, preserves English
        caches built on older bitig versions.
        Stanza backend: ``'spacy_stanza=<v>;stanza=<v>'`` — structurally distinct from native, so
        cross-backend cache collisions are impossible.
        """
        if self.backend == "spacy_stanza":
            from importlib.metadata import version

            return f"spacy_stanza={version('spacy_stanza')};stanza={version('stanza')}"
        return f"spacy={self.spacy_version}"

    @cached_property
    def model_identity(self) -> str:
        """Fingerprint the loaded pipeline, including Stanza's external weight files."""
        digest = hashlib.sha256(self.nlp.to_bytes())
        if self.backend == "spacy_stanza":
            stanza_pipeline = getattr(self.nlp.tokenizer, "snlp", None)
            if stanza_pipeline is None:
                raise RuntimeError("Stanza tokenizer does not expose model identity")
            paths = set()
            for processor in stanza_pipeline.processors.values():
                for key, value in processor.config.items():
                    if key.endswith("_path") and isinstance(value, str) and Path(value).is_file():
                        paths.add(value)
            if not paths:
                raise RuntimeError(
                    "Cannot fingerprint Stanza model weights; refusing unsafe cache reuse"
                )
            for path in sorted(paths):
                with Path(path).open("rb") as stream:
                    for block in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(block)
        return digest.hexdigest()

    def _key(self, doc: Document) -> str:
        return cache_key(
            doc.hash,
            self.model,
            self.backend_version + ";weights=" + self.model_identity,
            self.exclude,
        )

    def parse(self, corpus: Corpus) -> ParsedCorpus:
        parsed: list[Doc | None] = []
        to_parse_indices: list[int] = []
        to_parse_texts: list[str] = []

        for i, doc in enumerate(corpus.documents):
            cached = self.cache.get(self._key(doc)) if self.reuse_cache else None
            if cached is not None:
                try:
                    bin_ = DocBin().from_bytes(cached)
                    (spacy_doc,) = list(bin_.get_docs(self.nlp.vocab))
                    if spacy_doc.text != doc.text:
                        raise ValueError("cached text mismatch")
                    parsed.append(spacy_doc)
                    continue
                except (ValueError, TypeError, KeyError, EOFError, zlib.error):
                    _log.warning("Corrupt cached parse for %s; reparsing", doc.id)
            parsed.append(None)
            to_parse_indices.append(i)
            to_parse_texts.append(doc.text)

        if to_parse_texts:
            _log.info(
                "parsing %d documents (%d cached)",
                len(to_parse_texts),
                len(corpus) - len(to_parse_texts),
            )
            for i, spacy_doc in zip(to_parse_indices, self.nlp.pipe(to_parse_texts), strict=True):
                parsed[i] = spacy_doc
                bin_ = DocBin(docs=[spacy_doc])
                self.cache.put(self._key(corpus.documents[i]), bin_.to_bytes())

        # At this point, every slot has been populated either from cache or from fresh parsing.
        final_docs: list[Doc] = [d for d in parsed if d is not None]
        if len(final_docs) != len(parsed):
            raise RuntimeError("internal error: some documents were not parsed")
        return ParsedCorpus(corpus=corpus, docs=final_docs)
