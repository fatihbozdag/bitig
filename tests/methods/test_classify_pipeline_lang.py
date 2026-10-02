"""CV folds keep the corpus language (sklearn passes each fold a plain list)."""

from __future__ import annotations

from bitig.corpus import Corpus, Document
from bitig.features.function_words import FunctionWordExtractor
from bitig.methods.classify import FeatureTransformer


def test_feature_transformer_keeps_corpus_language() -> None:
    docs = [Document(id=f"d{i}", text="der die und in den", metadata={}) for i in range(3)]
    ext = FunctionWordExtractor()
    FeatureTransformer(ext, "de").fit(list(Corpus(documents=docs, language="de").documents))
    fm = ext.transform(Corpus(documents=docs, language="de"))
    assert "der" in fm.feature_names
    assert "about" not in fm.feature_names
