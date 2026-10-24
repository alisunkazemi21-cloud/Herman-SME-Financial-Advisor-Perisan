# Reviewed SKU changes preserve import history

Herman can internally review dated item names and SKU aliases. Imports resolve each row using its event date, retain the original source text and record the selected label definition. Conflicting aliases are rejected at the database boundary.

Focused storage and import/correction checks passed. Windows full regression passed 418 tests with one skip; Linux CI passed 417 with two skips. This is an internal backend slice; visible catalog editing, historical pack-use bindings and complete C16 acceptance remain unfinished.
