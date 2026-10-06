# Resource Optimization

Dependency-light planning utilities for estimating emergency supplies, scoring response priority, planning approximate visit order, and allocating available stock.

## Modules

- `demand_estimation.py`: transparent per-person estimates for water, food, shelter and medical kits.
- `priority_analysis.py`: score demand using severity, exposed population, vulnerability and time to impact.
- `resource_database.py`: validated records and thread-safe in-memory planning inventory. `ResourceRecord.from_object` accepts backend ORM/Pydantic objects or dictionaries.
- `resource_allocation.py`: allocate inventory by priority, resource type, unit and nearest depot; shortages are returned explicitly.
- `route_optimization.py`: nearest-neighbour visit order using great-circle distance.

## Important limitations

The backend `POST /api/resources/plan` adapter loads records from the database, runs the planner and applies reservations back to persisted inventory. Direct use of `InventoryStore` remains in-memory. Road access, travel time, capacity, current hazards and vehicle constraints are not modeled by the route helper. Confirm all plans against live inventory and official incident-command instructions before dispatch.
