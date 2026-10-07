from localvoice.textproc import clean


def test_clean_whitespace_and_trailing_space():
    assert clean("  hello   world ") == "hello world "
    assert clean("hello", trailing_space=False) == "hello"
    assert clean("   ") == ""


def test_replacements_whole_words_case_insensitive():
    reps = {"local voice": "LocalVoice", "cat": "dog"}
    assert clean("I use Local Voice daily, concatenate cat.", reps, False) == "I use LocalVoice daily, concatenate dog."


def test_replacement_with_backslash_is_literal():
    assert clean("go to c drive", {"c drive": r"C:\\"}, False) == r"go to C:\\"
