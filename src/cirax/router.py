"""The router: find the best chain of engines from one format to another.

Coverage comes from composition — direct edges where an engine does the job,
short chains through pivot formats where it doesn't (docx -> PDF -> PNG).
Routes are ranked by (hops, lossiness, engine priority).
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field

from .registry import Registry, Route, Engine, TREE_FMT

MAX_HOPS = 3


@dataclass
class Step:
    engine: Engine
    route: Route
    to_format: str  # the specific target format chosen from route.to_formats

    @property
    def lossless(self) -> bool:
        return self.route.lossless


@dataclass
class Plan:
    src: str
    dst: str
    steps: list[Step] = field(default_factory=list)
    cost: float = 0.0

    @property
    def lossless(self) -> bool:
        return all(s.lossless for s in self.steps)

    @property
    def engines(self) -> list[str]:
        return [s.engine.name for s in self.steps]


def _edge_cost(route: Route) -> float:
    return 1.0 + (0.0 if route.lossless else 0.5) + (100 - route.priority) / 100


def _adjacency(reg: Registry, fmt: str,
               engine_filter: str | None = None) -> list[tuple[str, Step, float]]:
    """All (target_format, step, cost) edges leaving `fmt` via installed engines."""
    edges = []
    for engine in reg.engines:
        if not engine.installed or not engine.executable:
            continue
        if engine_filter is not None and engine.name != engine_filter:
            continue
        for route in engine.routes:
            if route.ops:
                continue  # same-format ops are resolved only by find_plan
            if not route.matches_input(fmt):
                continue
            for target in route.to_formats:
                if target == fmt:
                    continue
                cost = _edge_cost(route)
                edges.append((target, Step(engine, route, target), cost))
    return edges


def find_plan(reg: Registry, src: str, dst: str,
              engine_filter: str | None = None) -> Plan | None:
    """Dijkstra over the format graph, max MAX_HOPS engine invocations.

    For src == dst, only same-format `ops` routes (strip metadata, line
    endings, transcode charset) qualify; otherwise there is nothing to do.
    `engine_filter` restricts routing to a single named engine (used by
    `--engine` when several ops engines share a format pair).
    """

    def allowed(engine: Engine) -> bool:
        return (engine.installed and engine.executable
                and (engine_filter is None or engine.name == engine_filter))

    if src == dst:
        candidates = []
        for engine in reg.engines:
            if not allowed(engine):
                continue
            for route in engine.routes:
                if route.ops and route.matches_input(src) and src in route.to_formats:
                    candidates.append((_edge_cost(route),
                                       Step(engine, route, src)))
        if not candidates:
            return None
        cost, step = min(candidates, key=lambda pair: pair[0])
        return Plan(src, dst, [step], cost)
    best: dict[str, tuple[float, int]] = {src: (0.0, 0)}
    heap: list[tuple[float, int, str, list[Step]]] = [(0.0, 0, src, [])]
    while heap:
        cost, hops, fmt, path = heapq.heappop(heap)
        if best.get(fmt, (float("inf"), 99)) < (cost, hops):
            continue
        if fmt == dst and path:
            return Plan(src, dst, path, cost)
        if hops >= MAX_HOPS:
            continue
        for target, step, step_cost in _adjacency(reg, fmt, engine_filter):
            nc, nh = cost + step_cost, hops + 1
            if best.get(target, (float("inf"), 99)) <= (nc, nh):
                continue
            best[target] = (nc, nh)
            heapq.heappush(heap, (nc, nh, target, path + [step]))
    return None


def reachable(reg: Registry, src: str) -> dict[str, Plan]:
    """Every format reachable from src, with the best plan to get there."""
    out: dict[str, Plan] = {}
    best: dict[str, tuple[float, int]] = {src: (0.0, 0)}
    heap: list[tuple[float, int, str, list[Step]]] = [(0.0, 0, src, [])]
    while heap:
        cost, hops, fmt, path = heapq.heappop(heap)
        if best.get(fmt, (float("inf"), 99)) < (cost, hops):
            continue
        if fmt != src and fmt not in out:
            out[fmt] = Plan(src, fmt, path, cost)
        if hops >= MAX_HOPS:
            continue
        for target, step, step_cost in _adjacency(reg, fmt):
            nc, nh = cost + step_cost, hops + 1
            if best.get(target, (float("inf"), 99)) <= (nc, nh):
                continue
            best[target] = (nc, nh)
            heapq.heappush(heap, (nc, nh, target, path + [step]))
    out.pop(TREE_FMT, None)  # internal staging pseudo-format
    return out
