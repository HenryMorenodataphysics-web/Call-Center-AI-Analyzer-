# Business-scoped knowledge ingestion v1

## Purpose

Knowledge ingestion v1 lets an authorized local reviewer upload company
policies and playbooks for retrieval-augmented Copilot answers. Documents are
not used to retrain Qwen. They are extracted, divided into bounded passages,
stored locally, and retrieved only when relevant to a question.

## Streamlit workflow

Open **Knowledge Base Admin** and provide:

- business ID;
- document title and type;
- version and effective date;
- language and market;
- PDF, DOCX, TXT, or Markdown file;
- explicit local-demo approval confirmation.

Unchecked documents are registered as `pending_review` and excluded from the
Copilot. Checked documents are marked `approved_demo` and become searchable.
The page shows document, approval, and chunk counts plus a bounded retrieval
test table. No deletion control is included in v1.

## Processing

1. Validate the business ID, metadata, extension, filename, and 10 MB limit.
2. Store the source beneath `.runtime/knowledge_base/<business_id>/`.
3. Extract text with `pypdf`, `docx2txt`, or UTF-8 text loading.
4. Reject files without sufficient extractable text.
5. Reject common embedded prompt-injection instructions.
6. Split text with LangChain's `RecursiveCharacterTextSplitter` using 1,200
   characters and 150 characters of overlap.
7. Persist a document registry and JSONL chunk index.
8. Retrieve only approved chunks for the selected business.

Every chunk retains document ID, business, title, type, version, effective
date, language, market, page when available, source filename, and content hash
provenance.

## Storage and privacy

All uploaded sources, registries, and chunks remain under `.runtime/`, which is
ignored by Git. The checked-in repository contains only the ingestion code and
contract. The local portfolio UI has no authentication, malware scanner, or
enterprise document-approval workflow; do not upload confidential material to
an untrusted installation.

## Retrieval architecture

The existing checked-in demo policies and approved uploaded chunks share the
same `PolicyRetriever` interface. Retrieval is lexical in v1 and preserves a
safe no-model fallback. A future semantic or hybrid retriever can implement the
same interface without changing Agent Memory, KPI calculation, or the Copilot
provider.

Checked-in demo policies are available only to `demo_customer_service`.
Uploaded indexes are isolated by `business_id`, preventing one business from
retrieving another business's passages.

## Security boundaries

- Document text is untrusted evidence, never an instruction to the application
  or LLM.
- Common prompt-injection phrases block ingestion.
- Only `approved_demo` chunks enter retrieval.
- Retrieval citations include business and version information.
- A policy passage can create a review signal but cannot prove misconduct.
- Human confirmation is required before operational or employment action.
- Scanned PDFs require a future OCR path and are rejected when no text can be
  extracted.

## Future adapters

- semantic embeddings;
- hybrid lexical and vector retrieval;
- governed enterprise authentication and roles;
- malware scanning;
- OCR;
- approval, retirement, and supersession workflows;
- business-profile validation;
- production vector stores such as pgvector or Qdrant.
