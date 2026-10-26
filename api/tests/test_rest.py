MADRID = "es:ine:mun:28079"


def test_catalog_lists_variables_with_coverage(client):
    catalog = client.get("/catalog").json()
    variables = {variable["id"]: variable for variable in catalog["variables"]}
    assert "population" in variables
    facets = {facet["id"]: facet for facet in variables["population"]["facets"]}
    assert facets["official"]["coverage"]["municipality"][0] == 1996
    assert "census_section" in facets["census"]["coverage"]
    assert [level["id"] for level in catalog["levels"]][0] == "census_section"


def test_observations_for_a_choropleth(client):
    body = client.get("/observations", params={"variable": "population", "level": "municipality", "period": 2025}).json()
    assert body["facet"]["id"] == "official"
    assert body["stats"]["count"] == 8132
    assert body["values"][MADRID] > 3_000_000
    assert len(body["stats"]["quantiles"]) == 4


def test_observations_within_a_province(client):
    body = client.get("/observations", params={"variable": "population", "level": "municipality", "within": "es:ine:prov:28"}).json()
    assert body["stats"]["count"] == 179
    assert all(entity_id.startswith("es:ine:mun:28") for entity_id in body["values"])


def test_ratio_variables(client):
    body = client.get("/observations", params={"variable": "population_age_share", "level": "province", "period": 2025}).json()
    assert all(0 < value < 100 for value in body["values"].values())


def test_options(client):
    women = client.get("/observations", params={"variable": "population", "level": "province", "period": 2025, "option": "sex:female"}).json()
    men = client.get("/observations", params={"variable": "population", "level": "province", "period": 2025, "option": "sex:male"}).json()
    total = client.get("/observations", params={"variable": "population", "level": "province", "period": 2025}).json()
    assert women["label"] == "Población · Mujeres" and total["label"] == "Población"
    assert all(abs(women["values"][key] + men["values"][key] - total["values"][key]) < 1e-6 for key in total["values"])
    under_15 = client.get(
        "/observations", params={"variable": "population_age_share", "level": "municipality", "period": 2025, "option": "age:Y0T4..Y10T14"}
    ).json()
    assert under_15["options"]["age"] == {"codes": ["Y0T4", "Y5T9", "Y10T14"], "label": "De 0 a 14 años"}
    everyone = client.get("/entities/es:ine:mun:28079/value", params={"variable": "population_age_share", "option": "age:Y0T4..Y_GE100"}).json()
    assert abs(everyone["value"] - 100) < 1e-6
    default = client.get("/entities/es:ine:mun:28079/value", params={"variable": "population_age_share"}).json()
    assert default["options"]["age"]["label"] == "65 años o más"
    assert client.get("/observations", params={"variable": "population", "level": "province", "option": "age:Y0T4"}).status_code == 400
    assert client.get("/observations", params={"variable": "population_age_share", "level": "province", "option": "age:Y10T14..Y0T4"}).status_code == 400


def test_series_from_each_source(client):
    body = client.get(f"/entities/{MADRID}/series", params={"variable": "population"}).json()
    facets = {facet["id"]: facet["values"] for facet in body["facets"]}
    assert len(facets["official"]) >= 29 and len(facets["census"]) == 5


def test_breakdown(client):
    body = client.get(f"/entities/{MADRID}/breakdown", params={"dataset": "population_sex_age", "period": 2025}).json()
    assert len(body["rows"]) == 3 * 22
    assert {dimension["id"] for dimension in body["dimensions"]} == {"sex", "age"}


def test_search_ignores_accents(client):
    results = client.get("/search", params={"q": "alacant"}).json()
    assert results[0]["name"] == "Alacant/Alicante"
    assert client.get("/search", params={"q": "getafe"}).json()[0]["id"] == "es:ine:mun:28065"


def test_entity_with_ancestors(client):
    body = client.get(f"/entities/{MADRID}").json()
    assert [ancestor["id"] for ancestor in body["ancestors"]] == ["es:ine:prov:28", "es:ine:ccaa:13", "es:country:es"]


def test_errors(client):
    assert client.get("/variables/nope").status_code == 404
    assert client.get("/observations", params={"variable": "population", "level": "municipality", "period": 1900}).status_code == 404
    assert client.get("/observations", params={"variable": "population_nationality_detail_share", "level": "census_section"}).status_code == 404
    assert client.get("/observations", params={"variable": "population", "level": "census_section", "facet": "official"}).status_code == 404
    assert client.get("/rank", params={"variable": "population", "level": "province", "within": MADRID}).status_code == 400


def test_monthly_registers(client):
    body = client.get("/observations", params={"variable": "registered_unemployment", "level": "country", "period": 201912}).json()
    # SEPE's published national figure for December 2019 (before values under 5 were hidden).
    assert body["values"]["es:country:es"] == 3_163_605
    assert body["facet"]["frequency"] == "monthly"
    women = client.get(
        "/observations", params={"variable": "registered_unemployment", "level": "province", "period": 202412, "option": ["sex:female", "age_band:Y_LT25"]}
    ).json()
    assert women["label"] == "Paro registrado · Mujeres · Menores de 25 años"


def test_rate_over_another_dataset(client):
    body = client.get(f"/entities/{MADRID}/series", params={"variable": "registered_unemployment_rate"}).json()
    values = body["facets"][0]["values"]
    # From the census's first year; months after its last year use its latest population.
    assert values[0]["period"] == 202101 and all(0 < row["value"] < 20 for row in values)


def test_census_activity_by_section(client):
    body = client.get("/observations", params={"variable": "unemployment_rate", "level": "census_section", "period": 2024}).json()
    assert body["stats"]["count"] > 36_000
    spain = client.get("/entities/es:country:es/value", params={"variable": "unemployment_rate", "period": 2021}).json()
    assert 10 < spain["value"] < 20


def test_nationality_lists(client):
    # The foreign total from either list matches INE's Spanish/foreign table (68535) for 2025.
    for variable, option in (("population_nationality", "nationality_main:foreign"), ("population_nationality_detail", "nationality_detail:foreign")):
        body = client.get("/observations", params={"variable": variable, "level": "country", "period": 2025, "option": option}).json()
        assert body["values"]["es:country:es"] == 6_911_971
    share = client.get(
        "/observations", params={"variable": "population_nationality_share", "level": "census_section", "period": 2025, "option": ["nationality_main:MAR", "sex:female"]}
    ).json()
    assert share["label"] == "Proporción de población por nacionalidad · Marruecos · Mujeres" and share["stats"]["count"] > 36_000
    detail = client.get("/variables/population_nationality_detail").json()
    values = {value["code"]: value for value in detail["options"][0]["values"]}
    assert values["FRA"]["parent"] == "eu" and values["eu"]["parent"] == "europe" and values["europe"]["parent"] == "foreign"


def test_age_indicators_and_birthplace(client):
    spain = {
        variable: client.get("/entities/es:country:es/value", params={"variable": variable, "period": 2025}).json()["value"]
        for variable in ("mean_age", "ageing_index", "dependency_ratio", "overageing_index")
    }
    assert 43 < spain["mean_age"] < 45 and 140 < spain["ageing_index"] < 180 and 45 < spain["dependency_ratio"] < 60 and 10 < spain["overageing_index"] < 25
    born = client.get("/observations", params={"variable": "population_birthplace_share", "level": "census_section", "period": 2025, "option": "birthplace:abroad"}).json()
    assert born["stats"]["count"] > 36_000 and born["label"] == "Proporción de población por lugar de nacimiento · En el extranjero"


def test_foreign_by_section_ignores_age(client):
    # By census section the foreign population has no age: the choice isn't applied, nor named.
    params = {"variable": "population_foreign_share", "period": 2025, "option": ["sex:female", "age:Y20T24..Y30T34"]}
    section = client.get("/observations", params={**params, "level": "census_section"}).json()
    assert section["facet"]["id"] == "census_sections" and section["label"] == "Proporción de población extranjera · Mujeres"
    municipality = client.get("/observations", params={**params, "level": "municipality"}).json()
    assert municipality["label"] == "Proporción de población extranjera · Mujeres · De 20 a 34 años"


def test_mobility(client):
    recent = client.get("/observations", params={"variable": "population_arrival_spain_share", "level": "census_section", "period": 2025}).json()
    assert recent["label"] == "Proporción de población por año de llegada a España · Después de 2020" and recent["stats"]["count"] > 36_000
    # Municipal only: the 151 cities, with the choices named.
    cities = client.get(
        "/observations", params={"variable": "population_residence_year_ago_share", "level": "municipality", "period": 2025, "option": ["nationality:foreign", "age:Y16T64"]}
    ).json()
    assert len(cities["values"]) == 151 and 0 < cities["values"][MADRID] < 100
    assert cities["label"] == "Proporción de población por residencia hace un año · Fuera del municipio · De 16 a 64 años · Extranjera"
    assert client.get("/observations", params={"variable": "population_previous_residence", "level": "province"}).status_code == 404


def test_education(client):
    tertiary = client.get("/observations", params={"variable": "population_education_share", "level": "census_section", "period": 2024, "option": "sex:female"}).json()
    assert tertiary["label"] == "Proporción de población por nivel de estudios · Educación superior · Mujeres" and tertiary["stats"]["count"] > 36_000
    madrid = {
        variable: client.get(f"/entities/{MADRID}/value", params={"variable": variable, "period": 2024, "option": option}).json()["value"]
        for variable, option in (("population_education_detail_share", "education_level:university"), ("population_studying_share", "studying:studying"), ("education_gender_gap", "education_level:tertiary"))
    }
    assert 30 < madrid["population_education_detail_share"] < 50 and 5 < madrid["population_studying_share"] < 25 and -10 < madrid["education_gender_gap"] < 10
    ages = client.get("/observations", params={"variable": "population_education_age_share", "level": "municipality", "period": 2024}).json()
    assert ages["label"] == "Proporción de población por nivel de estudios y edad · Educación superior · De 25 a 59 años" and len(ages["values"]) == 4144
