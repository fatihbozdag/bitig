"""German / French syllable counters against gold syllabifications (audit 2026-09-26 P2).

The gold counts are standard syllabifications (German: orthographic = spoken
syllables; French: spoken syllables, mute final -e not counted), assembled for
this test. Known failures are listed so the accuracy figure stays honest.
"""

from __future__ import annotations

import pytest

from bitig.languages.readability_de import count_syllables_de
from bitig.languages.readability_fr import count_syllables_fr

DE_GOLD = {
    "Haus": 1, "Computer": 3, "schwimmen": 2, "Abend": 2, "aber": 2, "Oma": 2, "Igel": 2,
    "über": 2, "Idee": 2, "Ecke": 2, "einen": 2, "Schule": 2, "Freundschaft": 2, "Kind": 1,
    "Kinder": 2, "Mädchen": 2, "Bäume": 2, "Häuser": 2, "Feier": 2, "freuen": 2, "bauen": 2,
    "Theater": 3, "Universität": 5, "Regierung": 3, "Bundesrepublik": 5,
    "Geschwindigkeit": 4, "Straße": 2, "Brief": 1, "Liebe": 2, "Tier": 1, "Spiel": 1,
    "spielen": 2, "viel": 1, "Bier": 1, "Fernseher": 3, "Zeitung": 2, "Leute": 2, "heute": 2,
    "Eule": 2, "Auto": 2, "Kaffee": 2, "Tee": 1, "See": 1, "Boot": 1, "Saal": 1, "Haar": 1,
    "Mai": 1, "Bayern": 2, "Papier": 2, "Musik": 2, "Natur": 2, "Lehrer": 2, "fahren": 2,
    "Uhr": 1, "Stuhl": 1, "Fenster": 2, "Wasser": 2, "essen": 2, "trinken": 2,
    "schreiben": 2, "lesen": 2, "Buch": 1, "Bücher": 2, "Schüler": 2, "Arbeit": 2,
    "Arbeiter": 3, "wichtig": 2, "interessant": 4, "Information": 5, "Nation": 3, "Kreuz": 1,
    "neun": 1, "Häuschen": 2, "äußerst": 2, "Ruhe": 2, "ruhig": 2, "Reise": 2, "reisen": 2,
    "Eier": 2, "Ei": 1, "Seite": 2, "sieben": 2, "Typ": 1, "System": 2, "Hobby": 2,
    "Party": 2, "Familie": 4, "Linie": 3, "Studie": 3, "Museum": 3, "Mutter": 2, "Vater": 2,
    "Bruder": 2, "Schwester": 2, "Großmutter": 3, "Apfel": 2, "Banane": 3, "Kartoffel": 3,
    "Gemüse": 3, "Frühstück": 2, "Abendessen": 4,
}  # fmt: skip
DE_KNOWN_MISSES = {"Familie", "Linie", "Studie", "Museum"}  # -ie + vowel, e-u hiatus

FR_GOLD = {
    "chat": 1, "bonjour": 2, "ami": 2, "élan": 2, "idée": 2, "école": 2, "maison": 2,
    "enfant": 2, "beaucoup": 2, "livre": 1, "table": 1, "porte": 1, "homme": 1, "femme": 1,
    "père": 1, "mère": 1, "frère": 1, "eau": 1, "beau": 1, "oiseau": 2, "voiture": 2,
    "nation": 2, "université": 5, "information": 4, "petit": 2, "grand": 1, "rouge": 1,
    "vert": 1, "bleu": 1, "noir": 1, "blanc": 1, "jour": 1, "nuit": 1, "pluie": 1, "roi": 1,
    "loi": 1, "voix": 1, "moi": 1, "toi": 1, "joie": 1, "vie": 1, "rue": 1, "musique": 2,
    "politique": 3, "économie": 4, "pied": 1, "rien": 1, "bien": 1, "chien": 1, "lieu": 1,
    "stylo": 2, "écoles": 2, "tables": 1, "très": 1, "les": 1, "le": 1, "théâtre": 2,
    "musée": 2, "année": 2, "journée": 2, "soirée": 2, "réunion": 3, "poème": 2, "Noël": 2,
    "naïf": 2, "aussi": 2, "autre": 1, "peuple": 1, "heure": 1, "fleur": 1, "cœur": 1,
    "soeur": 1, "travail": 2, "soleil": 2, "fille": 1, "famille": 2, "gentil": 2,
    "guerre": 1, "langue": 1, "aimer": 2, "parler": 2, "chanter": 2, "parlent": 1,
    "client": 2, "ville": 1, "monde": 1, "pays": 2, "question": 2, "quatre": 1, "quand": 1,
    "gare": 1, "guide": 1, "orange": 2, "jardin": 2, "cheval": 2, "animal": 3, "hôpital": 3,
    "téléphone": 3, "ordinateur": 4, "facile": 2, "difficile": 3, "possible": 2,
    "important": 3, "bonheur": 2, "chocolat": 3,
}  # fmt: skip
FR_KNOWN_MISSES = {"parlent", "client"}  # verb -ent, i-e hiatus


@pytest.mark.parametrize(
    ("count", "gold", "misses"),
    [
        (count_syllables_de, DE_GOLD, DE_KNOWN_MISSES),
        (count_syllables_fr, FR_GOLD, FR_KNOWN_MISSES),
    ],
)
def test_counter_matches_gold_except_known_misses(count, gold, misses) -> None:
    wrong = {w for w, g in gold.items() if count(w) != g}
    assert wrong == misses
    assert 1 - len(wrong) / len(gold) >= 0.95


def test_words_pyphen_undercounted_are_now_right() -> None:
    for word in ("Abend", "aber", "Oma", "Igel", "über", "Idee", "Ecke", "einen"):
        assert count_syllables_de(word) == 2, word
    for word in ("ami", "élan", "idée", "école"):
        assert count_syllables_fr(word) == 2, word
