# Changelog

## v0.2.0
- Switched from Chat Completions `json_object` + local `jsonschema` to DeepSeek Responses API `json_schema`.
- Removed duplicated structural validation and `jsonschema` dependency.
- Split the 1412-line monolith into small modules with single responsibilities.
- Retained only criterion-specific semantic validation and exact evidence verification.
- Replaced custom nested API retry loops with the SDK's built-in retry mechanism.
- Removed concurrency from the MVP runner.
- Added unit tests and Git versioning.

## v0.1.0
- Initial monolithic DeepSeek Judge runner.
