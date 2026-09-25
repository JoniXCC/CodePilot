from weather.convert import fahrenheit_to_celsius


def describe(city: str, high_f: float) -> str:
    return f"{city}: high of {fahrenheit_to_celsius(high_f):.1f}°C"
