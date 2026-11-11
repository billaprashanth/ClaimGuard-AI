"""A tiny, dependency-free StateGraph engine with the same API surface we use from LangGraph.

Used automatically when `langgraph` is not installed (or when CLAIMGUARD_ENGINE=builtin).
It implements LangGraph's semantics that this project relies on:
  * super-step execution (nodes triggered in the same step run "in parallel"
    on the same input snapshot),
  * reducers declared with `Annotated[type, reducer]` on the state schema,
  * fan-out edges, fan-in (join) edges `add_edge([a, b], c)` that wait for all sources,
  * conditional edges with a path map.
"""
from __future__ import annotations

from typing import Any, Callable, get_args, get_origin, get_type_hints, Annotated

START = "__start__"
END = "__end__"


class _Compiled:
    def __init__(self, g: "MiniStateGraph"):
        self.g = g

    def _merge(self, state: dict, update: dict) -> dict:
        for k, v in (update or {}).items():
            red = self.g.reducers.get(k)
            state[k] = red(state.get(k), v) if (red and k in state) else v
        return state

    def invoke(self, state: dict, config: dict | None = None) -> dict:
        state = dict(state)
        for k, red in self.g.reducers.items():  # initialise accumulators
            state.setdefault(k, red(None, None) if red.__name__ == "merge_dicts" else [])
        active = list(self._next(START, state))
        join_done: dict[int, set] = {}
        steps = 0
        while active:
            steps += 1
            if steps > 100:
                raise RuntimeError("Graph recursion limit reached")
            snapshot = dict(state)
            updates = []
            for node in active:
                updates.append((node, self.g.nodes[node](dict(snapshot)) or {}))
            for _, upd in updates:
                self._merge(state, upd)
            nxt: list[str] = []
            for node, _ in updates:
                for t in self._next(node, state):
                    if t not in nxt:
                        nxt.append(t)
                for i, (sources, target) in enumerate(self.g.joins):
                    if node in sources:
                        done = join_done.setdefault(i, set())
                        done.add(node)
                        if done >= set(sources):
                            join_done[i] = set()
                            if target not in nxt:
                                nxt.append(target)
            active = [n for n in nxt if n != END]
        return state

    def _next(self, node: str, state: dict):
        for src, dst in self.g.edges:
            if src == node:
                yield dst
        if node in self.g.conditional:
            fn, path_map = self.g.conditional[node]
            res = fn(state)
            for r in (res if isinstance(res, list) else [res]):
                yield path_map.get(r, r) if path_map else r


class MiniStateGraph:
    def __init__(self, schema: type):
        self.nodes: dict[str, Callable] = {}
        self.edges: list[tuple[str, str]] = []
        self.joins: list[tuple[tuple[str, ...], str]] = []
        self.conditional: dict[str, tuple[Callable, dict | None]] = {}
        self.reducers: dict[str, Callable] = {}
        for key, hint in get_type_hints(schema, include_extras=True).items():
            if get_origin(hint) is Annotated:
                meta = get_args(hint)[1:]
                if meta and callable(meta[0]):
                    self.reducers[key] = meta[0]

    def add_node(self, name: str, fn: Callable[[dict], dict]) -> None:
        self.nodes[name] = fn

    def add_edge(self, src: Any, dst: str) -> None:
        if isinstance(src, (list, tuple)):
            self.joins.append((tuple(src), dst))
        else:
            self.edges.append((src, dst))

    def add_conditional_edges(self, src: str, fn: Callable, path_map: dict | None = None) -> None:
        self.conditional[src] = (fn, path_map)

    def compile(self) -> _Compiled:
        return _Compiled(self)
