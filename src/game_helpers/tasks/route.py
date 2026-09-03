"""Shortest-path planning over a human-defined scene graph."""

from __future__ import annotations

import heapq
from collections import defaultdict

from .models import RoutePlan, TravelEdge


class SceneRouter:
    """Dijkstra router; edge actions can represent flags, teleport items, etc."""

    def __init__(self, edges: list[TravelEdge] | tuple[TravelEdge, ...] = ()) -> None:
        self._edges = tuple(edges)

    def shortest_path(self, source_scene: str, target_scene: str) -> RoutePlan:
        if source_scene == target_scene:
            return RoutePlan(source_scene, target_scene, (source_scene,), (), 0.0)

        graph: dict[str, list[TravelEdge]] = defaultdict(list)
        for edge in self._edges:
            graph[edge.source_scene].append(edge)

        queue: list[tuple[float, str]] = [(0.0, source_scene)]
        distance = {source_scene: 0.0}
        previous: dict[str, tuple[str, TravelEdge]] = {}

        while queue:
            cost, scene = heapq.heappop(queue)
            if cost != distance.get(scene):
                continue
            if scene == target_scene:
                break
            for edge in graph.get(scene, ()):
                next_cost = cost + edge.cost
                if next_cost < distance.get(edge.target_scene, float("inf")):
                    distance[edge.target_scene] = next_cost
                    previous[edge.target_scene] = (scene, edge)
                    heapq.heappush(queue, (next_cost, edge.target_scene))

        if target_scene not in distance:
            raise ValueError(f"no route from {source_scene!r} to {target_scene!r}")

        scenes: list[str] = [target_scene]
        actions: list[str] = []
        current = target_scene
        while current != source_scene:
            parent, edge = previous[current]
            scenes.append(parent)
            actions.append(edge.action)
            current = parent
        scenes.reverse()
        actions.reverse()
        return RoutePlan(source_scene, target_scene, tuple(scenes), tuple(actions), distance[target_scene])
