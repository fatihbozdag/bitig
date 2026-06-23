"""Turkish dotted-I folding: casing must not fragment a token or split a word in two types."""

import unicodedata

from bitig.features.mfw import _tokenise
from bitig.methods.zeta import _tokens as zeta_tokens
from bitig.plumbing.textnorm import fold_lower


def test_dotted_capital_i_folds_to_plain_i():
    # "İ".lower() == "i" + U+0307, so İçin used to count as a different type than için.
    assert fold_lower("İçin") == fold_lower("için") == "için"
    assert fold_lower("İstanbul") == "istanbul"
    assert fold_lower("TÜRKİYE") == fold_lower("Türkiye") == "türkiye"
    assert fold_lower("KATİL") == fold_lower("Katil") == "katil"  # naming terms case-stable
    assert fold_lower("Şüpheli") == "şüpheli"


def test_no_combining_marks_survive():
    assert not any(unicodedata.combining(c) for c in fold_lower("İzmir İYİ İsrail"))


def test_precomposed_accents_survive_from_nfd():
    # NFC-first means stripping combining marks does NOT destroy real accents.
    nfd = unicodedata.normalize("NFD", "Café")  # C a f e + combining acute
    assert any(unicodedata.combining(c) for c in nfd)  # sanity: input really is decomposed
    folded = fold_lower(nfd)
    assert not any(unicodedata.combining(c) for c in folded)  # no stray marks
    assert folded == fold_lower("Café") != "cafe"  # accent preserved; NFD and NFC agree
    assert fold_lower("çşğıöü") == "çşğıöü"


def test_ascii_I_stays_i_language_neutral():
    # ASCII "I" folds to "i", not the Turkish dotless "ı"; the tokenizer is neutral.
    assert fold_lower("I am") == "i am"


def test_tokenisers_fold_dotted_i():
    assert _tokenise("İçin için", lowercase=True) == ["için", "için"]
    assert _tokenise("İçin için", lowercase=False) == ["İçin", "için"]  # off = unchanged
    assert zeta_tokens("İstanbul İstanbul") == ["istanbul", "istanbul"]


def _tr_corpus(*texts: str):
    from bitig.corpus import Corpus, Document

    return Corpus(
        documents=[Document(id=f"d{i}", text=t) for i, t in enumerate(texts)], language="tr"
    )


def test_function_words_count_dotted_i_forms():
    # function_words lowercases before tokenising, so "İçin" used to split into i + çin.
    from bitig.features.function_words import FunctionWordExtractor

    fm = FunctionWordExtractor(wordlist=["için", "i"]).fit_transform(_tr_corpus("İçin için"))
    counts = dict(zip(fm.feature_names, fm.X[0], strict=True))
    assert counts == {"için": 2.0, "i": 0.0}


def test_word_ngrams_do_not_split_dotted_i():
    from bitig.features.ngrams import WordNgramExtractor

    fm = WordNgramExtractor(lowercase=True).fit_transform(_tr_corpus("İstanbul istanbul"))
    assert fm.feature_names == ["istanbul"]
    assert fm.X[0, 0] == 2.0
    off = WordNgramExtractor(lowercase=False).fit_transform(_tr_corpus("İstanbul istanbul"))
    assert sorted(off.feature_names) == ["istanbul", "İstanbul"]  # off = case kept


def test_char_ngrams_have_no_combining_dot():
    from bitig.forensic.char_ngrams import CategorizedCharNgramExtractor

    fm = CategorizedCharNgramExtractor(n=3, lowercase=True).fit_transform(_tr_corpus("İzmir izmir"))
    assert not any(unicodedata.combining(c) for name in fm.feature_names for c in name)


def test_distortion_masks_sentence_initial_dotted_i_function_word():
    from bitig.forensic.distortion import distort_text

    # dv_ma keeps listed function words and masks every other letter.
    out = distort_text("İçin geldi", mode="dv_ma", function_words={"için"})
    assert out.split()[0] == "İçin"  # recognised as a function word, kept verbatim
    assert out.split()[1] == "*****"
