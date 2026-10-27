# Illustrative flood-data CSV templates

Every row in these templates is invented solely to demonstrate column names and formats. It is
not a provider record, must never be copied into training data, and cannot be used to establish
flood or flood-free labels. The sentinel values (`ILLUSTRATIVE_ONLY` and `UNVERIFIED`) are
intentional; the NWDP adapter or readiness checks should reject or block them.

Copy the header only when preparing a real import. Preserve the actual provider export unchanged
in a separate raw directory. Fill canonical files only from authorized source records, retain a
source hash and field-mapping record, and obtain the independent approval and license evidence
described in `../../../docs/FLOOD_DATA_IMPORT_GUIDE.md`.

Files:

- `nwdp_cwc_water_levels_illustrative.csv`: column shape of the inspected NWDP/CWC hourly CSV
  export; not a genuine export.
- `nwdp_site_mapping_illustrative.csv`: manual mapping fields required by the NWDP normalizer.
- `danger_levels_illustrative.csv`, `coverage_illustrative.csv`,
  `crosswalk_illustrative.csv`, and `predictors_illustrative.csv`: canonical importer field
  examples. Their sentinel values deliberately do not provide verified evidence.
