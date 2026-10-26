"""
Code lists for statistical dimensions: stable English codes for INE's Spanish labels.
Totals keep their own code ("total"), so a published total and the sum of its parts sit side by side.
"""

import re

SEX = {"Total": "total", "Hombres": "male", "Mujeres": "female"}

#: Spanish or foreign nationality (INE's "nacionalidad (española/extranjera)").
NATIONALITY_SPANISH_FOREIGN = {"Total": "total", "Española": "spanish", "Extranjera": "foreign"}


def age_group(label: str) -> str:
    """INE's age groups as codes: "De 20 a 24 años" → Y20T24, "100 y más años" → Y_GE100, "Menos de 16 años" → Y_LT16."""
    if label in ("Todas las edades", "Total"):
        return "total"
    if match := re.fullmatch(r"De (\d+) a (\d+) años", label):
        return f"Y{match[1]}T{match[2]}"
    if match := re.fullmatch(r"(\d+) y más años", label):
        return f"Y_GE{match[1]}"
    if match := re.fullmatch(r"Menos de (\d+) años", label):
        return f"Y_LT{match[1]}"
    raise ValueError(f"Unknown age group: {label!r}")


def mapped(labels, codes: dict[str, str], name: str):
    """The codes of `labels`, failing on any label the code list doesn't know."""
    unknown = set(labels) - set(codes)
    if unknown:
        raise ValueError(f"Unknown {name} labels: {sorted(unknown)}")
    return labels.map(codes)

#: Countries by their INE label, as ISO 3166-1 alpha-3 codes: the same code in every list.
COUNTRIES = {
    "Alemania": "DEU", "Argelia": "DZA", "Argentina": "ARG", "Bangladesh": "BGD", "Bolivia": "BOL", "Brasil": "BRA", "Bulgaria": "BGR",
    "Bélgica": "BEL", "Canadá": "CAN", "Chile": "CHL", "China": "CHN", "Colombia": "COL", "Cuba": "CUB", "Dinamarca": "DNK",
    "Ecuador": "ECU", "Estados Unidos de América": "USA", "Filipinas": "PHL", "Finlandia": "FIN", "Francia": "FRA", "Gambia": "GMB",
    "Ghana": "GHA", "Guinea": "GIN", "Guinea Ecuatorial": "GNQ", "Honduras": "HND", "India": "IND", "Irlanda": "IRL", "Italia": "ITA",
    "Lituania": "LTU", "Mali": "MLI", "Marruecos": "MAR", "Mauritania": "MRT", "México": "MEX", "Moldavia": "MDA", "Nicaragua": "NIC",
    "Nigeria": "NGA", "Noruega": "NOR", "Pakistán": "PAK", "Paraguay": "PRY", "Países Bajos": "NLD", "Perú": "PER", "Polonia": "POL",
    "Portugal": "PRT", "Reino Unido": "GBR", "República Dominicana": "DOM", "Rumanía": "ROU", "Rusia": "RUS", "Senegal": "SEN",
    "Suecia": "SWE", "Suiza": "CHE", "Ucrania": "UKR", "Uruguay": "URY", "Venezuela": "VEN",
}

#: INE's country groups (grandes grupos) and the rests of its lists of main countries. Spain goes
#: apart: its label ("España", "Española") and code depend on the table.
_GROUPS = {
    "Total": "total",
    "Unión Europea (sin España)": "eu",
    "Resto de Europa": "europe_non_eu",
    "África": "africa",
    "América del Norte": "north_america",
    "Centro América y Caribe": "central_america_caribbean",
    "Sudamérica": "south_america",
    "Asia": "asia",
    "Oceanía": "oceania",
    "Apátridas": "stateless",
}

#: Nationality or country of birth, main countries by census section ("Otros países de Europa" is
#: Europe but the countries listed, EU or not).
COUNTRY_MAIN = {
    **_GROUPS,
    **COUNTRIES,
    "Otros países de Europa": "europe_other",
    "Otros países de África": "africa_other",
    "Otros países de América": "america_other",
    "Otros países de Asia": "asia_other",
}

#: Nationality or country of birth, main countries by municipality (and INE's country groups):
#: here "Otros países de Europa" is the rest of Europe outside the EU but the countries listed.
COUNTRY_DETAIL = {
    **_GROUPS,
    **COUNTRIES,
    "Otros países de la Unión Europea": "eu_other",
    "Otros países de Europa": "europe_non_eu_other",
    "Otros países de África": "africa_other",
    "Otro país de Centro América y Caribe": "central_america_caribbean_other",
    "Otros países de Sudamérica": "south_america_other",
    "Otros países de Asia": "asia_other",
}

#: Where residents were born, against where they live (INE's "relación entre lugar de nacimiento y
#: lugar de residencia").
BIRTHPLACE = {
    "Total": "total",
    "Mismo municipio al de residencia": "same_municipality",
    "Distinto municipio de la misma provincia": "same_province",
    "Distinta provincia de la misma comunidad": "same_community",
    "Distinta comunidad": "other_community",
    "Nacido en el extranjero o en antiguos territorios españoles": "abroad",
}

#: When residents came to live in Spain, in INE's bands (as published by census section).
ARRIVAL_SPAIN = {
    "Total": "total",
    "Después de 2020": "after_2020",
    "2011-2020": "2011_2020",
    "2001-2010": "2001_2010",
    "Antes de 2001": "before_2001",
    "No aplicable: siempre ha vivido en España": "always_in_spain",
}

#: Where residents lived before their current municipality (municipalities of 500 residents or more).
PREVIOUS_RESIDENCE = {
    "Total": "total",
    "Siempre ha residido en el mismo municipio": "always_here",
    "Residía en otro municipio": "other_municipality",
    "Residía en el extranjero": "abroad",
    "No consta la residencia anterior": "unknown",
}

#: Where residents lived a year before (provincial capitals and main cities).
RESIDENCE_YEAR_AGO = {
    "Total": "total",
    "Mismo municipio": "same_municipality",
    "Distinto municipio de la misma provincia": "same_province",
    "Distinta provincia de la misma comunidad": "same_community",
    "Distinta comunidad": "other_community",
    "Residía en el extranjero": "abroad",
    "No había nacido": "not_born",
}
