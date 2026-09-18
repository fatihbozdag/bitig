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
