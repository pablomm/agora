from agora_api.mcp import server as tools


def test_search_then_value_with_source():
    getafe = tools.search_entities("Getafe")[0]
    result = tools.get_value(getafe["id"], "population_foreign_share", 2025)
    assert result["place"] == "Getafe" and result["unit"] == "%" and 0 < result["value"] < 100
    assert "INE" in result["attribution"]


def test_rank_within_and_compare():
    ranking = tools.rank("population", "municipality", within="es:ine:prov:28", top=3)
    assert ranking["items"][0]["name"] == "Madrid" and ranking["out_of"] == 179
    compared = tools.compare(["es:ine:mun:28079", "es:ine:mun:08019"], "population", 2025)
    assert [row["place"] for row in compared] == ["Madrid", "Barcelona"]


def test_breakdown_has_labels():
    result = tools.get_breakdown("es:ine:mun:28079", "population_sex_age", 2025)
    assert len(result["rows"]) == 3 * 22
    assert {row["sex"] for row in result["rows"]} == {"Total", "Hombres", "Mujeres"}
    assert any(row["age"] == "De 20 a 24 años" for row in result["rows"])


def test_options():
    result = tools.get_value("es:ine:mun:28079", "population_sex_share", 2025, options={"sex": "male"})
    assert result["variable"] == "Proporción de población por sexo · Hombres" and 40 < result["value"] < 50


def test_list_variables_is_compact():
    variables = {variable["id"]: variable for variable in tools.list_variables()}
    assert variables["population"]["sources"][0]["levels"]["municipality"] == "1996–2025"


def test_download_link_and_shape():
    result = tools.download_dataset("population_sex_age", "census_section", periods=[2025], within="es:ine:mun:28079", filters={"sex": "female"}, labels=True)
    assert result["url"].startswith("http://localhost:8000/datasets/population_sex_age/census_section.parquet?period=2025")
    # Madrid's sections, each with its 22 age groups.
    assert result["rows"] % 22 == 0 and result["rows"] > 2000 * 22
    assert {"sex_label", "age_label", "value"} <= set(result["columns"]) and "INE" in result["attribution"]


def test_unlimited_results():
    assert tools.rank("population", "municipality", top=None)["out_of"] == len(tools.rank("population", "municipality", top=None)["items"])
