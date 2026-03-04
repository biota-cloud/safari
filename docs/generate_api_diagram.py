#!/usr/bin/env python3
"""
Tyto API Architecture Diagram Generator

Generates a visual architecture diagram using the 'diagrams' library.

Installation:
    pip install diagrams

Usage:
    python docs/generate_api_diagram.py

Output:
    docs/tyto_api_architecture.png
"""

from diagrams import Diagram, Cluster, Edge
from diagrams.programming.framework import FastAPI
from diagrams.onprem.database import PostgreSQL
from diagrams.onprem.client import Client
from diagrams.generic.storage import Storage
from diagrams.generic.compute import Rack
from diagrams.programming.language import Python

# Diagram configuration
graph_attr = {
    "fontsize": "20",
    "bgcolor": "#1a1a2e",
    "pad": "0.5",
    "fontcolor": "white",
}

node_attr = {
    "fontsize": "12",
    "fontcolor": "white",
}

edge_attr = {
    "fontsize": "10",
    "fontcolor": "#cccccc",
    "color": "#666666",
}


def main():
    with Diagram(
        "Tyto API Architecture",
        filename="docs/tyto_api_architecture",
        show=False,
        direction="LR",
        graph_attr=graph_attr,
        node_attr=node_attr,
        edge_attr=edge_attr,
    ):
        # External Clients
        with Cluster("External Clients"):
            tauri = Client("Tauri Desktop")
            mobile = Client("Mobile App")

        # API Gateway
        with Cluster("Modal ASGI Gateway"):
            api = FastAPI("FastAPI Server")
            auth = Python("Auth Module")

        # GPU Workers
        with Cluster("Modal GPU Pool"):
            yolo_worker = Rack("YOLO Detection")
            hybrid_worker = Rack("SAM3 + Classifier")

        # Storage Layer
        with Cluster("Storage"):
            supabase = PostgreSQL("Supabase\n(api_keys, api_models,\napi_jobs)")
            r2 = Storage("R2 Bucket\n(model weights)")

        # Client to API
        tauri >> Edge(label="Bearer tyto_xxx") >> api
        mobile >> Edge(label="Bearer tyto_xxx") >> api

        # API internal flow
        api >> Edge(label="Validate key") >> auth
        auth >> Edge(label="SHA256 lookup") >> supabase

        # Model lookup
        api >> Edge(label="Lookup model") >> supabase

        # Dispatch to workers
        api >> Edge(label="Detection") >> yolo_worker
        api >> Edge(label="Classification") >> hybrid_worker

        # Workers access storage
        yolo_worker >> Edge(label="Load weights") >> r2
        hybrid_worker >> Edge(label="Load classifier") >> r2

        # Progress updates
        yolo_worker >> Edge(label="Update progress", style="dashed") >> supabase
        hybrid_worker >> Edge(label="Update progress", style="dashed") >> supabase


if __name__ == "__main__":
    main()
    print("✓ Diagram generated: docs/tyto_api_architecture.png")
