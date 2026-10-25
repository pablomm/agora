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
    assert client.get("/observations", params={"variable": "population_foreign_share", "level": "census_section"}).status_code == 404
    assert client.get("/observations", params={"variable": "population", "level": "census_section", "facet": "official"}).status_code == 404
    assert client.get("/rank", params={"variable": "population", "level": "province", "within": MADRID}).status_code == 400
