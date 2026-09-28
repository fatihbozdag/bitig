"""run_study must honour preprocess.language (audit 2026-09-26 N-P1.13)."""

from __future__ import annotations

from pathlib import Path

import yaml

from bitig import runner
from bitig.features.function_words import FunctionWordExtractor
from bitig.features.readability import ReadabilityExtractor

_TR = [
    "Bir varmış bir yokmuş, evvel zaman içinde küçük bir köyde yaşlı bir adam yaşarmış.",
    "Adam her sabah erkenden kalkar ve bahçedeki ağaçlara su verirmiş, çünkü onları çok severmiş.",
    "Bir gün köye uzak diyarlardan bir yolcu gelmiş ve adamın kapısını çalmış.",
]


def test_turkish_study_uses_turkish_function_words_and_readability(tmp_path, monkeypatch):
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    for i, text in enumerate(_TR):
        (corpus_dir / f"d{i}.txt").write_text(text * 3, encoding="utf-8")
    study = {
        "name": "tr",
        "corpus": {"path": str(corpus_dir)},
        "preprocess": {"language": "tr"},
        "features": [
            {"id": "fw", "type": "function_word"},
            {"id": "read", "type": "readability"},
        ],
        "methods": [{"id": "pca", "kind": "reduce", "features": "fw", "n_components": 2}],
        "output": {"dir": str(tmp_path / "out"), "timestamp": False},
    }
    path = tmp_path / "study.yaml"
    path.write_text(yaml.safe_dump(study), encoding="utf-8")

    seen: dict[str, list[str]] = {}

    def spy(cls: type, key: str) -> type:
        class Spy(cls):  # type: ignore[misc, valid-type]
            def fit_transform(self, corpus):  # type: ignore[no-untyped-def]
                fm = super().fit_transform(corpus)
                seen[key] = list(fm.feature_names)
                seen[key + "_lang"] = [corpus.language]
                return fm

        return Spy

    monkeypatch.setitem(runner._FEATURE_BUILDERS, "function_word", spy(FunctionWordExtractor, "fw"))
    monkeypatch.setitem(runner._FEATURE_BUILDERS, "readability", spy(ReadabilityExtractor, "read"))
    runner.run_study(path)

    assert seen["fw_lang"] == ["tr"]
    assert "ve" in seen["fw"] and "the" not in seen["fw"]
    assert any("atesman" in name for name in seen["read"])
    assert not any(name == "flesch" for name in seen["read"])
    assert Path(tmp_path / "out").exists()
