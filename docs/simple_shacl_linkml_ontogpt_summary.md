# Simple Presentation Summary: SHACL, LinkML, and OntoGPT

## Presentation Focus

This presentation mainly focuses on three tools and their roles in a knowledge extraction pipeline:

- **LinkML**
- **OntoGPT**
- **SHACL**

The overall idea is to show how unstructured text, such as aviation manuals or handbooks, can be transformed into structured and validated knowledge.

---

## 1. Why this topic matters

Many domain documents, such as aviation manuals, are written in natural language.  
This makes them difficult for machines to process directly.

To use such knowledge in an intelligent system, we need to:

1. define a clear structure for the knowledge  
2. extract structured information from text  
3. validate whether the extracted knowledge is correct and complete  

This is where LinkML, OntoGPT, and SHACL become relevant.

---

## 2. LinkML

**LinkML** is used to define the target schema.

It helps answer questions such as:

- What classes do we need?
- What fields does each class have?
- Which fields are required?
- What data types are allowed?

In simple terms:

**LinkML defines what the structured knowledge should look like.**

Example classes could be:

- Procedure
- ChecklistStep
- Warning
- FailureEvent

So LinkML is mainly about **schema design and structure definition**.

---

## 3. OntoGPT

**OntoGPT** is used for knowledge extraction from text.

Its role is to:

- read unstructured text
- use LLMs to identify important information
- produce structured outputs
- align extracted information with ontology-like categories

In simple terms:

**OntoGPT helps transform text into structured knowledge.**

For example, from a manual paragraph, OntoGPT may extract:

- an event
- a condition
- a procedure
- a warning
- a sequence of actions

So OntoGPT is mainly about **LLM-based information extraction**.

---

## 4. SHACL

**SHACL** is used to validate graph-based or structured knowledge against constraints.

Its role is to check whether the extracted data really follows the intended structure.

For example, SHACL can check:

- whether a procedure has a name
- whether a procedure has at least one step
- whether each step has an order number
- whether required relations exist
- whether values have the correct datatype

In simple terms:

**SHACL checks whether the structured knowledge is valid.**

So SHACL is mainly about **validation and quality control**.

---

## 5. Relationship Between the Three

The three tools can be understood as different steps in one pipeline:

### Step 1: LinkML
Define the schema and target structure.

### Step 2: OntoGPT
Extract structured knowledge from text.

### Step 3: SHACL
Validate whether the extracted knowledge satisfies the required constraints.

A simple summary is:

- **LinkML defines**
- **OntoGPT extracts**
- **SHACL validates**

---

## 6. Why this is useful

This combination is useful because it helps turn unstructured documents into knowledge that is:

- structured
- machine-readable
- easier to query
- more reliable
- better suited for downstream AI systems

This is especially important in domains where correctness matters.

---

## 7. Main Takeaway

The key message of the presentation is:

**LinkML, OntoGPT, and SHACL can work together to support a pipeline from unstructured text to structured and validated knowledge.**

A short final sentence could be:

**LinkML defines the structure, OntoGPT extracts the knowledge, and SHACL ensures that the result is valid.**
