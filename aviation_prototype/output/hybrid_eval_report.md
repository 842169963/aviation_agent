# Hybrid RAG Evaluation Report

Generated: 2026-04-22T16:51:48

## Configuration

- Cases: `14`
- Include synthesis: `True`
- Abstain minimum final score: `3`
- Abstain maximum vector distance: `0.62`

## Summary

- Retrieval pass: `14/14`
- Synthesis pass: `10/10`
- Total flagged cases: `0`

## Results

| Case | Category | Expected | Top 1 | Top 3 | Score | Distance | Abstain | Retrieval | Synthesis | Notes |
|---|---|---|---|---|---:|---:|---|---|---|---|
| `happy_imc_semantic` | happy_path | Inadvertent VFR Flight Into IMC | Inadvertent VFR Flight Into IMC | Inadvertent VFR Flight Into IMC<br>Inadvertent Door Opening In-Flight<br>Tree Landing | 3 | 0.5461 | NO | PASS | PASS | Pure semantic phrasing; KG keyword score was previously 0. |
| `happy_cabin_smoke` | happy_path | Cabin Fire | Cabin Fire | Cabin Fire<br>Engine Fire<br>Electrical Fire | 15 | 0.3588 | NO | PASS | PASS |  |
| `happy_parachute` | happy_path | Ballistic Parachute Deployment | Ballistic Parachute Deployment | Ballistic Parachute Deployment<br>Emergency Autoland<br>Landing Gear Malfunction | 13 | 0.3932 | NO | PASS | PASS |  |
| `happy_snow_whiteout` | happy_path | Snow Landing | Snow Landing | Snow Landing<br>Landing Gear Malfunction<br>Tree Landing | 15 | 0.3642 | NO | PASS | PASS |  |
| `happy_efato` | happy_path | Engine Failure After Takeoff (Single-Engine) | Engine Failure After Takeoff (Single-Engine) | Engine Failure After Takeoff (Single-Engine)<br>Engine Fire<br>Total Flap Failure | 16 | 0.3016 | NO | PASS | PASS | Also checks that training notes are not treated as operational actions in synthesis. |
| `synonym_electrical_fire` | semantic_variant | Electrical Fire | Electrical Fire | Electrical Fire<br>Cabin Fire<br>Engine Fire | 6 | 0.4962 | NO | PASS | PASS |  |
| `synonym_landing_gear` | semantic_variant | Landing Gear Malfunction | Landing Gear Malfunction | Landing Gear Malfunction<br>Loss of Elevator Control - Down Cable Failure<br>Snow Landing | 15 | 0.4113 | NO | PASS | PASS |  |
| `synonym_open_door` | semantic_variant | Inadvertent Door Opening In-Flight | Inadvertent Door Opening In-Flight | Inadvertent Door Opening In-Flight<br>Engine Failure After Takeoff (Single-Engine)<br>Cabin Fire | 15 | 0.4392 | NO | PASS | PASS |  |
| `synonym_emergency_descent` | semantic_variant | Emergency Descent | Emergency Descent | Emergency Descent<br>Loss of Elevator Control - Down Cable Failure<br>Loss of Elevator Control - Up Cable Failure | 16 | 0.3889 | NO | PASS | PASS |  |
| `synonym_split_flap` | semantic_variant | Asymmetric Split Flap | Asymmetric Split Flap | Asymmetric Split Flap<br>Total Flap Failure<br>Inadvertent Door Opening In-Flight | 15 | 0.4354 | NO | PASS | PASS |  |
| `cross_fire_smoke` | ambiguous | N/A | Cabin Fire | Cabin Fire<br>Engine Fire<br>Electrical Fire | 15 | 0.3628 | NO | PASS | SKIP | Ambiguous by design; useful for inspecting competing top candidates. |
| `cross_fire_descent` | ambiguous | N/A | Cabin Fire | Cabin Fire<br>Engine Fire<br>Electrical Fire | 13 | 0.4428 | NO | PASS | SKIP | Ambiguous by design; current top result may be a fire procedure rather than Emergency Descent. |
| `unrelated_restaurant` | out_of_scope | ABSTAIN | Emergency Autoland | Emergency Autoland<br>Electrical System Failure<br>Landing Gear Malfunction | 3 | 0.7903 | YES | PASS | SKIP | Should ideally abstain instead of forcing an emergency procedure. |
| `unrelated_fuel_planning` | out_of_scope | ABSTAIN | Engine Fire | Engine Fire<br>Electrical System Failure<br>Engine Failure After Takeoff (Single-Engine) | 8 | 0.7378 | YES | PASS | SKIP | Should ideally abstain; current retrieval may still force a candidate. |

## Interpretation

- Happy-path failures usually indicate retrieval regression or stale vector index.
- Out-of-scope failures indicate the system needs an abstention gate before production use.
- Synthesis failures indicate prompt drift or missing KG structure.
