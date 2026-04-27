# Hybrid RAG Evaluation Report

Generated: 2026-04-27T15:26:44

## Configuration

- Cases: `14`
- Include synthesis: `False`
- Abstain minimum final score: `3`
- Abstain maximum vector distance: `0.62`

## Summary

- Retrieval pass: `14/14`
- Synthesis pass: `SKIP`
- Total flagged cases: `0`

## Results

| Case | Category | Expected | Top 1 | Top 3 | Score | Distance | Abstain | Retrieval | Synthesis | Notes |
|---|---|---|---|---|---:|---:|---|---|---|---|
| `happy_imc_semantic` | happy_path | Inadvertent VFR Flight Into IMC | Inadvertent VFR Flight Into IMC | Inadvertent VFR Flight Into IMC<br>Inadvertent Door Opening In-Flight<br>Engine Failure After Takeoff (Single-Engine) | 3 | 0.5409 | NO | PASS | SKIP | Pure semantic phrasing; KG keyword score was previously 0. |
| `happy_cabin_smoke` | happy_path | Cabin Fire | Cabin Fire | Cabin Fire<br>Engine Fire<br>Electrical Fire | 15 | 0.3696 | NO | PASS | SKIP |  |
| `happy_parachute` | happy_path | Ballistic Parachute Deployment | Ballistic Parachute Deployment | Ballistic Parachute Deployment<br>Emergency Autoland<br>Landing Gear Malfunction | 15 | 0.3994 | NO | PASS | SKIP |  |
| `happy_snow_whiteout` | happy_path | Snow Landing | Snow Landing | Snow Landing<br>Tree Landing<br>Water Ditching | 15 | 0.3915 | NO | PASS | SKIP |  |
| `happy_efato` | happy_path | Engine Failure After Takeoff (Single-Engine) | Engine Failure After Takeoff (Single-Engine) | Engine Failure After Takeoff (Single-Engine)<br>Engine Fire<br>Total Flap Failure | 15 | 0.3075 | NO | PASS | SKIP | Also checks that training notes are not treated as operational actions in synthesis. |
| `synonym_electrical_fire` | semantic_variant | Electrical Fire | Electrical Fire | Electrical Fire<br>Landing Gear Malfunction<br>Engine Fire | 6 | 0.4881 | NO | PASS | SKIP |  |
| `synonym_landing_gear` | semantic_variant | Landing Gear Malfunction | Landing Gear Malfunction | Landing Gear Malfunction<br>Loss of Elevator Control (Down Cable Failure)<br>Snow Landing | 15 | 0.3843 | NO | PASS | SKIP |  |
| `synonym_open_door` | semantic_variant | Inadvertent Door Opening In-Flight | Inadvertent Door Opening In-Flight | Inadvertent Door Opening In-Flight<br>Engine Failure After Takeoff (Single-Engine)<br>Landing Gear Malfunction | 16 | 0.4457 | NO | PASS | SKIP |  |
| `synonym_emergency_descent` | semantic_variant | Emergency Descent | Emergency Descent | Emergency Descent<br>Loss of Elevator Control (Down Cable Failure)<br>Loss of Elevator Control (Up Cable Failure) | 16 | 0.3914 | NO | PASS | SKIP |  |
| `synonym_split_flap` | semantic_variant | Asymmetric Split Flap | Asymmetric Split Flap | Asymmetric Split Flap<br>Total Flap Failure<br>Landing Gear Malfunction | 15 | 0.4334 | NO | PASS | SKIP |  |
| `cross_fire_smoke` | ambiguous | N/A | Cabin Fire | Cabin Fire<br>Electrical Fire<br>Engine Fire | 15 | 0.3705 | NO | PASS | SKIP | Ambiguous by design; useful for inspecting competing top candidates. |
| `cross_fire_descent` | ambiguous | N/A | Cabin Fire | Cabin Fire<br>Engine Fire<br>Electrical Fire | 13 | 0.4343 | NO | PASS | SKIP | Ambiguous by design; current top result may be a fire procedure rather than Emergency Descent. |
| `unrelated_restaurant` | out_of_scope | ABSTAIN | Emergency Autoland | Emergency Autoland<br>Landing Gear Malfunction<br>Inadvertent Door Opening In-Flight | 4 | 0.7979 | YES | PASS | SKIP | Should ideally abstain instead of forcing an emergency procedure. |
| `unrelated_fuel_planning` | out_of_scope | ABSTAIN | Engine Fire | Engine Fire<br>Engine Failure After Takeoff (Single-Engine)<br>Electrical System Failure | 7 | 0.7476 | YES | PASS | SKIP | Should ideally abstain; current retrieval may still force a candidate. |

## Interpretation

- Happy-path failures usually indicate retrieval regression or stale vector index.
- Out-of-scope failures indicate the system needs an abstention gate before production use.
- Synthesis failures indicate prompt drift or missing KG structure.
