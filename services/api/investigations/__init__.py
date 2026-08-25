"""
The investigation lifecycle — task 1.6.

Everything between "a citizen or analyst submitted something" and "there is a
durable, re-openable case file with a report on it". The three modules split by
the question they answer:

* `intake.py` — *what did we just receive?* Turns a JSON body or a multipart
  upload into `EvidenceItem`s, enforces the size and count caps, sanitises
  filenames, and puts the bytes in the blob store.
* `runner.py` — *what is happening to it right now?* Drives 1.3's graph,
  journals one `InvestigationEvent` per completed node so the SSE stream is
  observed progress rather than an estimate, and saves the finished state
  through 1.5's `EvidenceStore`.
* `report.py` — *what does it say?* Projects a finished `InvestigationState`
  into the package a citizen, a bank or a cyber cell actually reads, in JSON
  and as a PDF.

`routes/investigations.py` is the only caller. Nothing here imports FastAPI:
the HTTP status codes, the RBAC and the streaming response belong to the route,
and keeping them out of here is what lets the lifecycle be tested without a
client and moved onto 1.8's worker without being rewritten.
"""
