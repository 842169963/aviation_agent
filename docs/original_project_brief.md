We want to build an AI-based advisory assistant for private pilots. The problem is that private pilots usually have less training and less frequent flying experience than professional pilots. In normal situations this may be fine, but in emergencies or abnormal situations they may forget the correct checklist, procedure, or response under stress.

The idea is to create a system that uses:

aviation handbooks and manuals

ontology and knowledge graphs

live aircraft and environment data

agentic AI for orchestration

A future work: possibly a digital twin of the aircraft and current flight situation

The system should not replace the pilot. It should act as a decision-support assistant that gives grounded, context-aware, step-by-step advice.

Core Problem

Private pilots may:

fly infrequently

forget rare emergency procedures

struggle to search long manuals during stress

misjudge risk in fast-changing situations

need help not only during disasters, but also before a situation becomes worse

So the goal is to move from static manuals to real-time intelligent advisory support.


Main Vision

The system should:

extract knowledge from FAA handbooks, checklists, and aircraft manuals

structure this knowledge into an ontology-based knowledge graph

connect to aircraft sensors and flight context

identify the current situation

retrieve the relevant procedure or warning

provide short, clear, step-by-step guidance to the pilot
Agentic AI

The AI should not “freely decide” like magic. It should coordinate the workflow:

detect context

identify possible situations

select the relevant graph modules

retrieve grounded procedures

explain what to do

You need to learn 
Basics of what is Ontology 
The relation between Ontology and Knowledge Graph
How can we create knowledge Graph from natural language (e.g. Books, PDF and ...)
Why Hallucination happened in GenAIs and how we can reduce it in LLMs?
What is RAG?
What is Hybrid-Rag (KG combine with Vector)?
How we can retrieve from a rag?
What is Agentic AI?