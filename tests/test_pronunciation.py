from gomd.pronunciation.dictionary import PronunciationDictionary, PronunciationRule

def test_word_boundaries_and_case_insensitive():
    d=PronunciationDictionary([PronunciationRule("cat","kat")])
    assert d.apply("cat scatter CAT") == "kat scatter kat"

def test_language_and_engine_scoping():
    d=PronunciationDictionary([PronunciationRule("circumflex accent","циркумфлекс экцент",language="en-GB",engine_id="piper-cli")])
    assert d.apply("circumflex accent",language="en-GB",engine_id="piper-cli")=="циркумфлекс экцент"
    assert d.apply("circumflex accent",language="ru",engine_id="piper-cli")=="circumflex accent"

def test_json_roundtrip(tmp_path):
    d=PronunciationDictionary([PronunciationRule("zero","зиро",language="en-GB",priority=4)])
    p=tmp_path/"dictionary.json"; d.save_json(p)
    loaded=PronunciationDictionary.load_json(p)
    assert loaded.rules[0].priority==4
    assert loaded.apply("zero",language="en-GB")=="зиро"


def test_higher_priority_wins_for_identical_source():
    d=PronunciationDictionary([
        PronunciationRule("zero","low",priority=10),
        PronunciationRule("zero","high",priority=100),
    ])
    assert d.apply("zero") == "high"
