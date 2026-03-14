from datetime import timezone

from henk.requirements import Requirements, RequirementsStatus


def test_requirements_status_flow():
    req = Requirements(task_description="Schrijf iets")
    assert req.status == RequirementsStatus.DRAFT

    req.confirm()
    assert req.status == RequirementsStatus.CONFIRMED

    req.start_execution()
    assert req.status == RequirementsStatus.EXECUTING

    req.complete("klaar")
    assert req.status == RequirementsStatus.EVALUATED
    assert req.result == "klaar"


def test_requirements_add_spec_only_allowed_states():
    req = Requirements(task_description="Doe taak")
    req.add_specification("kort")
    req.confirm()
    req.add_specification("Nederlands")
    assert "kort" in req.specifications
    assert "Nederlands" in req.specifications

    req.start_execution()
    before = req.specifications
    req.add_specification("extra")
    assert req.specifications == before


def test_requirements_fail_sets_evaluated():
    req = Requirements(task_description="Taak")
    req.fail("kapot")
    assert req.status == RequirementsStatus.EVALUATED
    assert req.result == "Mislukt: kapot"


def test_requirements_timestamps_are_timezone_aware():
    """created_at, confirmed_at en completed_at moeten altijd timezone-aware zijn."""
    req = Requirements(task_description="Taak")
    assert req.created_at.tzinfo is not None

    req.confirm()
    assert req.confirmed_at is not None
    assert req.confirmed_at.tzinfo is not None

    req.start_execution()
    req.complete("klaar")
    assert req.completed_at is not None
    assert req.completed_at.tzinfo is not None


def test_requirements_fail_timestamp_is_timezone_aware():
    req = Requirements(task_description="Taak")
    req.fail("reden")
    assert req.completed_at is not None
    assert req.completed_at.tzinfo is not None


def test_requirements_timestamps_are_utc():
    """Alle timestamps moeten UTC zijn zodat vergelijkingen met staging werken."""
    req = Requirements(task_description="Taak")
    req.confirm()
    req.complete("ok")
    assert req.created_at.tzinfo == timezone.utc
    assert req.confirmed_at.tzinfo == timezone.utc
    assert req.completed_at.tzinfo == timezone.utc
