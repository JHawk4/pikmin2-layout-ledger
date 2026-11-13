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

    runs = []
    for entry in board["runs"]:
        r = entry["run"]
        players = [
            Player(p.get("id"), users.get(p.get("id"), p.get("id") or "?")) if p["rel"] == "user"
            else Player(None, p.get("name", "?"))
            for p in r["players"]
        ]
        links = ((r.get("videos") or {}).get("links")) or []
        system = r.get("system") or {}
        runs.append(Run(
            id=r["id"],
            place=entry["place"],
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
        ))
    runs.sort(key=lambda run: run.place)
    return runs[:n]
