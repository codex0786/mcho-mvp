from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

LicenseStatus = Literal[
    "unreviewed", "approved", "public_domain", "open_license", "licensed", "restricted", "blocked"
]
APPROVED_LICENSE_STATUSES = {"approved", "public_domain", "open_license", "licensed"}


class SourceCreateIn(BaseModel):
    name: str = Field(min_length=3, max_length=240)
    source_type: str = Field(pattern=r"^[a-z][a-z0-9_]{1,59}$")
    access_mode: str = Field(default="public_api", max_length=60)
    homepage_url: HttpUrl | None = None
    license_terms_url: HttpUrl | None = None
    owner_name: str | None = Field(default=None, max_length=240)
    retention_policy: str | None = Field(default=None, max_length=2000)
    refresh_cadence: str = Field(default="manual", max_length=80)

    @field_validator("license_terms_url")
    @classmethod
    def terms_url_must_use_https(cls, value):
        if value is not None and value.scheme != "https":
            raise ValueError("License terms URL must use HTTPS.")
        return value


class SourcePatchIn(BaseModel):
    access_mode: str | None = Field(default=None, max_length=60)
    homepage_url: HttpUrl | None = None
    license_terms_url: HttpUrl | None = None
    owner_name: str | None = Field(default=None, max_length=240)
    retention_policy: str | None = Field(default=None, max_length=2000)
    refresh_cadence: str | None = Field(default=None, max_length=80)
    license_status: LicenseStatus | None = None
    active: bool | None = None

    @field_validator("license_terms_url")
    @classmethod
    def terms_url_must_use_https(cls, value):
        if value is not None and value.scheme != "https":
            raise ValueError("License terms URL must use HTTPS.")
        return value

    @field_validator("license_status")
    @classmethod
    def license_status_cannot_be_null(cls, value):
        if value is None:
            raise ValueError("license_status cannot be null; use an explicit review status.")
        return value

    @field_validator("active", "access_mode", "refresh_cadence")
    @classmethod
    def non_nullable_fields_cannot_be_null(cls, value):
        if value is None:
            raise ValueError("This field cannot be null; omit it to leave the value unchanged.")
        return value


class SourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    source_type: str
    access_mode: str
    license_status: str
    homepage_url: str | None
    license_terms_url: str | None
    owner_name: str | None
    retention_policy: str | None
    refresh_cadence: str
    terms_reviewed_at: str | None = None
    terms_reviewed_by: str | None = None
    active: bool
