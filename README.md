## TomTom flow

The TomTom caller reads the OSMnx GeoPackage directly. It uses the midpoint
of each edge geometry, transforms it from EPSG:31983 to WGS84 (`lat,lon`),
and writes the traffic attributes to a separate GeoPackage. The source graph
is not overwritten. JSONL checkpoints allow interrupted runs to resume
without issuing requests that already succeeded.

Install the required packages and configure the API key:

```powershell
pip install geopandas osmnx requests
$env:TOMTOM_API_KEY = "your_api_key"
python scripts/api-caller.py
```

Input: `cache/gama_drive_reduced.gpkg` (`nodes` and `edges` layers)

Output: `cache/gama_drive_reduced_tomtom.gpkg`

Checkpoint: `cache/tomtom_flow_results.jsonl`
