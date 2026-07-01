# Subsystem B — Graph

Build a `networkx.DiGraph` from a lifted binary and query the call graph. Nodes are functions, edges are calls.

```
  BinaryArtifact (from A)  ──>  CallGraph  ──> queries
                     │                    │
                     │                    ├── callers_of("malloc")
                     │                    ├── callees_of("main", transitive=True)
                     │                    ├── orphans()
                     │                    ├── cycles()
                     │                    └── shortest_path("main", "printf")
                     │
                     ├── to_graphml("graph.graphml")
                     └── to_pickle("graph.pkl")
```

## Public API

```python
from bainary.graph import CallGraph

# Construction
cg = CallGraph.from_artifact(artifact)
cg = CallGraph.from_json("target.json")

# Basic properties
cg.node_count           # 42
cg.edge_count           # 136
cg.functions            # {"0x401000": FunctionNode(...), ...}

# Queries (all return set[str] of function NAMES, not addresses)
cg.callers_of("malloc")                         # {"foo", "bar"}
cg.callers_of("malloc", transitive=True)        # {"foo", "bar", "main", "init"}

cg.callees_of("main")                           # {"a", "printf"}
cg.callees_of("main", transitive=True)          # {"a", "b", "c", "printf"}

cg.orphans()                                    # functions nobody calls
cg.entry_points()                               # functions with no callers (same as orphans)

cg.cycles()                                     # [{"a", "b"}] — SCCs with > 1 node
cg.shortest_path("main", "c")                   # ["main", "a", "b", "c"]

# Serialization
cg.to_graphml("out.graphml")                    # GraphML XML (lossy: no pseudocode)
cg.to_pickle("out.pkl")                         # Full round-trip (includes FunctionNode)

# Raw NetworkX access (for advanced queries)
cg.graph                                        # nx.DiGraph
nx.betweenness_centrality(cg.graph)
nx.all_simple_paths(cg.graph, "main", "malloc")
```

## FunctionNode

```python
from bainary.graph import FunctionNode

node = cg.functions["0x401000"]
node.address        # "0x401000"
node.name           # "main"
node.signature      # "int main(void)"
node.is_external    # True if thunk/import
node.is_thunk       # True if PLT wrapper
node.pseudocode     # "int main(void) { ... }" or None
node.size_bytes     # bytes of machine code
```

## Graph construction

```python
for fn in artifact.functions:
    # Node added per function
    g.add_node(fn.address, node=FunctionNode(...))

for fn in artifact.functions:
    for callee in fn.callees:
        if callee.address in g:
            g.add_edge(fn.address, callee.address)
```

External imports (not in `artifact.functions`) are silently dropped — the graph is internal-only.

## Error handling

```python
from bainary.graph.errors import GraphError
from bainary.lift.errors import BainaryError

assert issubclass(GraphError, BainaryError)

cg.callers_of("nonexistent")   # GraphError: function 'nonexistent' not in graph
```

## Source files

| File | Responsibility |
|---|---|
| `callgraph.py` | `CallGraph` class + `FunctionNode` dataclass |
| `errors.py` | `GraphError` exception |
