from app.transcription.numbers import spoken_numbers_to_digits


def test_single_number_words_become_digits():
    assert spoken_numbers_to_digits("Pain score two out of ten.") == "Pain score 2 out of 10."
    assert spoken_numbers_to_digits("Take two.") == "Take 2."


def test_compounds_decimals_and_blood_pressure_shorthand():
    assert spoken_numbers_to_digits("thirty six point eight") == "36.8"
    assert spoken_numbers_to_digits("twenty-two milligrams") == "22 milligrams"
    assert spoken_numbers_to_digits("one hundred and twenty two") == "122"
    assert spoken_numbers_to_digits("one twenty two over seventy eight") == "122 over 78"
    assert spoken_numbers_to_digits("two and a half tablets") == "2.5 tablets"
    assert spoken_numbers_to_digits("a hundred") == "100"


def test_words_that_are_not_counts_stay_words():
    assert spoken_numbers_to_digits("one of the tablets") == "one of the tablets"
    assert spoken_numbers_to_digits("no one else") == "no one else"
    assert spoken_numbers_to_digits("twice daily") == "twice daily"
    assert spoken_numbers_to_digits("Oh, hello.") == "Oh, hello."


def test_digits_already_written_stay_digits():
    assert spoken_numbers_to_digits("SpO2 98% and pulse 72.") == "SpO2 98% and pulse 72."


def test_arabic_number_words_become_digits():
    assert spoken_numbers_to_digits("خذ اثنين حبة") == "خذ 2 حبة"
    assert spoken_numbers_to_digits("اثنين وعشرين") == "22"
