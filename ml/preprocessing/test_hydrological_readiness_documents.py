import json
import re
from pathlib import Path
from urllib.parse import urlsplit


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DOCS = REPOSITORY_ROOT / "docs"
REQUEST = DOCS / "CWC_NWIC_PROVIDER_CLARIFICATION_REQUEST_DRAFT.md"
TRACKER = DOCS / "CWC_NWIC_PROVIDER_RESPONSE_TRACKER.md"
GATE = DOCS / "HYDROLOGICAL_METADATA_READINESS_GATE.json"
EVIDENCE_PLAN = DOCS / "HYDROLOGICAL_EVIDENCE_ACQUISITION_PLAN.json"


def _tracker_rows():
    rows = {}
    for line in TRACKER.read_text(encoding="utf-8").splitlines():
        if not re.match(r"^\|\s*\d+\s*\|", line):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        rows[int(cells[0])] = cells
    return rows


def _request_questions():
    request = REQUEST.read_text(encoding="utf-8")
    return {
        int(match.group(1)): match.group(2)
        for match in re.finditer(r"(?m)^\s*(\d+)\.\s+(.+)$", request)
    }


def _field_is_reviewed(field):
    review = field["review"]
    if field["status"] == "CONFIRMED":
        return (
            review["review_decision"] == "SUFFICIENT"
            and all(
                review[key]
                for key in ("evidence_source", "evidence_scope", "reviewer", "review_date")
            )
        )
    if field["status"] == "NOT_APPLICABLE":
        return (
            review["review_decision"] == "NOT_APPLICABLE"
            and all(
                review[key]
                for key in (
                    "evidence_source",
                    "evidence_scope",
                    "reviewer",
                    "review_date",
                    "justification",
                )
            )
        )
    return field["status"] == "UNRESOLVED" and review["review_decision"] == "PENDING"


def test_all_24_draft_questions_have_complete_tracker_entries():
    draft = REQUEST.read_text(encoding="utf-8")
    question_numbers = [
        int(match.group(1))
        for match in re.finditer(r"(?m)^\s*(\d+)\.\s+", draft)
    ]
    rows = _tracker_rows()

    assert question_numbers == list(range(1, 25))
    assert set(rows) == set(question_numbers)
    assert all(len(row) == 8 for row in rows.values())
    assert all(row[3] == "NOT_RECORDED" for row in rows.values())
    assert all(row[4] == "None recorded" for row in rows.values())
    assert all(row[5] == "None recorded" for row in rows.values())
    assert all(row[6] == "PENDING" for row in rows.values())


def test_contact_and_provider_response_remain_unverified_and_unrecorded():
    tracker = TRACKER.read_text(encoding="utf-8")
    assert "**Contact verification:** `UNVERIFIED`" in tracker
    assert "**External response:** `NOT_RECORDED`" in tracker
    assert "**Draft sent:** `NOT_RECORDED`" in tracker


def test_both_datasets_remain_blocked_with_unresolved_traceable_fields():
    gate = json.loads(GATE.read_text(encoding="utf-8"))
    assert gate["normalization_gate"]["decision"] == "BLOCKED"
    assert gate["normalization_gate"]["may_proceed"] is False
    assert gate["field_review_policy"]["provider_response_alone_is_sufficient"] is False
    assert gate["field_review_policy"]["unanswered_response_is_confirmation"] is False
    assert len(gate["datasets"]) == 2

    for dataset in gate["datasets"]:
        assert dataset["readiness_status"] == "BLOCKED"
        assert len(dataset["fields"]) == 15
        assert all(field["status"] == "UNRESOLVED" for field in dataset["fields"])
        assert all(_field_is_reviewed(field) for field in dataset["fields"])


def test_readiness_confirmation_requires_reviewed_evidence_traceability():
    gate = json.loads(GATE.read_text(encoding="utf-8"))
    field = json.loads(json.dumps(gate["datasets"][0]["fields"][0]))
    field["status"] = "CONFIRMED"
    assert not _field_is_reviewed(field)

    field["review"].update(
        {
            "evidence_source": "provider-data-dictionary.pdf, page 4",
            "evidence_scope": "Exact Godavari resource and listed station IDs",
            "review_decision": "SUFFICIENT",
            "reviewer": "Project reviewer",
            "review_date": "2026-10-28",
        }
    )
    assert _field_is_reviewed(field)

    field["status"] = "NOT_APPLICABLE"
    field["review"]["review_decision"] = "NOT_APPLICABLE"
    assert not _field_is_reviewed(field)
    field["review"]["justification"] = "Documented reason"
    assert _field_is_reviewed(field)


def test_local_document_links_resolve():
    documents = [
        REPOSITORY_ROOT / "ml" / "datasets" / "hydrological" / "README.md",
        REQUEST,
        TRACKER,
        DOCS / "STAGE_2_PART_B_HYDROLOGICAL_AUDIT.md",
        DOCS / "STAGE_2_PART_B2_METADATA_PROVENANCE_REVIEW.md",
        DOCS / "PHYSICS_BASED_FLOOD_MODELLING_PREPARATION.md",
        DOCS / "STAGE_2_PART_A_VERIFICATION_RESULTS.md",
    ]
    link_pattern = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")

    for document in documents:
        content = document.read_text(encoding="utf-8")
        for raw_target in link_pattern.findall(content):
            target = raw_target.split(maxsplit=1)[0].strip("<>")
            parsed = urlsplit(target)
            if parsed.scheme or target.startswith("#"):
                continue
            local_path = (document.parent / parsed.path).resolve()
            assert local_path.exists(), f"{document}: unresolved link {target}"


def test_markdown_audit_matches_machine_readable_audit_summary():
    report = json.loads(
        (DOCS / "STAGE_2_PART_B_HYDROLOGICAL_AUDIT.json").read_text(
            encoding="utf-8"
        )
    )
    markdown = (DOCS / "STAGE_2_PART_B_HYDROLOGICAL_AUDIT.md").read_text(
        encoding="utf-8"
    )
    assert len(report["files"]) == 2
    gate = json.loads(GATE.read_text(encoding="utf-8"))
    gate_by_filename = {
        Path(dataset["input_path"]).name: dataset["audit_summary"]
        for dataset in gate["datasets"]
    }

    for dataset in report["files"]:
        filename = Path(dataset["path"]).name
        assert filename in markdown
        assert f"{dataset['row_count']} / {dataset['station_count']}" in markdown
        assert dataset["timestamp_range"]["minimum"] in markdown
        assert dataset["timestamp_range"]["maximum"] in markdown

        summary = gate_by_filename[filename]
        assert summary["rows"] == dataset["row_count"]
        assert summary["station_identities_for_audit_only"] == dataset["station_count"]
        assert (
            summary["observed_timestamp_range_source_timezone_unknown"]["minimum"]
            == dataset["timestamp_range"]["minimum"]
        )
        assert (
            summary["observed_timestamp_range_source_timezone_unknown"]["maximum"]
            == dataset["timestamp_range"]["maximum"]
        )
        assert summary["exact_duplicate_rows"] == dataset["duplicate_checks"]["exact_duplicate_rows"]
        assert (
            summary["repeated_station_timestamp_records"]
            == dataset["duplicate_checks"]["duplicate_station_timestamp_records"]
        )
        assert (
            summary["repeated_station_timestamp_records_with_different_water_level"]
            == dataset["duplicate_checks"][
                "repeated_station_timestamp_records_with_different_water_level"
            ]
        )
        assert (
            summary["missing_water_level_values"]
            == dataset["missing_values"][
                "River Water Level Telemetry Hourly (meter)"
            ]["count"]
        )
        assert (
            summary["negative_water_level_values_requiring_provider_interpretation"]
            == dataset["numeric_checks"]["negative_water_levels"]
        )
        assert (
            summary["timestamp_order_regressions"]
            == dataset["timestamp_checks"][
                "records_not_in_source_chronological_order_within_station"
            ]
        )


def test_metadata_review_preserves_reported_conflicts_extremes_and_gaps():
    review = (DOCS / "STAGE_2_PART_B2_METADATA_PROVENANCE_REVIEW.md").read_text(
        encoding="utf-8"
    )
    expected_examples = (
        "185.015 vs 166.848",
        "271.339 vs 271.338",
        "-673.0",
        "2583.0",
        "-990.33",
        "1602.237",
        "2021-07-20 04:00 to 2024-07-22 23:00",
        "2021-11-03 08:00 to 2023-12-18 06:00",
    )
    assert all(example in review for example in expected_examples)


def test_evidence_plan_maps_every_gate_field_and_tracker_question():
    plan = json.loads(EVIDENCE_PLAN.read_text(encoding="utf-8"))
    gate = json.loads(GATE.read_text(encoding="utf-8"))
    tracker_questions = set(_tracker_rows())
    fields_by_name = {
        field["field"]: field
        for dataset in gate["datasets"]
        for field in dataset["fields"]
    }

    assert len(plan["field_mappings"]) == 15
    assert {item["field"] for item in plan["field_mappings"]} == set(fields_by_name)
    assert plan["question_mapping_review"]["unmapped_tracker_questions"] == []
    assert plan["question_mapping_review"]["unmapped_readiness_fields"] == []

    mapped_questions = set()
    for item in plan["field_mappings"]:
        assert item["dataset_scope"]
        assert item["evidence_required"]
        assert item["authoritative_source_expected"]
        assert item["validation_procedure"]
        assert item["reviewer_role"]
        assert item["acceptance_criteria"]
        assert item["unresolved_or_blocked_condition"]
        assert all(dependency in fields_by_name for dependency in item["dependencies"])
        assert fields_by_name[item["field"]]["status"] == "UNRESOLVED"
        assert item["evidence_state"] == {
            "evidence_requested": "PLANNED_NOT_SENT",
            "evidence_received": "NOT_RECORDED",
            "evidence_independently_checked": "NOT_CHECKED",
            "field_accepted": False,
        }
        assert item["tracker_question_numbers"]
        assert set(item["tracker_question_numbers"]) <= tracker_questions
        mapped_questions.update(item["tracker_question_numbers"])

    assert mapped_questions == tracker_questions
    assert plan["readiness_snapshot"]["normalization_gate_decision"] == "BLOCKED"
    assert plan["readiness_snapshot"]["normalization_may_proceed"] is False
    assert plan["readiness_snapshot"]["godavari_unresolved_fields"] == 15
    assert plan["readiness_snapshot"]["krishna_unresolved_fields"] == 15


def test_prioritized_evidence_sequence_preserves_acceptance_dependencies():
    plan = json.loads(EVIDENCE_PLAN.read_text(encoding="utf-8"))
    sequence = plan["prioritized_sequence"]

    assert [step["priority"] for step in sequence] == list(range(1, 6))
    assert sequence[0]["question_numbers"] == list(range(1, 25))
    assert "actually received" in sequence[1]["dependencies"][0]
    assert "stable station crosswalk accepted" in " ".join(
        sequence[3]["dependencies"]
    )
    assert "all field-specific authoritative evidence" in sequence[4]["dependencies"][0]


def test_evidence_plan_sources_and_question_mapping_are_explicit_and_unverified():
    plan = json.loads(EVIDENCE_PLAN.read_text(encoding="utf-8"))
    questions = _request_questions()
    source_review = plan["scope"]["source_authority_review"]

    assert source_review["status"] == "PROPOSED_SOURCES_NOT_INDEPENDENTLY_VERIFIED"
    assert source_review["contact_status"] == "UNVERIFIED"
    assert source_review["review_performed"] is False
    assert all(
        source["verification_status"] == "NOT_VERIFIED"
        and source["expected_responsible_authority"]
        and source["specific_artifact_sought"]
        for source in source_review["expected_authorities_and_artifacts"]
    )
    minimum_request_terms = {
        "source_resource_identity_and_export_completeness": (
            "resource",
            "version",
            "complete",
            "checksum",
        ),
        "stable_physical_gauge_id_and_station_crosswalk": (
            "stable",
            "gauge",
            "crosswalk",
            "history",
        ),
        "coordinates_crs_source_accuracy_and_location_history": (
            "coordinate",
            "accuracy",
            "reference system",
            "location",
        ),
        "administrative_codes_and_names": ("state", "district", "effective"),
        "river_basin_and_reach_assignment": ("river", "basin", "reach"),
        "Data_Acquisition_Time_semantics_timezone_and_clock_rules": (
            "Data Acquisition Time",
            "timezone",
            "daylight-saving",
        ),
        "water_level_quantity_unit_sign_and_negative_values": (
            "physical quantity",
            "unit",
            "sign convention",
            "negative",
        ),
        "RL_of_zeroGauge_and_MeanSeaLevel_definitions": (
            "RL_of_zeroGauge",
            "MeanSeaLevel",
            "zero",
        ),
        "vertical_datum_compatibility": ("vertical datum", "benchmark", "transformation"),
        "observation_quality_flags_and_status": ("QC", "quality flag", "sentinel"),
        "repeated_station_timestamp_and_revision_policy": (
            "repeated station/timestamp",
            "revision",
            "source rows",
        ),
        "station_operation_sampling_and_missingness": (
            "cadence",
            "outages",
            "operating",
            "absent timestamp",
        ),
        "Is_DischargeDataAvailable_semantics": (
            "Is_DischargeDataAvailable",
            "scope/time",
        ),
        "license_attribution_and_permitted_reuse": (
            "license",
            "attribution",
            "redistribution",
            "commercial",
        ),
        "source_water_level_unit_header_declaration": (
            "River Water Level Telemetry Hourly (meter)",
            "exact unit",
        ),
    }

    for mapping in plan["field_mappings"]:
        relevant_questions = " ".join(
            questions[number] for number in mapping["tracker_question_numbers"]
        ).casefold()
        for required_term in minimum_request_terms[mapping["field"]]:
            assert required_term.casefold() in relevant_questions, (
                mapping["field"],
                required_term,
                mapping["tracker_question_numbers"],
            )


def test_evidence_handling_distinguishes_source_claims_checks_and_acceptance():
    plan = json.loads(EVIDENCE_PLAN.read_text(encoding="utf-8"))
    scope = plan["scope"]
    preservation = " ".join(scope["evidence_preservation_procedure"]).casefold()
    assessment = scope["evidence_assessment_protocol"]

    assert "sha-256" in preservation
    assert "received date/time" in preservation
    assert "unchanged original" in preservation
    assert "transformation log" in preservation
    assert "do not commit" in preservation
    assert "record what the provider" in assessment["provider_statement"].casefold()
    assert "separate checks" in assessment["independent_verification"].casefold()
    assert "readiness gate" in assessment["internal_acceptance"].casefold()
    for condition in ("incomplete_evidence", "contradictory_evidence", "superseded_evidence", "limited_scope_evidence"):
        assert "UNRESOLVED" in assessment[condition]


def test_plan_has_human_pre_send_review_checklist():
    plan = json.loads(EVIDENCE_PLAN.read_text(encoding="utf-8"))
    scope = plan["scope"]
    checklist = scope["human_pre_send_checklist"]
    joined = " ".join(checklist).casefold()

    assert len(checklist) >= 5
    assert "verify the proposed email/contact" in joined
    assert "all 24 numbered questions" in joined
    assert "human" in joined and "approve" in joined
    gate = scope["request_send_gate"]
    assert gate["approval_status"] == "NOT_APPROVED"
    assert gate["approval_record"]["approver_name_or_role"] is None
    assert gate["approval_record"]["approval_date"] is None
    assert gate["approval_record"]["verified_contact_source"] is None
    required_action = gate["required_human_action"].casefold()
    assert "must personally review" in required_action
    assert "only that authorized human may then send it manually" in required_action


def test_evidence_intake_template_tracks_receipt_scope_and_separate_review_states():
    plan = json.loads(EVIDENCE_PLAN.read_text(encoding="utf-8"))
    scope = plan["scope"]
    template = scope["evidence_intake_record_template"]
    instructions = " ".join(scope["evidence_intake_instructions"]).casefold()

    required_keys = {
        "actual_received_date_time",
        "receipt_channel",
        "sender_identity_as_claimed",
        "sender_identity_verification_status",
        "sender_identity_verification_source_and_result",
        "exact_scope",
        "linked_tracker_question_numbers",
        "linked_readiness_fields",
        "sha256_if_appropriate",
        "original_preservation_location_or_restricted_reference",
        "derived_or_transformed_copies",
        "provider_statement_summary_and_citation",
        "independent_verification_checks_and_sources",
        "contradictions_missing_details_or_limitations",
        "supersedes_or_is_superseded_by",
        "review_decision",
        "readiness_gate_change_authorized",
    }
    assert required_keys <= template.keys()
    assert template["intake_status"] == "NOT_RECEIVED"
    assert template["sender_identity_verification_status"] == "NOT_VERIFIED"
    assert template["review_decision"] == "PENDING"
    assert template["readiness_gate_change_authorized"] is False
    assert "preserve the original attachment" in instructions
    assert "separately" in instructions
    assert "keep affected readiness fields unresolved" in instructions
