"""Look up games, categories and variables by name, and list the top runs."""

from __future__ import annotations

from .api import SrcomClient, SrcomError
from .links import parse_video_url
from .models import Player, Run


def _match(items: list[dict], key: str, wanted: str, label: str) -> dict:
    w = wanted.strip().lower()
    for it in items:
        if it["id"].lower() == w:
            return it
    for it in items:
        if str(key(it) if callable(key) else it[key]).strip().lower() == w:
            return it
    names = ", ".join(repr(key(i) if callable(key) else i[key]) for i in items)
    raise SrcomError(f"no {label} matching {wanted!r}; options: {names}")


def resolve_game(client: SrcomClient, game: str) -> dict:
    """Accepts a game id, abbreviation (e.g. 'pikmin2') or exact name."""
    for params in ({"abbreviation": game}, {"name": game}):
        found = client.get_data("games", params)
        for g in found:
            if game.lower() in (g["id"].lower(), g["abbreviation"].lower(), g["names"]["international"].lower()):
                return g
    try:
        return client.get_data(f"games/{game}")
    except SrcomError:
        raise SrcomError(f"game not found: {game!r}") from None


def resolve_category(client: SrcomClient, game_id: str, category: str) -> dict:
    cats = client.get_data(f"games/{game_id}/categories")
    return _match(cats, "name", category, "category")


def resolve_variables(
    client: SrcomClient, game_id: str, category_id: str, variables: dict[str, str] | None
) -> dict[str, str]:
    """Map {variable name or id: value label or id} to {variable id: value id}."""
    if not variables:
        return {}
    all_vars = client.get_data(f"games/{game_id}/variables")
    usable = [v for v in all_vars if v.get("category") in (None, category_id)]
    out = {}
    for name, label in variables.items():
        var = _match(usable, "name", name, "variable")
        values = [{"id": k, "label": v["label"]} for k, v in var["values"]["values"].items()]
        out[var["id"]] = _match(values, "label", label, f"value of {var['name']!r}")["id"]
    return out


def top_runs(
    client: SrcomClient,
    game: str,
    category: str,
    variables: dict[str, str] | None = None,
    n: int = 5,
) -> list[Run]:
    """The top `n` places on a full-game leaderboard, best first.

    Runs without a video are included (with `videos == []`) so callers can
    report them; filter on `run.videos` to skip them.
    """
    g = resolve_game(client, game)
    cat = resolve_category(client, g["id"], category)
    var_ids = resolve_variables(client, g["id"], cat["id"], variables)
    params = {"top": n, "embed": "players,platforms,regions"}
    params.update({f"var-{k}": v for k, v in var_ids.items()})
    board = client.get_data(f"leaderboards/{g['id']}/category/{cat['id']}", params)

    users = {p["id"]: p["names"]["international"] for p in board["players"]["data"] if p.get("rel") == "user"}
    platforms = {p["id"]: p["name"] for p in board["platforms"]["data"]}
    regions = {r["id"]: r["name"] for r in board["regions"]["data"]}

    runs = [_run_from_api(entry["run"], entry["place"], users, platforms, regions) for entry in board["runs"]]
    runs.sort(key=lambda run: run.place)
    return runs[:n]


def _run_from_api(r: dict, place: int, users: dict, platforms: dict, regions: dict, series: str | None = None) -> Run:
    players = [
        Player(p.get("id"), users.get(p.get("id"), p.get("id") or "?")) if p["rel"] == "user"
        else Player(None, p.get("name", "?"))
        for p in r["players"]
    ]
    links = ((r.get("videos") or {}).get("links")) or []
    system = r.get("system") or {}
    return Run(
        id=r["id"],
        place=place,
        players=players,
        time_seconds=float(r["times"]["primary_t"]),
        date=r.get("date"),
        weblink=r["weblink"],
        game_id=r["game"],
        category_id=r["category"],
        platform=platforms.get(system.get("platform"), system.get("platform")),
        region=regions.get(system.get("region"), system.get("region")),
        emulated=bool(system.get("emulated")),
        videos=[parse_video_url(l["uri"]) for l in links],
        values=r.get("values") or {},
        series=series,
    )


def all_runs(client: SrcomClient, game_id: str, category_id: str, var_ids: dict[str, str] | None = None) -> list[dict]:
    """Every verified run of a category (current and obsolete), oldest first, as raw API dicts
    with players, platform and region embedded; filtered to the given variable values."""
    params = {"game": game_id, "category": category_id, "status": "verified", "orderby": "date",
              "direction": "asc", "max": 200, "embed": "players,platform,region", "offset": 0}
    out = []
    while True:
        page = client.get("runs", params)
        out.extend(page["data"])
        if len(page["data"]) < params["max"]:
            break
        params = dict(params, offset=params["offset"] + params["max"])
    want = var_ids or {}
    return [r for r in out if all((r.get("values") or {}).get(k) == v for k, v in want.items())]


def wr_history(
    client: SrcomClient,
    game: str,
    category: str,
    variables: dict[str, str] | None = None,
) -> list[Run]:
    """Every run that was the world record when it was set, oldest first.

    `place` is the run's position in the history (1 = the first record) and
    `series` is "wr", so their slugs (`wr01_...`) never collide with leaderboard runs.
    """
    g = resolve_game(client, game)
    cat = resolve_category(client, g["id"], category)
    var_ids = resolve_variables(client, g["id"], cat["id"], variables)
    best = None
    out: list[Run] = []
    for r in all_runs(client, g["id"], cat["id"], var_ids):
        t = float(r["times"]["primary_t"])
        if best is not None and t >= best:
            continue
        best = t
        users = {p["id"]: p["names"]["international"] for p in r["players"]["data"] if p.get("rel") == "user"}
        r = dict(r, players=[{"rel": p.get("rel"), "id": p.get("id"), "name": p.get("name")}
                             for p in r["players"]["data"]])
        plat = r.get("platform", {}).get("data") or {}
        reg = r.get("region", {}).get("data") or {}
        platforms = {plat.get("id"): plat.get("name")} if plat else {}
        regions = {reg.get("id"): reg.get("name")} if reg else {}
        out.append(_run_from_api(r, len(out) + 1, users, platforms, regions, series="wr"))
    return out
