# Knowledge base

This folder contains the documents searchable by the Agent Copilot. Retrieval
provides policy context; the LLM does not treat its own general knowledge as an
approved company policy.

## Files

- `compliance_guardrails.md`: privacy, safety, escalation, and responsible-use
  boundaries.
- `customer_service_playbook.md`: example service behaviors and coaching
  guidance.
- `qa_policy_demo.md`: example QA expectations used to demonstrate grounded
  policy retrieval.

These files are demonstration policies, not employer-approved documents.
Replace them with versioned, business-owned policies for operational use.

Documents uploaded through Streamlit are not stored here. They remain under
`.runtime/knowledge_base/<business_id>/` so confidential or employer-owned
content is not accidentally included in Git.
