#!/usr/bin/env python3
"""Export OpenAPI spec as JSON/YAML files"""

import json
import yaml
from server import app

def export_openapi():
    """Export OpenAPI specification to JSON and YAML files"""
    openapi_schema = app.openapi()
    
    # Export as JSON
    with open("openapi.json", "w") as f:
        json.dump(openapi_schema, f, indent=2)
    
    # Export as YAML
    with open("openapi.yaml", "w") as f:
        yaml.dump(openapi_schema, f, default_flow_style=False, sort_keys=False)
    
    print("✅ OpenAPI spec exported to openapi.json and openapi.yaml")

if __name__ == "__main__":
    export_openapi()