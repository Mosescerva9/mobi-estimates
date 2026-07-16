"""Canonical takeoff-evidence + provider-neutral interface tests (Milestone 2)."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.takeoff import (
    CANONICAL_EVIDENCE_SCHEMA_VERSION,
    EVIDENCE_CLASSES,
    NON_HUMAN_REVIEWED_EVIDENCE_CLASSES,
    AuthorizedThirdPartyProvider,
    CanonicalEvidence,
    CustomerSuppliedProvider,
    EvidenceClass,
    EvidenceQuarantineError,
    EvidenceReviewStatus,
    FutureCadBimProvider,
    FutureThirdPartyProvider,
    HumanVerifiedTakeoffProvider,
    ManualTakeoffImportProvider,
    MeasurementMethod,
    MobiNativeTakeoffProvider,
    OpenTakeoffProvider,
    TakeoffContext,
    TakeoffProviderKind,
)


def _evidence(**over):
    data = dict(
        tenant_id=uuid4(),
        company_id=uuid4(),
        project_id=uuid4(),
        document_id=uuid4(),
        sheet_id=uuid4(),
        page_number=1,
        takeoff_provider=TakeoffProviderKind.MANUAL_IMPORT,
        provider_record_id="rec-1",
        evidence_class=EvidenceClass.MEASURED,
        measurement_method=MeasurementMethod.MANUAL_ENTRY,
        trade="painting",
        scope_category="interior_walls",
        description="Paint walls",
        extractor_version="1.0.0",
    )
    data.update(over)
    return CanonicalEvidence(**data)


def _context(**over):
    data = dict(
        tenant_id=uuid4(),
        company_id=uuid4(),
        project_id=uuid4(),
        document_id=uuid4(),
        sheet_id=uuid4(),
        extractor_version="1.0.0",
    )
    data.update(over)
    return TakeoffContext(**data)


def _payload(**over):
    data = dict(
        provider_record_id="rec-1",
        page_number=1,
        trade="painting",
        scope_category="interior_walls",
        description="Paint walls",
        quantity=Decimal("100"),
        unit="SF",
        confidence=Decimal("0.9"),
    )
    data.update(over)
    return data


# ---------------------------------------------------------------------------
# Canonical evidence schema
# ---------------------------------------------------------------------------
def test_valid_measured_evidence():
    ev = _evidence(quantity=Decimal("100"), unit="SF", confidence=Decimal("0.8"))
    assert ev.schema_version == CANONICAL_EVIDENCE_SCHEMA_VERSION
    assert ev.review_status == EvidenceReviewStatus.PENDING.value
    assert ev.evidence_class == EvidenceClass.MEASURED.value
    assert ev.is_human_reviewed is False


def test_valid_human_verified_evidence():
    ev = _evidence(
        takeoff_provider=TakeoffProviderKind.HUMAN_VERIFIED,
        evidence_class=EvidenceClass.HUMAN_VERIFIED,
        measurement_method=MeasurementMethod.DIGITAL_MEASUREMENT,
        review_status=EvidenceReviewStatus.APPROVED,
        reviewed_by="estimator-7",
    )
    assert ev.is_human_reviewed is True


def test_valid_mobi_native_model_candidate_evidence():
    ev = _evidence(
        takeoff_provider=TakeoffProviderKind.MOBI_NATIVE,
        evidence_class=EvidenceClass.MODEL_CANDIDATE,
        measurement_method=MeasurementMethod.MODEL_INFERENCE,
    )
    assert ev.evidence_class == EvidenceClass.MODEL_CANDIDATE.value
    assert ev.is_human_reviewed is False


def test_unknown_schema_version_rejected():
    with pytest.raises(ValidationError):
        _evidence(schema_version="unexpected_v9")


def test_unknown_evidence_field_rejected():
    with pytest.raises(ValidationError):
        _evidence(surprise="boom")


def test_unknown_evidence_class_rejected():
    with pytest.raises(ValidationError):
        _evidence(evidence_class="totally_made_up")


def test_unsupported_unit_rejected():
    with pytest.raises(ValidationError):
        _evidence(quantity=Decimal("1"), unit="WIDGETS")


def test_confidence_bounds_enforced():
    with pytest.raises(ValidationError):
        _evidence(confidence=Decimal("1.5"))


def test_page_number_must_be_positive():
    with pytest.raises(ValidationError):
        _evidence(page_number=0)


@pytest.mark.parametrize(
    "evidence_class",
    [EvidenceClass.UNSUPPORTED, EvidenceClass.TEST_FIXTURE, EvidenceClass.MODEL_CANDIDATE],
)
def test_non_review_classes_valid_but_not_human_reviewed(evidence_class):
    ev = _evidence(evidence_class=evidence_class)
    assert ev.evidence_class == evidence_class.value
    assert evidence_class in EVIDENCE_CLASSES
    assert evidence_class in NON_HUMAN_REVIEWED_EVIDENCE_CLASSES
    # Valid evidence, but never human-reviewed just because it validated.
    assert ev.is_human_reviewed is False


def test_all_required_classes_present():
    expected = {
        "measured",
        "formula_derived",
        "schedule_extracted",
        "specification_extracted",
        "customer_supplied",
        "human_verified",
        "vendor_quote",
        "cost_book",
        "allowance",
        "model_candidate",
        "test_fixture",
        "unsupported",
    }
    assert {c.value for c in EVIDENCE_CLASSES} == expected


# ---------------------------------------------------------------------------
# Provider interface
# ---------------------------------------------------------------------------
def test_manual_provider_normalizes_mapped_payload():
    provider = ManualTakeoffImportProvider()
    ctx = _context()
    ev = provider.normalize(_payload(), context=ctx)
    assert isinstance(ev, CanonicalEvidence)
    assert ev.takeoff_provider == TakeoffProviderKind.MANUAL_IMPORT.value
    assert ev.evidence_class == EvidenceClass.MEASURED.value
    assert ev.tenant_id == ctx.tenant_id
    assert ev.project_id == ctx.project_id
    assert ev.quantity == Decimal("100")
    # Provider payloads cannot claim tenancy/lineage; the context owns it.
    assert ev.extractor_version == "1.0.0"


def test_mobi_native_provider_defaults_to_model_candidate():
    provider = MobiNativeTakeoffProvider()
    ev = provider.normalize(_payload(), context=_context())
    assert ev.evidence_class == EvidenceClass.MODEL_CANDIDATE.value
    assert ev.is_human_reviewed is False


def test_human_verified_provider_shell():
    provider = HumanVerifiedTakeoffProvider()
    ev = provider.normalize(
        _payload(review_status="approved", reviewed_by="estimator-7"),
        context=_context(),
    )
    assert ev.takeoff_provider == TakeoffProviderKind.HUMAN_VERIFIED.value
    assert ev.is_human_reviewed is True


def test_future_cad_bim_provider_is_unsupported():
    provider = FutureCadBimProvider()
    ev = provider.normalize(_payload(), context=_context())
    assert ev.evidence_class == EvidenceClass.UNSUPPORTED.value


def test_open_takeoff_provider_normalizes_measured_digital_payload():
    provider = OpenTakeoffProvider()
    ctx = _context()
    ev = provider.normalize(
        _payload(condition="8ft interior walls", scale='1/4" = 1\''),
        context=ctx,
    )
    assert ev.takeoff_provider == TakeoffProviderKind.OPEN_TAKEOFF.value
    assert ev.evidence_class == EvidenceClass.MEASURED.value
    assert ev.measurement_method == MeasurementMethod.DIGITAL_MEASUREMENT.value
    # Takeoff-tool provenance fields round-trip through the canonical schema.
    assert ev.condition == "8ft interior walls"
    assert ev.scale == '1/4" = 1\''
    assert ev.is_human_reviewed is False


def test_customer_supplied_provider_normalizes_customer_declaration():
    provider = CustomerSuppliedProvider()
    ev = provider.normalize(_payload(), context=_context())
    assert ev.takeoff_provider == TakeoffProviderKind.CUSTOMER_SUPPLIED.value
    assert ev.evidence_class == EvidenceClass.CUSTOMER_SUPPLIED.value
    assert ev.measurement_method == MeasurementMethod.CUSTOMER_DECLARATION.value
    # Customer-supplied quantities are never human-reviewed just by validating.
    assert ev.is_human_reviewed is False


def test_future_third_party_provider_defaults_to_unsupported():
    provider = FutureThirdPartyProvider()
    ev = provider.normalize(_payload(), context=_context())
    assert ev.takeoff_provider == TakeoffProviderKind.FUTURE_THIRD_PARTY.value
    # Exists as a lane, but unsupported until an adapter is explicitly implemented.
    assert ev.evidence_class == EvidenceClass.UNSUPPORTED.value
    assert ev.measurement_method == MeasurementMethod.NONE.value


def test_condition_and_scale_are_optional():
    # Providers that cannot express takeoff-tool provenance simply omit them.
    ev = _evidence()
    assert ev.condition is None
    assert ev.scale is None


def test_provider_still_quarantines_unknown_field_alongside_condition_scale():
    provider = OpenTakeoffProvider()
    with pytest.raises(EvidenceQuarantineError) as excinfo:
        # condition/scale are mapped; "layer" is not — the whole payload quarantines.
        provider.normalize(
            _payload(condition="walls", scale="1:50", layer="A-WALL"),
            context=_context(),
        )
    assert excinfo.value.reason_code == "unknown_payload_fields"


def test_provider_rejects_unknown_payload_field():
    provider = AuthorizedThirdPartyProvider()
    with pytest.raises(EvidenceQuarantineError) as excinfo:
        # "qty" is not "quantity"; we do not synonym-map it, we quarantine.
        provider.normalize({**_payload(), "qty": 5}, context=_context())
    assert excinfo.value.reason_code == "unknown_payload_fields"


def test_provider_quarantines_invalid_canonical_value():
    provider = ManualTakeoffImportProvider()
    with pytest.raises(EvidenceQuarantineError) as excinfo:
        provider.normalize(_payload(unit="WIDGETS"), context=_context())
    assert excinfo.value.reason_code == "canonical_validation_failed"


def test_provider_rejects_non_mapping_payload():
    provider = ManualTakeoffImportProvider()
    with pytest.raises(EvidenceQuarantineError) as excinfo:
        provider.normalize(["not", "a", "dict"], context=_context())
    assert excinfo.value.reason_code == "malformed_payload"


def test_batch_normalization_splits_good_and_quarantined():
    provider = MobiNativeTakeoffProvider()
    ctx = _context()
    result = provider.normalize_batch(
        [
            _payload(provider_record_id="rec-1"),
            {**_payload(provider_record_id="rec-2"), "qty": 5},  # unknown field
            _payload(provider_record_id="rec-3", unit="WIDGETS"),  # bad unit
        ],
        context=ctx,
    )
    assert result.provider == TakeoffProviderKind.MOBI_NATIVE
    assert len(result.evidence) == 1
    assert result.evidence[0].provider_record_id == "rec-1"
    assert len(result.quarantined) == 2
    assert result.ok is False
    reason_codes = {q.reason_code for q in result.quarantined}
    assert reason_codes == {"unknown_payload_fields", "canonical_validation_failed"}
