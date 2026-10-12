# ChatGPT native probe fix

- Root issue: json.loads accepted 1e9999 by converting it to infinity.
- Fix: reject non-finite values after parse_float/parse_int conversion.
- Added negative cases for positive/negative exponent overflow and top-level/nested placement.
- Scope: evidence/entry-probes/chatgpt only.
