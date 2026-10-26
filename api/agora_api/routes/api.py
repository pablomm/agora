"""REST endpoints for the web: compact JSON, straight from the services."""

from fastapi import APIRouter, Query

from agora_api.services import catalog, classifications, data, entities

router = APIRouter()

OPTION = Query(None, description='A variable\'s option, as dimension:code or, for ranges, dimension:first..last (e.g. sex:female, age:Y0T4..Y10T14); repeat for several')


def _options(option: list[str] | None) -> dict[str, str]:
    out = {}
    for entry in option or []:
        dimension, separator, code = entry.partition(":")
        if not separator:
            raise ValueError(f"Option {entry!r} isn't dimension:code")
        out[dimension] = code
    return out


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/catalog")
def get_catalog() -> dict:
    """Levels, topics, variables (with their facets' coverage), datasets and dimensions."""
    return catalog.summary()


@router.get("/classifications")
def get_classifications() -> list[dict]:
    """Statistical classifications (CNAE-2025, CNAE-2009, CNO-11, CNED-2014, CPA 2.2): ids, levels, sizes."""
    return classifications.listing()


@router.get("/classifications/{classification_id}")
def get_classification_items(
    classification_id: str,
    level: int | None = Query(None, description="Only this level (1 = the top)"),
    parent: str | None = Query(None, description="Only the items under this code"),
    q: str | None = Query(None, description="Only items whose code or label has every word (accents don't matter)"),
    limit: int = Query(500, le=10000),
) -> dict:
    return classifications.items(classification_id, level, parent, q, limit)


@router.get("/classifications/{classification_id}/{code}")
def get_classification_item(classification_id: str, code: str) -> dict:
    """One code: its label, ancestors, children and correspondences to and from other classifications."""
    return classifications.item(classification_id, code)


@router.get("/variables/{variable_id}")
def get_variable(variable_id: str) -> dict:
    return catalog.variable(variable_id)


@router.get("/observations")
def get_observations(
    variable: str,
    level: str,
    period: int | None = None,
    facet: str | None = None,
    within: str | None = Query(None, description="Only units inside this one (e.g. es:ine:prov:28)"),
    option: list[str] | None = OPTION,
    change: bool = Query(False, description="Each unit's change against the year before: % for counts, a difference (points for rates) for the rest"),
) -> dict:
    """A variable for every unit of a level in a year ({entity_id: value}), with quantiles for a legend."""
    return data.observations(variable, level, period, facet, within, _options(option), change)


@router.get("/rank")
def get_rank(
    variable: str,
    level: str,
    period: int | None = None,
    within: str | None = None,
    top: int = 10,
    ascending: bool = False,
    facet: str | None = None,
    option: list[str] | None = OPTION,
    change: bool = Query(False, description="Rank by change against the year before"),
) -> dict:
    return data.rank(variable, level, period, within, top, ascending, facet, _options(option), change)


@router.get("/search")
def get_search(q: str, level: list[str] | None = Query(None), limit: int = Query(10, le=50)) -> list[dict]:
    return entities.search(q, level, limit)


@router.get("/entities/{entity_id}")
def get_entity(entity_id: str) -> dict:
    return entities.describe(entity_id)


@router.get("/entities/{entity_id}/series")
def get_series(entity_id: str, variable: str, facet: str | None = None, option: list[str] | None = OPTION) -> dict:
    return data.series(entity_id, variable, facet, _options(option))


@router.get("/entities/{entity_id}/value")
def get_value(entity_id: str, variable: str, period: int | None = None, facet: str | None = None, option: list[str] | None = OPTION) -> dict:
    return data.value(entity_id, variable, period, facet, _options(option))


@router.get("/entities/{entity_id}/breakdown")
def get_breakdown(entity_id: str, dataset: str, period: int | None = None) -> dict:
    return data.breakdown(entity_id, dataset, period)
