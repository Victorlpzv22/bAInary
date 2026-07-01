# Examples

## End-to-end: lift → call graph → refine

```python
import os
from bainary.lift import lift
from bainary.graph import CallGraph
from bainary.refine import Refiner, create_client

# 1. Lift binary
artifact = lift("target.elf", backend="ghidra_headless")
print(f"Binary: {artifact.binary.format} {artifact.binary.arch}")
print(f"Functions: {len(artifact.functions)}")

# 2. Build call graph
cg = CallGraph.from_artifact(artifact)
print(f"Call graph: {cg.node_count} nodes, {cg.edge_count} edges")
print(f"Orphans: {cg.orphans()}")
print(f"Cycles: {cg.cycles()}")

# 3. Refine with LLM
client = create_client(
    provider="openai",
    api_key=os.environ["OPENCODE_APIKEY"],
    base_url="https://opencode.ai/zen/go/v1",
    model="kimi-k2.7-code",
)
refiner = Refiner(client=client)
refined = refiner.refine(artifact, cg)

# 4. Compare
for fn in artifact.functions[:3]:
    if fn.pseudocode:
        ref = next(f for f in refined.functions if f.name == fn.name)
        print(f"\n{fn.name}:")
        print("  ORIGINAL:", fn.pseudocode[:100], "...")
        print("  REFINED: ", ref.pseudocode[:100], "...")
```

## Pipeline without LLM (just A + B)

```python
from bainary.lift import lift
from bainary.graph import CallGraph

artifact = lift("target.elf", backend="lief_capstone")
cg = CallGraph.from_artifact(artifact)

# Find the entry point
print("Entry points:", cg.entry_points())

# Find dead code (functions nobody calls)
print("Orphans:", cg.orphans())

# Trace a call chain
print("path from start to printf:", cg.shortest_path("_start", "printf"))

# Export for analysis
cg.to_graphml("callgraph.graphml")
cg.to_pickle("callgraph.pkl")
```

## Using GraphML with external tools

```python
from bainary.lift import lift
from bainary.graph import CallGraph

artifact = lift("target.elf")
cg = CallGraph.from_artifact(artifact)
cg.to_graphml("callgraph.graphml")
```

Then open `callgraph.graphml` in:
- **Gephi** — visualize with Force Atlas 2 layout
- **yEd** — automatic layout + PDF export
- **Cytoscape** — network analysis

## Using pickle for fast round-trips

```python
from bainary.graph import CallGraph

cg = CallGraph.from_pickle("callgraph.pkl")  # future: CallGraph(pickle.load(open(...)))
assert cg.node_count > 0
print(cg.callers_of("malloc"))
```

## NetworkX advanced queries

```python
from bainary.graph import CallGraph
import networkx as nx

cg = CallGraph.from_artifact(artifact)

# Find the most central functions (by betweenness)
bc = nx.betweenness_centrality(cg.graph)
for addr, score in sorted(bc.items(), key=lambda x: -x[1])[:5]:
    print(f"  {cg.functions[addr].name}: {score:.3f}")

# Find all paths between two functions
paths = list(nx.all_simple_paths(cg.graph, "main", "printf"))
print(f"Simple paths from main to printf: {len(paths)}")

# Find the function with highest in-degree (called the most)
in_degrees = cg.graph.in_degree()
max_in = max(in_degrees, key=lambda x: x[1])
print(f"Most-called: {cg.functions[max_in[0]].name} ({max_in[1]} callers)")
```

## Using the refine cache

```python
from bainary.refine import Refiner, create_client
from bainary.refine.cache import RefinementCache

client = create_client(
    provider="openai",
    api_key=os.environ["OPENCODE_APIKEY"],
    base_url="https://opencode.ai/zen/go/v1",
    model="kimi-k2.7-code",
)

# Custom cache directory
cache = RefinementCache(model="kimi-k2.7-code")
print(f"Cache at: {cache._root}")

refiner = Refiner(client=client, cache=cache)
refined = refiner.refine(artifact, cg)   # First run: calls LLM (~3s/function)
refined = refiner.refine(artifact, cg)   # Second run: cache hit (<0.1s/function)
```

## Running with Ollama (local)

```python
from bainary.refine import Refiner, create_client

# If you have Ollama running locally with a model like codellama
client = create_client(
    provider="openai",                    # Ollama is OpenAI-compatible
    api_key="ollama",                     # Ollama doesn't need a real key
    base_url="http://localhost:11434/v1", # Ollama's OpenAI endpoint
    model="codellama:7b",
)

refiner = Refiner(client=client)
refined = refiner.refine(artifact)
```

## Checking dangerous function calls

```python
from bainary.lift import lift
from bainary.graph import CallGraph

artifact = lift("target.elf")
cg = CallGraph.from_artifact(artifact)

dangerous = {"system", "exec", "popen", "fork", "CreateRemoteThread", "WinExec"}
for name, node in cg.functions.items():
    callees = cg.callees_of(node.name)
    found = dangerous & callees
    if found:
        print(f"WARNING: {node.name} calls {found}")
```

## Batch analysis of multiple binaries

```python
from pathlib import Path
from bainary.lift import lift
from bainary.graph import CallGraph

corpus = Path("corpus/").glob("*.elf")
for path in corpus:
    try:
        artifact = lift(str(path), backend="lief_capstone")
        cg = CallGraph.from_artifact(artifact)
        print(f"{path.name}: {cg.node_count} functions, {cg.edge_count} calls")
        orphans = cg.orphans()
        if orphans:
            print(f"  Orphans: {sorted(orphans)}")
    except ValueError as e:
        print(f"{path.name}: SKIP ({e})")
```
