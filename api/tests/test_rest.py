MADRID = "es:ine:mun:28079"


def test_catalog_lists_variables_with_coverage(client):
    catalog = client.get("/catalog").json()
    variables = {variable["id"]: variable for variable in catalog["variables"]}
    assert "population" in variables
    facets = {facet["id"]: facet for facet in variables["population"]["facets"]}
    assert facets["official"]["coverage"]["municipality"][0] == 1996
    assert "census_section" in facets["census"]["coverage"]
    assert [level["id"] for level in catalog["levels"]][0] == "census_section"


def test_catalog_datasets_have_tags_and_units(client):
    catalog = client.get("/catalog").json()
    levels = {level["id"]: level for level in catalog["levels"]}
    assert levels["municipality"]["units"] > 8000
    datasets = {dataset["id"]: dataset for dataset in catalog["datasets"]}
    assert "imputed" in datasets["registered_unemployment"]["tags"]
    assert "derived" in datasets["population_mean_age"]["tags"]
    assert "single_edition" in datasets["dwellings_2021"]["tags"]
    # Municipalities of 500 residents or more: about half of them.
    assert datasets["population_education_detail"]["units"]["municipality"] < 0.6 * levels["municipality"]["units"]


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


def test_change_against_the_year_before(client):
    rate = client.get("/observations", params={"variable": "unemployment_rate", "level": "province", "period": 2024, "change": True}).json()
    assert rate["unit"] == "puntos" and rate["change"] == {"from": 2023, "as": "difference"} and rate["label"] == "Tasa de paro · variación interanual"
    people = client.get("/observations", params={"variable": "registered_unemployment", "level": "country", "period": 202412, "change": True}).json()
    assert people["unit"] == "%" and people["change"]["from"] == 202312 and -20 < people["values"]["es:country:es"] < 20
    assert client.get("/observations", params={"variable": "unemployment_rate", "level": "province", "period": 2021, "change": True}).status_code == 404


def test_classifications(client):
    listing = {entry["id"]: entry for entry in client.get("/classifications").json()}
    assert {"cnae2025", "cnae2009", "cno11", "cned2014_a", "cned2014_f", "cpa22"} <= set(listing) and listing["cno11"]["items"] == 761
    doctors = client.get("/classifications/cno11", params={"q": "medicos", "level": 5}).json()
    assert any(item["code"] == "2111" for item in doctors["items"])
    item = client.get("/classifications/cno11/2111").json()
    assert [ancestor["code"] for ancestor in item["ancestors"]] == ["2", "B", "21", "211"]
    assert any(pair["classification"] == "ciuo08" for pair in item["correspondences"]["to"])
    # Dots are optional; both CNAE versions answer for each other.
    cnae = client.get("/classifications/cnae2009/01.11").json()
    assert cnae["code"] == "0111" and any(pair["classification"] == "cnae2025" and pair["label"] for pair in cnae["correspondences"]["to"])
    education = client.get("/classifications/cned2014_a/CM").json()
    assert {"classification": "education_level", "code": "doctorate", "note": None, "label": None} in education["correspondences"]["from"]


def test_dimensions_linked_to_classifications(client):
    dimensions = {dimension["id"]: dimension for dimension in client.get("/catalog").json()["dimensions"]}
    assert dimensions["cno11"]["classification"] == "cno11" and dimensions["sector"]["groups_of"] == "cnae2009"
    # The CNO-11 dimension takes its labels from the classification.
    assert {"code": "2", "label": "Técnicos y profesionales científicos e intelectuales", "parent": None} in dimensions["cno11"]["values"]
    held = client.get("/classifications/cno11/2111").json()["dimensions"]
    assert {"dimension": "cno11", "value": "2", "label": "Técnicos y profesionales científicos e intelectuales"} in held
    assert any(entry["dimension"] == "occupation_group" and entry["value"] == "high_skilled" for entry in held)
    assert any(entry["dimension"] == "sector" and entry["value"] == "industry" for entry in client.get("/classifications/cnae2009/1011").json()["dimensions"])
    employed = client.get("/observations", params={"variable": "employed_by_cnae2009_share", "level": "municipality", "period": 2023, "option": "cnae2009:J"}).json()
    assert employed["label"] == "Proporción de ocupados por sección de actividad (CNAE-2009) · Información y comunicaciones" and 0 < employed["values"][MADRID] < 30


def test_professional_status_and_activity_groups(client):
    own = client.get("/observations", params={"variable": "employed_by_status_share", "level": "census_section", "period": 2023}).json()
    assert own["label"] == "Proporción de ocupados por situación profesional · Cuenta propia" and own["stats"]["count"] > 36_000
    spain = client.get("/entities/es:country:es/value", params={"variable": "employed_by_status_share", "period": 2023}).json()["value"]
    assert 10 < spain < 25
    public = client.get(f"/entities/{MADRID}/value", params={"variable": "employed_by_cnae2009_share", "period": 2023, "option": "cnae2009:public_services"}).json()
    parts = [client.get(f"/entities/{MADRID}/value", params={"variable": "employed_by_cnae2009_share", "period": 2023, "option": f"cnae2009:{code}"}).json()["value"] for code in "OPQ"]
    assert abs(public["value"] - sum(parts)) < 1e-9


def test_income(client):
    income = client.get("/observations", params={"variable": "income", "level": "census_section", "period": 2023}).json()
    assert income["label"] == "Renta · Neta media por persona" and income["unit"] == "€" and income["stats"]["count"] > 36_000
    madrid = client.get(f"/entities/{MADRID}/value", params={"variable": "income", "period": 2023}).json()["value"]
    assert madrid == 19_632
    poverty = client.get("/observations", params={"variable": "income_thresholds", "level": "census_section", "period": 2023, "option": ["sex:female", "income_group:under_18"]}).json()
    assert all(0 <= value <= 100 for value in poverty["values"].values()) and poverty["stats"]["count"] > 36_000
    change = client.get("/observations", params={"variable": "income", "level": "province", "period": 2024, "change": True}).json()
    assert change["unit"] == "%" and all(-5 < value < 20 for value in change["values"].values())


def test_marital_status(client):
    married = client.get("/observations", params={"variable": "population_marital_status_share", "level": "municipality", "period": 2024}).json()
    assert married["label"] == "Proporción de población por estado civil · Casados/as" and married["stats"]["count"] > 8_100
    madrid = client.get(f"/entities/{MADRID}/value", params={"variable": "population_marital_status_share", "period": 2024, "option": "marital_status:married"}).json()["value"]
    assert 35 < madrid < 45
    young = client.get("/observations", params={"variable": "population_marital_status_age_share", "level": "municipality", "period": 2024, "option": ["marital_status:single", "age:Y16T34"]}).json()
    assert young["stats"]["count"] > 4_000 and all(0 <= value <= 100 for value in young["values"].values())


def test_income_distribution(client):
    # A dataset without a layer: the Dagum's parameters, for a unit's detail.
    body = client.get(f"/entities/{MADRID}/breakdown", params={"dataset": "income_distribution", "period": 2023}).json()
    parameters = {row["distribution_parameter"]: row["value"] for row in body["rows"]}
    assert set(parameters) == {"a", "b", "p"} and parameters["a"] > 2
    a, b, p = parameters["a"], parameters["b"], parameters["p"]
    median = b * (2 ** (1 / p) - 1) ** (-1 / a)
    assert abs(median / 22_750 - 1) < 0.05  # INE's median per consumption unit in Madrid, 2023
    catalog = client.get("/catalog").json()
    assert any(dataset["id"] == "income_distribution" for dataset in catalog["datasets"])
    assert not any("income_distribution" in (facet["dataset"] for facet in variable["facets"]) for variable in catalog["variables"])


def test_census_2021(client):
    # A one-off census: one period, down to sections, in its own topic after the yearly ones.
    catalog = client.get("/catalog").json()
    # Among the topics with variables (geometries' and classifications' come after them).
    used = {variable["topic"] for variable in catalog["variables"]}
    topics = [topic["id"] for topic in catalog["topics"] if topic["id"] in used]
    assert topics[-1] == "census_2021"
    empty = client.get("/observations", params={"variable": "dwellings_2021_share", "level": "census_section", "option": "dwelling:non_principal"}).json()
    assert empty["period"] == 2021 and empty["stats"]["count"] > 35_000
    spain = client.get("/entities/es:country:es/value", params={"variable": "dwellings_2021", "option": "dwelling:total"}).json()["value"]
    assert spain == 26_623_708
    households = client.get(f"/entities/{MADRID}/value", params={"variable": "households_2021", "option": "household_size:total"}).json()["value"]
    assert 1_200_000 < households < 1_400_000
    use = client.get("/observations", params={"variable": "dwelling_use_2021_share", "level": "municipality", "option": "dwelling_use:empty"}).json()
    assert use["stats"]["count"] > 3_000 and all(0 <= value <= 100 for value in use["values"].values())
    area = client.get("/entities/es:country:es/value", params={"variable": "floor_area_2021"}).json()
    assert area["unit"] == "m²" and 80 < area["value"] < 95
    size = client.get("/observations", params={"variable": "household_size_2021", "level": "census_section"}).json()
    assert size["stats"]["count"] > 36_000
    median = client.get("/observations", params={"variable": "electricity_consumption_2021", "level": "census_district"}).json()
    assert median["unit"] == "kWh" and median["stats"]["count"] > 5_000


def test_census_2021_detail(client):
    # INE's custom tables, down to sections: hidden sections imputed, every table adding up to the official households.
    for dataset, dimension in [("households_by_structure_2021", "household_structure"), ("households_by_members_2021", "members"), ("households_by_nuclei_2021", "household_nuclei")]:
        rows = client.get("/entities/es:country:es/breakdown", params={"dataset": dataset, "period": 2021}).json()["rows"]
        assert {row["value"] for row in rows if row[dimension] == "total"} == {18_539_223}
    alone = client.get("/observations", params={"variable": "households_by_structure_2021_share", "level": "census_section", "option": "household_structure:living_alone"}).json()
    assert alone["stats"]["count"] > 36_000 and all(0 <= value <= 100 for value in alone["values"].values())
    nuclei = client.get("/entities/es:country:es/breakdown", params={"dataset": "nuclei_by_children_2021", "period": 2021}).json()["rows"]
    assert 12_500_000 < next(row["value"] for row in nuclei if row["children"] == "total") < 14_000_000
    same_sex = client.get(f"/entities/{MADRID}/value", params={"variable": "couples_by_sexes_2021_share", "option": "couple_sexes:same_sex"}).json()["value"]
    assert 0.5 < same_sex < 3
    children = client.get("/entities/es:country:es/value", params={"variable": "nuclei_mean_children_2021", "option": "nucleus_type:total"}).json()["value"]
    assert 1 < children < 1.5
    age = client.get(f"/entities/{MADRID}/value", params={"variable": "dwellings_mean_age_2021", "option": "dwelling:total"}).json()
    assert 40 < age["value"] < 55


def test_dataset_described(client):
    body = client.get("/datasets/population_sex_age").json()
    assert [dimension["id"] for dimension in body["dimensions"]] == ["sex", "age"]
    files = {file["name"]: file for file in body["files"]}
    assert files["census_section"]["rows"] > 10_000_000 and files["census_section"]["periods"][-1] == 2025 and "value" in body["columns"]
    assert any(dataset["id"] == "population_sex_age" for dataset in client.get("/datasets", params={"q": "poblacion sexo edad"}).json())


def test_catalog_has_geometries_and_reference_tables(client):
    datasets = {dataset["id"]: dataset for dataset in client.get("/catalog").json()["datasets"]}
    assert datasets["ign_au_municipalities"]["kind"] == "geometry" and datasets["cnae2025"]["kind"] == "reference"
    # Catastro's urban parcels: a file per province or Catastro office, without the foral ones'.
    parcels = {file["name"]: file for file in datasets["catastro_urban_parcels"]["files"]}
    assert len(parcels) == 52 and "31" not in parcels and parcels["53"]["label"] == "Cádiz (gerencia 53)"
    assert [file["name"] for file in datasets["navarra_urban_parcels"]["files"]] == ["31"]
    # Listed but not served: no license known.
    assert not datasets["postal_code_areas_2024"]["downloadable"] and "no_license" in datasets["postal_code_areas_2024"]["tags"]
    geometries = client.get("/datasets", params={"kind": "geometry"}).json()
    assert {dataset["kind"] for dataset in geometries} == {"geometry"}


def test_geometry_and_reference_downloads(client):
    madrid = client.get("/datasets/ign_au_municipalities/municipalities.csv", params={"filter": "province_code:28"}).text.splitlines()
    # Geometries as WKT in CSV, and with their GeoParquet metadata in a Parquet slice.
    assert len(madrid) == 1 + 179 and ',"MULTIPOLYGON (((' in madrid[1]
    sliced = client.get("/datasets/ign_au_provinces/provinces.parquet", params={"filter": "ccaa_code:13"}).content
    assert sliced[:4] == b"PAR1" and b'"primary_column"' in sliced
    sections = client.get("/datasets/cnae2025/items.csv", params={"filter": "level:1"}).text.splitlines()
    assert sections[0].startswith("classification,code,label") and len(sections) == 1 + 22
    units = client.get("/datasets/territorial_units/municipality.csv", params={"filter": "province_id:es:ine:prov:28"}).text.splitlines()
    assert len(units) == 1 + 179 and any(",Getafe," in line for line in units)
    assert client.get("/datasets/postal_code_areas_2024/postal_codes.parquet").status_code == 403
    assert client.get("/datasets/ign_au_provinces/provinces.csv", params={"period": 2025}).status_code == 400


def test_dataset_downloads(client, tmp_path):
    whole = client.get("/datasets/population_sex_age/province.parquet")
    assert whole.headers["content-type"] == "application/vnd.apache.parquet" and whole.content[:4] == b"PAR1"
    # A slice as CSV with labels: Madrid's 179 municipalities, women of every age group, in 2025.
    sliced = client.get(
        "/datasets/population_sex_age/municipality.csv",
        params={"period": 2025, "within": "es:ine:prov:28", "filter": ["sex:female", "age:total"], "labels": "true"},
    )
    lines = sliced.text.splitlines()
    assert lines[0].split(",")[-2:] == ["sex_label", "age_label"] and len(lines) == 1 + 179
    assert all(line.endswith(",Mujeres,Todas las edades") for line in lines[1:])
    # The same slice twice is the same file, so readers fetching it in ranges see one version.
    again = client.head("/datasets/population_sex_age/municipality.parquet", params={"period": 2025, "filter": "sex:female"})
    assert again.headers["etag"] == client.head("/datasets/population_sex_age/municipality.parquet", params={"period": 2025, "filter": "sex:female"}).headers["etag"]
    assert client.get("/datasets/population_sex_age/municipality.csv", params={"filter": "colour:red"}).status_code == 400
    assert client.get("/datasets/population_sex_age/planet.csv").status_code == 404


def test_dataset_metadata_for_its_page(client):
    datasets = {dataset["id"]: dataset for dataset in client.get("/catalog").json()["datasets"]}
    parcels = datasets["navarra_urban_parcels"]
    # Drawn by the map's parcels layer; its focus is the municipality with most parcels (Pamplona).
    assert parcels["tiles"] == "cadastral_parcels" and parcels["extent"][0] < parcels["focus"][0] < parcels["focus"][2] < parcels["extent"][2]
    assert datasets["population_sex_age"]["measure"] == {"id": "population", "unit": "personas", "aggregation": "sum"}
    body = client.get("/datasets/population_sex_age").json()
    assert 65034 in body["run"]["tables"] and all(check["mismatches"] == 0 for check in body["run"]["checks"])
    files = {file["name"]: file for file in body["files"]}
    assert files["municipality"]["units_by_period"]["2025"] > 8000
    assert client.get("/datasets/ine_census_sections").json()["validity"]["as_of"] == "2026-01-01"


def test_licenses_metadata_and_checksums(client):
    licenses = {entry["id"]: entry for entry in client.get("/licenses").json()}
    assert licenses["CC-BY-4.0"]["open"] and not licenses["DGC-INSPIRE-2016"]["open"]
    assert set(licenses["DGC-INSPIRE-2016"]["datasets"]) == {"catastro_cadastral_zones", "catastro_urban_parcels"}
    assert client.get("/licenses/CC-BY-4.0").json()["conditions"]["es"][0].startswith("Citar")
    body = client.get("/datasets/ign_au_provinces").json()
    assert body["description"]["es"].startswith("Límites") and "IGN" in body["keywords"]["es"] and body["topics"] == ["territory"]
    assert body["fields"]["name"]["es"].startswith("Nombre oficial")
    assert len(body["files"][0]["sha256"]) == 64
    head = client.get("/datasets/ign_au_provinces/provinces/head", params={"limit": 3}).json()
    assert len(head["rows"]) == 3 and head["rows"][0]["geometry"].startswith(("POLYGON", "MULTIPOLYGON"))
    assert client.get("/datasets/postal_code_areas_2024/postal_codes/head").status_code == 403


def test_cadastre_listed_but_not_served(client):
    # The Catastro's license doesn't allow redistributing its original information: its notes say where to get it.
    for dataset_id, file in (("catastro_urban_parcels", "28"), ("catastro_cadastral_zones", "cadastral_zones_2023-04"), ("cadastral_polygons_2023", "rural_polygons_2023")):
        body = client.get(f"/datasets/{dataset_id}").json()
        assert not body["downloadable"] and "not_downloadable" in body["tags"]
        assert "catastro.hacienda.gob.es/webinspire" in body["processing"]["es"]
        assert client.get(f"/datasets/{dataset_id}/{file}.parquet").status_code == 403
    assert client.get("/datasets/navarra_urban_parcels/31.parquet").status_code == 200
