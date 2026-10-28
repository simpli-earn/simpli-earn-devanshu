import pytest

from simpliearn_pipeline.config import check_settings, load_settings, validate_settings


def test_defaults_are_local_and_valid():
    settings = load_settings({})
    errors, warnings = check_settings(settings)
    assert settings.blob_backend == "local"
    assert errors == []
    assert warnings  # database url missing


def test_gcs_requires_bucket_and_db_url_must_be_postgres():
    settings = load_settings({"PIPELINE_BLOB_BACKEND": "gcs", "PIPELINE_DATABASE_URL": "mysql://u:p@h/db"})
    errors, _ = check_settings(settings)
    assert any("PIPELINE_GCS_BUCKET" in e for e in errors)
    assert any("postgres" in e for e in errors)


def test_strict_mode_raises_but_never_leaks_the_password():
    env = {
        "PIPELINE_BLOB_BACKEND": "bogus",
        "STRICT_CONFIG": "1",
        "PIPELINE_DATABASE_URL": "postgres://u:secretpw@h/db",
    }
    settings = load_settings(env)
    assert "secretpw" not in repr(settings)
    with pytest.raises(RuntimeError) as exc:
        validate_settings(settings)
    assert "secretpw" not in str(exc.value)


def test_non_strict_mode_only_prints(capsys):
    validate_settings(load_settings({"PIPELINE_BLOB_BACKEND": "bogus"}))
    assert "PIPELINE_BLOB_BACKEND" in capsys.readouterr().out
