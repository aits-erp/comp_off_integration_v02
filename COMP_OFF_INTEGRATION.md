# Comp-Off integration change log

This log is the source of truth for code imported from the standalone
`comp_off` app. Add an entry here whenever the integrated implementation is
changed.

## 2026-10-13 — Initial integration

- Added `real_group/doctype/comp_off_source_request/`, a child DocType used by
  `Leave Application` to record exactly which Compensatory Leave Request
  credits are consumed.
- Added the two Leave Application custom fields:
  `custom_comp_off_source_request` and `custom_comp_off_available_work_date`.
- Added `api/comp_off.py` for unused-credit lookup and FIFO data.
- Added server validation in `doc_events/leave_application.py`. It prevents
  reused, expired, unsubmitted, wrong-employee, wrong-leave-type, same-day,
  or multi-date source credits. It also requires one source credit per leave
  day.
- Replaced the prior Comp-Off single-day restriction with source-count
  validation, allowing a multi-day Comp-Off application only when each day is
  backed by a separate earned credit.
- Added Leave Application form behavior: visibility by Leave Type, source
  filtering, selected-work-date summary, and a non-blocking FIFO warning.
- Added an idempotent post-model-sync patch to migrate a legacy single Link
  value into child rows when this app replaces the standalone `comp_off` app.

### Changed-file map

| File | Change |
| --- | --- |
| `real_group_hrms/api/comp_off.py` | Whitelisted source-credit lookup and FIFO helper methods. |
| `real_group_hrms/doc_events/leave_application.py` | Source-credit validation and multi-day Comp-Off support. |
| `real_group_hrms/public/js/form/leave_application.js` | Form visibility, selection query, worked-date display, and FIFO warning. |
| `real_group_hrms/real_group/doctype/comp_off_source_request/` | New child DocType and controller. |
| `real_group_hrms/fixtures/custom_field.json` | New Leave Application fields. |
| `real_group_hrms/fixtures/property_setter.json` | Places the new fields immediately after Leave Type. |
| `real_group_hrms/patches/migrate_comp_off_source_request_to_multiselect.py` | Idempotent legacy data migration. |
| `real_group_hrms/patches.txt` | Registers the data migration after model sync. |

## 2026-10-13 — Frappe Cloud install compatibility

- Replaced the obsolete `cx-Oracle2~=8.3.1` package with
  `oracledb>=2.5,<3.0` in `pyproject.toml`. The old package cannot build in
  Frappe Cloud's isolated `uv` environment because its build script assumes
  `pkg_resources` is already installed.
- Updated the four Oracle integration import sites to use
  `import oracledb as cx_Oracle`. The alias deliberately keeps the existing
  connection and `DatabaseError` code unchanged while using Oracle's supported
  successor driver.

## Existing functionality deliberately retained

- Attendance-based Comp-Off allocation remains in
  `real_group_hrms/doc_events/attendance.py`.
- Compensatory Leave Request allocation/reversal remains in
  `real_group_hrms/overrides/compensatory_leave_request.py`.
- Monthly FIFO expiry remains in `real_group_hrms/tasks/expire_coff.py`.

## Validation checklist before production

1. Run `bench --site <staging-site> migrate` and confirm the custom fields and
   child DocType exist.
2. Verify one and multiple Comp-Off day applications, cancellation, source
   reuse prevention, expired-source rejection, and FIFO warning.
3. Reprocess a worked holiday and confirm it produces only one active
   Compensatory Leave Request and the expected leave-ledger balance.
