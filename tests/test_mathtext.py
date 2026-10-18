from gomd.mathtext.engine import MathTextEngine, number_to_words

def test_implication_and_decimal_example():
    result=MathTextEngine().normalize("2x^2=9 => x=1,5")
    assert result.text == "два икс в квадрате равно девяти, отсюда следует, что икс равен одному целому пяти десятым"
    assert not result.warnings

def test_zero_and_negative_numbers():
    engine=MathTextEngine()
    assert engine.normalize("0").text == "ноль"
    assert "нулю" in engine.normalize("x=0").text
    assert engine.normalize("-5").text == "минус пять"

def test_powers_roots_and_relations():
    engine=MathTextEngine()
    assert "в квадрате" in engine.normalize("x^2=4").text
    assert engine.normalize(r"\sqrt{9}=3").text == "корень квадратный из девяти равен трём"
    assert "меньше или равно" in engine.normalize("x<=4").text

def test_latex_fraction_explicit_span():
    result=MathTextEngine().normalize(r"$\frac{1}{2}$")
    assert result.text.startswith("дробь:") and not result.warnings

def test_greek_letters_and_functions():
    result=MathTextEngine().normalize("sin(x)=0")
    assert result.text.startswith("синус открываем скобку икс")
    assert "нулю" in result.text

def test_prose_with_formula_suffix():
    result=MathTextEngine().normalize("Найдите x, если 2x^2=9")
    assert result.text.startswith("Найдите x, если два икс")
    assert not result.warnings

def test_subscripts_and_units():
    engine=MathTextEngine()
    assert "с индексом два" in engine.normalize("x_2=4").text
    assert engine.normalize("5 м/с").text == "пять метров в секунду"
    assert "килограммов" in engine.normalize("5 кг").text
    assert "эм цэ в квадрате" in engine.normalize("mc^2=E").text

def test_ambiguous_expression_is_preserved_with_warning():
    source="Найдите производную и оцените результат"
    result=MathTextEngine().normalize(source)
    assert result.text==source

def test_number_decimal_and_cases():
    assert number_to_words("1,5")=="одна целая пять десятых"
    assert number_to_words("1.5", "dative")=="одному целому пяти десятым"


def test_mixed_fraction_uses_singular_ordinal_for_one_half():
    result=MathTextEngine().normalize("3 1/2")
    assert result.text == "три целых одна вторая"
    assert not result.warnings


def test_variable_only_arithmetic_and_standalone_function():
    engine=MathTextEngine()
    assert engine.normalize("x + y").text == "икс плюс игрек"
    result=engine.normalize("sin(x)")
    assert result.text == "синус открываем скобку икс закрываем скобку"
    assert not result.warnings
