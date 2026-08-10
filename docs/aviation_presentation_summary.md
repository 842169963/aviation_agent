# Presentation Summary: Ontology, Knowledge Extraction, and AI Advisory Support for Private Pilots

## 1. Core Topic

This presentation explains how unstructured aviation knowledge from manuals, handbooks, and checklists can be transformed into a **grounded, context-aware advisory system** for private pilots.

The main goal is not to replace the pilot, but to provide **decision-support assistance** in abnormal or emergency situations, especially when stress makes it difficult to quickly recall the correct procedure.

---

## 2. Motivation / Problem

Private pilots often:

- fly less frequently than professional pilots
- have less routine exposure to rare abnormal or emergency situations
- may forget checklists or procedures under stress
- may struggle to search long manuals quickly
- may misjudge risk in fast-changing situations

So the problem is not that manuals do not exist.  
The problem is that **manuals are static, while flight situations are dynamic**.

This motivates the move from static documentation to an **AI-based advisory assistant**.

---

## 3. Vision

The intended system should combine:

- aviation handbooks, manuals, and checklists
- ontology and knowledge graph technologies
- aircraft and environmental context data
- retrieval mechanisms
- agentic AI for orchestration

Its output should be:

- short
- grounded
- context-aware
- step-by-step guidance for the pilot

A future extension could include a digital twin of the aircraft and flight situation.

---

## 4. Why Ontology

Aviation manuals are mostly written in natural language.  
To make them usable by an intelligent system, their knowledge must be structured.

An **ontology** provides the conceptual model of the aviation domain.  
It defines the key concepts, properties, and relationships, such as:

- Aircraft
- Component
- Failure
- Procedure
- ChecklistStep
- Warning
- SensorState
- PilotAction

So ontology answers the question:

**What kinds of entities exist in this domain, and how are they related?**

---

## 5. Ontology vs Knowledge Graph

This distinction is important:

- **Ontology** = the conceptual structure or blueprint
- **Knowledge Graph** = the populated graph containing actual entities and relations

In simple terms:

- ontology defines the semantic model
- the knowledge graph stores real structured domain knowledge based on that model

Example:

- ontology may define `EmergencyProcedure`, `AbnormalSituation`, and `ProcedureStep`
- the knowledge graph may contain a specific instance such as `EngineFailureAfterTakeoff`

---

## 6. From Natural Language to Structured Knowledge

Since manuals and PDFs are unstructured text, the system needs a way to extract useful knowledge from them.

This is where LLM-based extraction becomes useful.

The general idea is:

- input: manuals, handbooks, checklists, procedure descriptions
- extraction: identify conditions, events, actions, warnings, and relations
- output: structured knowledge elements that can populate a knowledge graph

---

## 7. Role of OntoGPT

**OntoGPT** can be used as an extraction tool.

Its role in the pipeline is to:

- process unstructured text
- use LLMs to identify relevant knowledge
- align extracted content with ontology-based structures
- produce structured output that can later be stored in a knowledge graph

So in short:

**OntoGPT helps transform aviation text into structured, ontology-aligned knowledge.**

---

## 8. Role of LinkML

**LinkML** is not mainly for extraction.  
Its purpose is to define the **target schema**.

This means it helps specify:

- what classes exist
- what fields each class should have
- what data types are allowed
- which fields are required
- how structured knowledge should be represented

So:

- **LinkML defines the structure**
- **OntoGPT performs the extraction**

This separation is important in the presentation.

---

## 9. Role of SHACL

After structured knowledge is extracted and added to a graph, it still needs to be validated.

This is where **SHACL** fits in.

SHACL can be used to validate graph data against constraints such as:

- whether a procedure has a name
- whether a procedure has at least one step
- whether each step has an order number
- whether required relations exist
- whether values have the correct type

So SHACL acts as a:

- validation layer
- guardrail
- quality-control mechanism for the knowledge graph

This is especially important in aviation, because unreliable graph entries may later lead to unreliable retrieval or advice.

A clear division of roles is:

- **LinkML defines the target schema**
- **OntoGPT extracts structured knowledge**
- **SHACL validates the resulting graph data**

---

## 10. Hallucination and Reliability

LLMs may hallucinate because they generate plausible text rather than directly verifying real-world facts.

In a safety-critical domain such as aviation, this is dangerous.

To reduce hallucination, the system should rely on:

- grounding in source manuals
- structured extraction
- ontology-based constraints
- graph-based representation
- SHACL validation
- retrieval before generation

So the model should not invent advice freely.  
Instead, it should retrieve and organize **grounded domain knowledge**.

---

## 11. RAG and Hybrid RAG

A knowledge graph alone is not enough, because a large amount of aviation knowledge still exists in text documents.

This is why **RAG (Retrieval-Augmented Generation)** is useful.

RAG works by:

1. retrieving relevant information from documents
2. using the retrieved information to support generation

However, for this scenario, **Hybrid RAG** is more suitable.

Hybrid RAG combines:

- **vector retrieval** for semantically similar text passages
- **knowledge graph retrieval** for explicit relations, dependencies, and structured reasoning

Benefits:

- more grounded retrieval
- better explainability
- better use of both text and graph knowledge
- lower hallucination risk

---

## 12. Role of Agentic AI

In this presentation, **Agentic AI** should not be described as an autonomous pilot.

Its role is better understood as **orchestration**.

That means it coordinates steps such as:

- detecting flight context
- identifying possible abnormal situations
- selecting relevant graph and document modules
- retrieving grounded procedures
- assembling short, step-by-step guidance

So:

**Agentic AI is the orchestration layer, not a replacement for the human pilot.**

---

## 13. Overall Pipeline

A concise pipeline for the presentation is:

**Aviation manuals / handbooks / checklists**  
→ **LLM-based extraction (e.g. OntoGPT)**  
→ **Schema / ontology definition (e.g. LinkML)**  
→ **Knowledge graph construction**  
→ **SHACL validation**  
→ **Hybrid RAG retrieval (KG + vector)**  
→ **Agentic orchestration**  
→ **Grounded advisory support for private pilots**

This is the main architecture the presentation should communicate.

---

## 14. Main Takeaway

The presentation is not mainly about introducing isolated tools.

It is about showing how:

- ontology-based modeling
- text-to-knowledge extraction
- graph validation
- hybrid retrieval
- and agentic orchestration

can be combined into a **grounded aviation advisory assistant** for private pilots.

A good one-sentence summary is:

**The presentation explains how unstructured aviation manuals can be transformed into validated, retrievable, and context-aware knowledge for AI-supported pilot advisory systems.**
