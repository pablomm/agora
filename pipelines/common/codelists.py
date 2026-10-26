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

#: Born in Spain or abroad (INE's "país/lugar de nacimiento (España/extranjero)").
BORN = {"Total": "total", "España": "spain", "Extranjero": "abroad"}

#: Highest level of education completed, grouped (as published by census section): the groups of
#: EDUCATION_DETAIL.
EDUCATION_GROUPED = {
    "Total": "total",
    "Educación primaria e inferior": "primary_or_less",
    "Primera etapa de Educación Secundaria y similar": "lower_secondary",
    "Segunda etapa de Educación Secundaria y Educación Postsecundaria no Superior": "upper_secondary",
    "Educación superior": "tertiary",
}

#: Highest level of education completed, in detail (municipalities of 500 residents or more).
EDUCATION_DETAIL = {
    "Total": "total",
    "Sin estudios": "no_schooling",
    "Educación primaria": "primary",
    "Primera etapa de Educación Secundaria y similar": "lower_secondary",
    "Segunda etapa de educación secundaria, con orientación general": "upper_secondary_general",
    "Segunda etapa de educación secundaria con orientación profesional, Educación postsecundaria no superior": "upper_secondary_vocational",
    "Enseñanzas de formación profesional, artes plásticas y diseño y deportivas de grado superior y equivalentes": "vocational_higher",
    "Grados universitarios de hasta 240 créditos ECTS, diplomados universitarios y equivalentes": "bachelor",
    "Grados universitarios de más de 240 créditos ECTS, licenciados y equivalentes": "bachelor_long",
    "Másteres, especialidades en Ciencias de la Salud por el sistema de residencia y similares": "master",
    "Doctorado universitario": "doctorate",
}

#: Studies in progress, grouped (municipalities of 500 residents or more).
STUDYING = {
    "Total": "total",
    "Educación primaria e inferior": "studying_primary_or_less",
    "Primera etapa de Educación Secundaria y similar": "studying_lower_secondary",
    "Segunda etapa de educación secundaria, con orientación general": "studying_upper_secondary_general",
    "Segunda etapa de Educación Secundaria, con orientación profesional (con y sin continuidad en la educación superior), Educación postsecundaria no superior": "studying_upper_secondary_vocational",
    "Educación superior": "studying_tertiary",
    "Cursa estudios pero no hay información sobre los mismos": "studying_unknown",
    "No cursa estudios": "not_studying",
}

#: Relation with economic activity, residents aged 16 and over (INE's "relación con la actividad (agrupado)").
ACTIVITY = {
    "Total": "total",
    "Ocupado/a": "employed",
    "Parado/a": "unemployed",
    "Perceptor/a pensión de incapacidad, jubilación, prejubilación": "pensioner",
    "Estudiante": "student",
    "Otra situación de inactividad": "other_inactive",
}

#: Occupation of the employed, aggregated (census sections): groups of CNO-11 major groups.
OCCUPATION_GROUP = {
    "Total": "total",
    "Directores/gerentes y profesionales/técnicos de nivel medio o alto": "high_skilled",
    "Trabajadores cualificados y oficiales/operarios de nivel bajo": "mid_skilled",
    "Ocupaciones elementales": "elementary",
    "No consta": "not_stated",
}

#: Economic activity of the employed, by sector (census sections): groups of CNAE-2009 sections.
SECTOR = {
    "Total CNAE": "total",
    "Agricultura, ganadería y pesca": "agriculture",
    "Industria": "industry",
    "Construcción": "construction",
    "Servicios": "services",
    "No consta": "not_stated",
}

#: Professional status of the employed, aggregated (census sections).
PROFESSIONAL_STATUS = {"Total": "total", "Trabajador por cuenta propia": "self_employed", "Trabajador por cuenta ajena y otra situación": "employee"}

#: Professional status of the employed, in detail (municipalities of 500 residents or more): the
#: self-employed with or without staff, employees permanent or temporary.
PROFESSIONAL_STATUS_DETAIL = {
    "Total": "total",
    "Trabajador por cuenta propia que emplea personal": "employer",
    "Trabajador por cuenta propia que no emplea personal": "own_account",
    "Trabajador por cuenta ajena fijo o indefinido, y otra situación": "employee_permanent",
    "Trabajador por cuenta ajena temporal": "employee_temporary",
}

#: Marital status of residents aged 16 and over (annual census): INE gives divorced and separated together.
MARITAL_STATUS = {
    "Total": "total",
    "Soltero/a": "single",
    "Casado/a": "married",
    "Viudo/a": "widowed",
    "Divorciado/a o separado/a": "divorced_separated",
    "No consta": "not_stated",
}
