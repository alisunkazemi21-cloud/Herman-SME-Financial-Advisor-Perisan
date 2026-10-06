# Backend checkpoint technical report

Checkpoint: `backend-2026-10-05`. Data is synthetic.

The implementation includes the domain model, two migrations, API, separate evidence files and real PostgreSQL tests. The restaurant example starts with 100 kg, adds 50 kg of purchases, subtracts 120 kg theoretical consumption and 5 kg waste, and expects 25 kg. A count of 18 kg leaves 7 kg unexplained; the number does not establish its cause.

The full suite passed 86 tests with one real OCR test skipped; 28 backend/domain tests passed again after final changes. The read benchmark used 1,000 businesses, one million movements and 25 workers, with no observed errors or unauthorized reads. Final p95 was 1,946.38 ms. This excludes the full application path, OCR, document processing and model inference.

Methods, raw files, settings and open issues: [BACKEND_ACCEPTANCE](../research/BACKEND_ACCEPTANCE.md). This checkpoint did not change the interface.
