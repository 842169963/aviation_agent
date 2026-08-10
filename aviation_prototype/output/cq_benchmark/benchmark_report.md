# CQ SPARQL Benchmark — V1 vs V2 Ontology

- Scored CQs: **35**
- Generator model: `gpt-4o-mini`  (openai)
- Judge model: `gpt-4o`  (openai)

## Summary

| Metric | V1 | V2 |
|---|---:|---:|
| Total score | 12.0 / 35 | 17.0 / 35 |
| Avg score | 0.343 | 0.486 |
| 1.0 | 6 | 11 |
| 0.5 | 12 | 12 |
| 0.0 | 17 | 12 |

**Structural wins (V1 fails, V2 ≥ 0.5):** 10

**Token cost:** generator in=76184 out=8522; judge in=34426 out=4939

## Per-CQ scores

| CQ | Question | V1 | V2 | Struct. win |
|---|---|---:|---:|:---:|
| CQ001 | What techniques should a pilot use for emergency landings in adverse terrain conditions? | 0.5 | 0.5 |  |
| CQ002 | What are the conditions that necessitate a forced landing? | 1.0 | 1.0 |  |
| CQ003 | What psychological factors can impair a pilot's decision-making during an emergency landin | 0.0 | 0.0 |  |
| CQ004 | What are the risks associated with excessive nose-low pitch attitude and high sink rate du | 0.0 | 0.0 |  |
| CQ005 | What factors should a pilot consider when selecting an emergency landing site? | 0.5 | 0.5 |  |
| CQ006 | What precautions should be taken regarding flap usage during final approach? | 0.5 | 1.0 | ✅ |
| CQ007 | What factors should a pilot consider when planning an approach to land? | 0.0 | 0.5 | ✅ |
| CQ008 | What types of terrain are considered suitable for emergency landings? | 0.0 | 0.0 |  |
| CQ009 | What considerations should a pilot take into account when selecting a landing area in conf | 0.5 | 0.5 |  |
| CQ010 | What are the recommended procedures for executing a tree landing? | 1.0 | 1.0 |  |
| CQ011 | What are the recommended procedures for executing a water landing and a snow landing? | 0.0 | 0.0 |  |
| CQ012 | What actions should a pilot take immediately after an engine failure during initial climb? | 0.5 | 0.0 |  |
| CQ013 | What are the procedures to follow during an emergency descent due to an engine fire? | 1.0 | 1.0 |  |
| CQ014 | What are the procedures for handling an in-flight fire? | 0.5 | 0.5 |  |
| CQ015 | What steps should a pilot take upon discovering an in-flight engine compartment fire? | 0.5 | 1.0 | ✅ |
| CQ016 | What steps should a pilot take when an electrical fire is detected? | 0.0 | 1.0 | ✅ |
| CQ017 | What actions should a pilot take in response to a cabin fire? | 1.0 | 0.0 |  |
| CQ018 | What actions should a pilot take when encountering an asymmetric split flap situation duri | 0.0 | 0.0 |  |
| CQ019 | What actions can a pilot take to maintain pitch control during a loss of elevator control? | 0.0 | 0.0 |  |
| CQ020 | What actions should a pilot take when landing with one main gear retracted? | 0.5 | 0.5 |  |
| CQ021 | What indications should a pilot expect from the airspeed indicator, VSI, and altimeter dur | 0.0 | 0.0 |  |
| CQ022 | What are the corrective actions for specific abnormal engine instrument indications? | 0.0 | 0.5 | ✅ |
| CQ023 | What actions should a pilot take in response to an inadvertent door opening during flight? | 1.0 | 1.0 |  |
| CQ024 | What immediate actions should a VFR pilot take when encountering IMC? | 1.0 | 1.0 |  |
| CQ025 | What should a pilot do to maintain control of the airplane during spatial disorientation? | 0.5 | 0.5 |  |
| CQ026 | What are the key steps a pilot must follow for effective emergency attitude control? | 0.5 | 1.0 | ✅ |
| CQ027 | What are the recommended bank angle limits for turns to ensure safety during flight? | 0.0 | 0.5 | ✅ |
| CQ028 | What are the necessary actions a pilot must take to achieve a proper climb? | 0.0 | 0.0 |  |
| CQ029 | What is the maximum allowable rate of descent during a power reduction? | 0.0 | 0.5 | ✅ |
| CQ030 | What should an untrained instrument pilot avoid during maneuvers to maintain control of th | 0.5 | 0.5 |  |
| CQ031 | What factors should a pilot consider when transitioning from instrument to visual flight? | 0.0 | 0.0 |  |
| CQ032 | What emergency systems can be deployed in case of an engine failure? | 0.0 | 1.0 | ✅ |
| CQ033 | What conditions necessitate the deployment of a ballistic parachute system? | 0.0 | 1.0 | ✅ |
| CQ034 | What actions does the EAL system take when it detects pilot incapacitation? | 0.5 | 0.5 |  |
| CQ035 | What procedures should a pilot follow in the event of a pitot-static system failure during | 0.0 | 0.0 |  |

## Top structural wins (V2 unlocks queries V1 cannot express)

### CQ006 — What precautions should be taken regarding flap usage during final approach?
- Expected: Flaps should be used to improve maneuverability at slow speed, but caution is needed due to increased drag and decreased gliding distance.
- V1: **0.5** — The V1 results contain actions related to flap usage, but they lack explicit connection to final approach or detailed precautions regarding maneuverability, stalling speed, or drag. The information is partially relevant but does not fully address the CQ's expected answer or required concepts.
- V2: **1.0** — The V2 results include actions related to flap usage and warnings that provide additional context about precautions, such as stalling speed and operational risks. This aligns well with the expected answer and required concepts, making the results comprehensive and relevant.

V2 query:
```sparql
PREFIX av: <https://example.org/aviation/>
SELECT ?procName ?action ?warning WHERE {
  ?p a av:EmergencyProcedure ; av:name ?procName ; av:hasStep ?step .
  ?step av:action ?action .
  OPTIONAL { ?p av:hasWarning ?w . ?w av:description ?warning . }
  FILTER(CONTAINS(LCASE(STR(?action)), "flap") || CONTAINS(LCASE(STR(?procName)), "final approach"))
} LIMIT 20
```

V2 result rows (first 5 of 8):
```json
[
  {
    "procName": "Tree Landing",
    "action": "Use the normal landing configuration (full flaps, gear down)",
    "warning": null
  },
  {
    "procName": "Electrical System Failure",
    "action": "Plan for a no-flap landing and anticipate manual landing gear extension",
    "warning": "The electrically-powered landing gear and flaps do not function properly on the power left in a partially-depleted battery."
  },
  {
    "procName": "Water Ditching",
    "action": "Use no more than intermediate flaps on low-wing airplanes.",
    "warning": null
  },
  {
    "procName": "Emergency Descent",
    "action": "Ensure airspeed does not exceed never-exceed speed, maximum landing gear extended speed, or maximum flap extended speed",
    "warning": "Prolonged practice of emergency descents should be avoided to prevent excessive cooling of the engine cylinders."
  },
  {
    "procName": "Emergency Descent",
    "action": "Extend landing gear and flaps as recommended by the manufacturer",
    "warning": "Prolonged practice of emergency descents should be avoided to prevent excessive cooling of the engine cylinders."
  }
]
```

### CQ015 — What steps should a pilot take upon discovering an in-flight engine compartment fire?
- Expected: The pilot should shut off the fuel supply by placing the mixture control in idle cut off and the fuel selector to OFF, while leaving the ignition switch ON.
- V1: **0.5** — The V1 query retrieves actions related to 'Engine Fire,' including 'Shut off the fuel supply to the engine' and 'Leave the ignition switch ON,' which partially align with the expected answer. However, it also includes unrelated actions for 'Engine Failure' and 'Electrical Fire,' introducing noise and missing specificity about the engine compartment fire scenario.
- V2: **1.0** — The V2 query specifically filters for actions triggered by an 'engine compartment fire,' yielding relevant steps such as 'Leave the ignition switch ON' and 'Shut off the fuel supply to the engine.' This directly matches the expected answer and avoids irrelevant noise, making it fully correct.

V2 query:
```sparql
PREFIX av: <https://example.org/aviation/>
SELECT ?procName ?action WHERE {
  ?p a av:EmergencyProcedure ; av:name ?procName ; av:hasStep ?step ; av:hasTriggerCondition ?tc .
  ?step av:action ?action .
  ?tc av:description ?desc .
  FILTER(CONTAINS(LCASE(STR(?desc)), "engine compartment fire"))
} LIMIT 20
```

V2 result rows (first 4 of 4):
```json
[
  {
    "procName": "Engine Fire",
    "action": "Leave the ignition switch ON"
  },
  {
    "procName": "Engine Fire",
    "action": "Shut off the fuel supply to the engine"
  },
  {
    "procName": "Engine Fire",
    "action": "Do not shut off the electrical master switch unless necessary"
  },
  {
    "procName": "Engine Fire",
    "action": "Consider stopping the propeller rotation"
  }
]
```

### CQ016 — What steps should a pilot take when an electrical fire is detected?
- Expected: The pilot should attempt to identify the faulty circuit, turn off the battery master switch and alternator/generator switches if conditions permit, and land as soon as possible.
- V1: **0.0** — The V1 results focus on procedures for tree landings and landing gear malfunctions, which are unrelated to the CQ about electrical fire procedures. None of the required concepts, such as 'faulty circuit,' 'battery master switch,' or 'alternator/generator switches,' are addressed.
- V2: **1.0** — The V2 results directly address the CQ by listing actions specific to an electrical fire, including turning off the battery master switch and alternator/generator switches, checking circuit breakers, and other relevant steps. These align well with the expected answer and required concepts.

V2 query:
```sparql
PREFIX av: <https://example.org/aviation/>
SELECT ?procName ?action WHERE {
  ?p a av:EmergencyProcedure ; av:name ?procName ; av:hasStep ?step .
  ?step av:action ?action .
  ?p av:hasTriggerCondition ?tc .
  ?tc av:description ?desc .
  FILTER(CONTAINS(LCASE(STR(?desc)), "electrical fire"))
} LIMIT 20
```

V2 result rows (first 5 of 6):
```json
[
  {
    "procName": "Electrical Fire",
    "action": "Turn all individual electrical switches OFF"
  },
  {
    "procName": "Electrical Fire",
    "action": "Select electrical switches that were ON before the fire indication one at a time"
  },
  {
    "procName": "Electrical Fire",
    "action": "Turn off the battery master switch and alternator/generator switches"
  },
  {
    "procName": "Electrical Fire",
    "action": "Turn the electrical master switch OFF"
  },
  {
    "procName": "Electrical Fire",
    "action": "Turn the master switch back ON"
  }
]
```

### CQ026 — What are the key steps a pilot must follow for effective emergency attitude control?
- Expected: Trim the airplane for hands-off level flight, resist over-control, make smooth and small attitude changes, and utilize available aids.
- V1: **0.5** — The V1 results include emergency procedures and actions, but they lack specific focus on attitude control and the key steps outlined in the expected answer. While some actions like 'Maintain control of the airplane using flight instruments' are partially relevant, the majority of the results are unrelated to the CQ's focus.
- V2: **1.0** — The V2 results are more aligned with the CQ, as they include actions like 'Make all attitude changes smooth and small' and 'Execute a water landing at minimum speed and in a normal landing attitude,' which directly address emergency attitude control. The results also cover broader emergency procedures, making them comprehensive and relevant.

V2 query:
```sparql
PREFIX av: <https://example.org/aviation/>
SELECT ?procName ?action WHERE {
  ?p a av:EmergencyProcedure ; av:name ?procName ; av:hasStep ?step .
  ?step av:action ?action .
  FILTER(CONTAINS(LCASE(STR(?action)), "attitude") || CONTAINS(LCASE(STR(?procName)), "emergency"))
} LIMIT 20
```

V2 result rows (first 5 of 16):
```json
[
  {
    "procName": "Emergency Autoland",
    "action": "Initiate emergency descent"
  },
  {
    "procName": "Emergency Autoland",
    "action": "Broadcast position and intention to land"
  },
  {
    "procName": "Emergency Autoland",
    "action": "Transmit automated radio broadcasts"
  },
  {
    "procName": "Emergency Autoland",
    "action": "Set transponder to squawk 7700"
  },
  {
    "procName": "Emergency Autoland",
    "action": "Activate EAL system manually if needed"
  }
]
```

### CQ032 — What emergency systems can be deployed in case of an engine failure?
- Expected: Ballistic parachute systems and Emergency Autoland systems can be deployed.
- V1: **0.0** — V1 is marked as UNSUPPORTED, meaning it cannot handle the query or provide any relevant results for the competency question.
- V2: **1.0** — V2 successfully retrieves the two emergency systems mentioned in the expected answer: 'Ballistic Parachute System' and 'Emergency Autoland System.' The results are directly relevant to the competency question and include the required concepts.

V2 query:
```sparql
PREFIX av: <https://example.org/aviation/>
SELECT ?sysName WHERE {
  ?p a av:EmergencyProcedure ; av:hasStep ?step .
  ?step av:action ?action .
  ?p av:relatesToSystem ?s .
  ?s av:name ?sysName .
  FILTER(CONTAINS(LCASE(STR(?action)), "engine failure") || CONTAINS(LCASE(STR(?sysName)), "ballistic parachute") || CONTAINS(LCASE(STR(?sysName)), "emergency autoland"))
} LIMIT 20
```

V2 result rows (first 5 of 9):
```json
[
  {
    "sysName": "Emergency Autoland System"
  },
  {
    "sysName": "Emergency Autoland System"
  },
  {
    "sysName": "Emergency Autoland System"
  },
  {
    "sysName": "Emergency Autoland System"
  },
  {
    "sysName": "Emergency Autoland System"
  }
]
```


## Failure cases (V1 = 0 and V2 = 0)

These reveal data-quality gaps, not schema gaps — candidates for LLM re-extraction.

- **CQ003**: What psychological factors can impair a pilot's decision-making during an emergency landing?  
  V2 reason: V2 query attempts to filter for psychological hazards and decision-making but returns no results. Without any data, it cannot address the CQ.
- **CQ004**: What are the risks associated with excessive nose-low pitch attitude and high sink rate during an emergency landing?  
  V2 reason: V2 query execution returned no results, meaning it failed to retrieve any hazards or descriptions related to the required concepts such as nose-low pitch attitude, high sink rate, or structural damage.
- **CQ008**: What types of terrain are considered suitable for emergency landings?  
  V2 reason: V2 query attempts to filter for actions related to landing or terrain but returns no results. It does not provide any information about suitable terrain types for emergency landings, which is the expected answer.
- **CQ011**: What are the recommended procedures for executing a water landing and a snow landing?  
  V2 reason: The results for V2 are identical to V1 and similarly fail to address the required concepts of water landing, snow landing, minimum speed, normal landing attitude, or depth perception. The results focus on unrelated procedures like tree landings and landing gear malfunctions, which do not answer the CQ.
- **CQ018**: What actions should a pilot take when encountering an asymmetric split flap situation during landing?  
  V2 reason: The V2 results also fail to address the specific scenario of an asymmetric split flap situation during landing. While the query includes additional filters for terms like 'airspeed' and 'stall,' the results remain focused on unrelated procedures such as tree landings and landing gear malfunctions, without providing the expected actions or concepts.
- **CQ019**: What actions can a pilot take to maintain pitch control during a loss of elevator control?  
  V2 reason: The V2 query also returned no results, meaning it similarly fails to provide any relevant information about the actions a pilot can take to maintain pitch control during a loss of elevator control. It does not address the expected answer or required concepts.
- **CQ021**: What indications should a pilot expect from the airspeed indicator, VSI, and altimeter during a descent if the pitot-static system is partially blocked?  
  V2 reason: V2 query attempts to retrieve descriptions of airspeed indicators, VSI, and altimeters, but the result is empty. It does not provide the expected answer or address the required concepts.
- **CQ028**: What are the necessary actions a pilot must take to achieve a proper climb?  
  V2 reason: The V2 results are identical to V1 and suffer from the same issues. The rows do not provide the specific procedural steps for achieving a proper climb, nor do they mention key concepts like 'attitude indicator' or 'incremental power adjustment.' The results are focused on emergency procedures and are not relevant to the CQ.
- **CQ031**: What factors should a pilot consider when transitioning from instrument to visual flight?  
  V2 reason: V2 query execution returned no results, meaning it failed to retrieve any factors related to transitioning from instrument to visual flight as required by the competency question.
- **CQ035**: What procedures should a pilot follow in the event of a pitot-static system failure during IFR flight?  
  V2 reason: The V2 query also returned no results, indicating it did not retrieve any relevant data to address the competency question or cover the required concepts.