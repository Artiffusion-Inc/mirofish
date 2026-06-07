#!/usr/bin/env python3
"""
MiroFish-Local Quick Demo
=========================
One-click MiroFish simulation: upload seed news -> build knowledge graph -> view entity relationships

Usage:
    python demo.py              # Use default example seed
    python demo.py --seed FILE  # Use custom seed file

Prerequisites:
    1. .env file configured (at least LLM_API_KEY)
    2. Backend service running (npm run backend or python backend/run.py)
"""

import argparse
import json
import os
import sys
import time

try:
    import requests
except ImportError:
    print("Missing requests library, installing...")
    os.system(f"{sys.executable} -m pip install requests -q")
    import requests

API_BASE = "http://localhost:5001/api"
DEFAULT_SEED = os.path.join(os.path.dirname(__file__), "examples", "seed_news.txt")


def check_health():
    """Check if the backend service is running"""
    try:
        r = requests.get("http://localhost:5001/health", timeout=5)
        return r.status_code == 200
    except requests.ConnectionError:
        return False


def upload_and_generate_ontology(seed_path):
    """Upload seed file and generate ontology"""
    print(f"\n📄 Uploading seed file: {seed_path}")
    with open(seed_path, "r", encoding="utf-8") as f:
        content = f.read()
    print(f"   File size: {len(content)} characters")
    print(f"   Preview: {content[:80]}...")

    print("\n🧠 Generating ontology (entity types & relation types)...")
    r = requests.post(
        f"{API_BASE}/graph/ontology/generate",
        files={"file": (os.path.basename(seed_path), content, "text/plain")},
        timeout=120,
    )
    r.raise_for_status()
    data = r.json()

    project_id = data.get("project_id") or data.get("data", {}).get("project_id")
    if not project_id:
        print(f"   Response: {json.dumps(data, ensure_ascii=False, indent=2)}")
        return data

    print(f"   ✅ Project created successfully! project_id = {project_id}")

    # Show ontology info
    ontology = data.get("ontology") or data.get("data", {}).get("ontology")
    if ontology:
        entity_types = ontology.get("entity_types", [])
        edge_types = ontology.get("edge_types", [])
        print(f"\n📊 Ontology analysis results:")
        print(f"   Entity types ({len(entity_types)}):")
        for et in entity_types[:10]:
            name = et if isinstance(et, str) else et.get("name", et)
            print(f"     • {name}")
        print(f"   Relation types ({len(edge_types)}):")
        for er in edge_types[:10]:
            name = er if isinstance(er, str) else er.get("name", er)
            print(f"     • {name}")

    return data


def build_graph(project_id):
    """Build knowledge graph"""
    print(f"\n🕸️  Building knowledge graph...")
    r = requests.post(
        f"{API_BASE}/graph/build",
        json={"project_id": project_id},
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()

    task_id = data.get("task_id") or data.get("data", {}).get("task_id")
    if not task_id:
        print(f"   Response: {json.dumps(data, ensure_ascii=False, indent=2)}")
        return data

    print(f"   Task submitted, task_id = {task_id}")

    # Poll task status
    for i in range(60):
        time.sleep(3)
        r = requests.get(f"{API_BASE}/graph/task/{task_id}", timeout=10)
        status_data = r.json()
        status = status_data.get("status") or status_data.get("data", {}).get("status", "unknown")
        print(f"   ⏳ Building... ({(i+1)*3}s) Status: {status}")

        if status in ("completed", "done", "success"):
            print(f"   ✅ Knowledge graph build complete!")
            graph_id = status_data.get("graph_id") or status_data.get("data", {}).get("graph_id")
            if graph_id:
                show_graph(graph_id)
            return status_data

        if status in ("failed", "error"):
            print(f"   ❌ Build failed: {status_data}")
            return status_data

    print("   ⏰ Timeout, please check results via API later")
    return None


def show_graph(graph_id):
    """Display graph data"""
    r = requests.get(f"{API_BASE}/graph/data/{graph_id}", timeout=10)
    if r.status_code != 200:
        return

    data = r.json()
    nodes = data.get("nodes") or data.get("data", {}).get("nodes", [])
    edges = data.get("edges") or data.get("data", {}).get("edges", [])

    print(f"\n🌐 Knowledge graph overview:")
    print(f"   Nodes: {len(nodes)}")
    print(f"   Edges: {len(edges)}")

    if nodes:
        print(f"\n   Main entities:")
        for node in nodes[:8]:
            name = node.get("name") or node.get("label", "?")
            ntype = node.get("type") or node.get("entity_type", "")
            print(f"     • [{ntype}] {name}")

    if edges:
        print(f"\n   Main relations:")
        for edge in edges[:5]:
            src = edge.get("source_name") or edge.get("source", "?")
            tgt = edge.get("target_name") or edge.get("target", "?")
            rel = edge.get("type") or edge.get("relation", "?")
            print(f"     • {src} --[{rel}]--> {tgt}")


def main():
    parser = argparse.ArgumentParser(description="MiroFish-Local Quick Demo")
    parser.add_argument("--seed", default=DEFAULT_SEED, help="Seed file path")
    parser.add_argument("--skip-build", action="store_true", help="Skip graph building, only generate ontology")
    args = parser.parse_args()

    print("=" * 60)
    print("🐟 MiroFish-Local Quick Demo")
    print("=" * 60)

    # 1. Check service
    print("\n🔍 Checking backend service...")
    if not check_health():
        print("   ❌ Backend not running! Please start it with:")
        print("      npm run backend")
        print("   or:")
        print("      cd backend && uv run python run.py")
        sys.exit(1)
    print("   ✅ Backend service healthy (http://localhost:5001)")

    # 2. Check seed file
    if not os.path.exists(args.seed):
        print(f"\n   ❌ Seed file not found: {args.seed}")
        sys.exit(1)

    # 3. Generate ontology
    result = upload_and_generate_ontology(args.seed)

    # 4. Build graph (optional)
    if not args.skip_build:
        project_id = None
        if isinstance(result, dict):
            project_id = result.get("project_id") or result.get("data", {}).get("project_id")
        if project_id:
            build_graph(project_id)

    print("\n" + "=" * 60)
    print("🎉 Demo complete!")
    print("=" * 60)
    print("\nNext steps:")
    print("  1. Open http://localhost:3000 to view the frontend")
    print("  2. In the UI: create simulations, run them, and generate reports")
    print("  3. See README.md for complete features")
    print()


if __name__ == "__main__":
    main()
