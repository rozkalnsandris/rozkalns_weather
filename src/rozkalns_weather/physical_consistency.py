from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterable

if TYPE_CHECKING:
    from .models import ForecastRun

PHYSICAL_CONSISTENCY_VERSION = "forecast-physical-v1"

DEWPOINT_TOLERANCE_DEGC = 0.5
GUST_TOLERANCE_MS = 0.5
BOUND_TOLERANCE_PERCENT = 0.5
NONNEGATIVE_TOLERANCE = 0.05

BOUNDED_PERCENT_VARIABLES = frozenset(
    {"relative_humidity_2m", "cloud_cover", "precipitation_probability_1h"}
)
NONNEGATIVE_VARIABLES = frozenset(
    {"precipitation_1h", "wind_speed_10m", "wind_gust_10m"}
)


@dataclass(frozen=True, slots=True)
class PhysicalIdentity:
    provider: str
    model_name: str
    model_version: str | None
    init_time_utc: str
    valid_time_utc: str
    lead_hours: float
    statistic: str
    location_id: str

    def as_dict(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "model_name": self.model_name,
            "model_version": self.model_version,
            "init_time_utc": self.init_time_utc,
            "valid_time_utc": self.valid_time_utc,
            "lead_hours": self.lead_hours,
            "statistic": self.statistic,
            "location_id": self.location_id,
        }


@dataclass(frozen=True, slots=True)
class PhysicalSample:
    identity: PhysicalIdentity
    variable: str
    value: float


@dataclass(frozen=True, slots=True)
class PhysicalFinding:
    severity: str
    reason_code: str
    variables: tuple[str, ...]
    identity: PhysicalIdentity
    values: tuple[tuple[str, float], ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "severity": self.severity,
            "reason_code": self.reason_code,
            "variables": list(self.variables),
            "identity": self.identity.as_dict(),
            "values": {name: value for name, value in self.values},
        }


@dataclass(frozen=True, slots=True)
class PhysicalConsistencyReport:
    state: str
    findings: tuple[PhysicalFinding, ...]

    @property
    def reason_codes(self) -> tuple[str, ...]:
        return tuple(sorted({item.reason_code for item in self.findings}))

    @property
    def blocked_reason_codes(self) -> tuple[str, ...]:
        return tuple(
            sorted({item.reason_code for item in self.findings if item.severity == "BLOCKED"})
        )

    def to_metadata(self) -> dict[str, object]:
        return {
            "contract_version": PHYSICAL_CONSISTENCY_VERSION,
            "state": self.state,
            "reason_codes": list(self.reason_codes),
            "blocked_reason_codes": list(self.blocked_reason_codes),
            "finding_count": len(self.findings),
            "findings": [item.as_dict() for item in self.findings],
        }


class PhysicalConsistencyError(ValueError):
    """A forecast run contains a blocking physical contradiction."""

    def __init__(self, report: PhysicalConsistencyReport) -> None:
        self.report = report
        self.reason_codes = report.blocked_reason_codes or report.reason_codes
        super().__init__(
            "physical_consistency_blocked:"
            + (",".join(self.reason_codes) if self.reason_codes else "unknown")
        )


def _utc_string(value) -> str:
    return value.isoformat().replace("+00:00", "Z")


def forecast_run_samples(run: ForecastRun) -> tuple[PhysicalSample, ...]:
    init_time = _utc_string(run.init_time_utc)
    return tuple(
        PhysicalSample(
            identity=PhysicalIdentity(
                provider=run.provider,
                model_name=run.model_name,
                model_version=run.model_version,
                init_time_utc=init_time,
                valid_time_utc=_utc_string(value.valid_time_utc),
                lead_hours=float(value.lead_hours),
                statistic=value.statistic,
                location_id="forecast_run",
            ),
            variable=value.variable,
            value=float(value.value),
        )
        for value in run.values
    )


def _severity(delta: float, tolerance: float) -> str:
    return "SUSPECT" if delta <= tolerance else "BLOCKED"


def _cross_reason(base: str, severity: str) -> str:
    return f"{base}_TOLERANCE" if severity == "SUSPECT" else base


def report_physical_consistency(
    samples: Iterable[PhysicalSample],
) -> PhysicalConsistencyReport:
    items = tuple(samples)
    findings: list[PhysicalFinding] = []

    for sample in items:
        if sample.variable in BOUNDED_PERCENT_VARIABLES and not 0.0 <= sample.value <= 100.0:
            distance = -sample.value if sample.value < 0.0 else sample.value - 100.0
            severity = _severity(distance, BOUND_TOLERANCE_PERCENT)
            findings.append(
                PhysicalFinding(
                    severity=severity,
                    reason_code=_cross_reason("BOUNDED_FIELD_OUT_OF_RANGE", severity),
                    variables=(sample.variable,),
                    identity=sample.identity,
                    values=((sample.variable, sample.value),),
                )
            )

        if sample.variable in NONNEGATIVE_VARIABLES and sample.value < 0.0:
            severity = _severity(abs(sample.value), NONNEGATIVE_TOLERANCE)
            findings.append(
                PhysicalFinding(
                    severity=severity,
                    reason_code=_cross_reason("NEGATIVE_MAGNITUDE", severity),
                    variables=(sample.variable,),
                    identity=sample.identity,
                    values=((sample.variable, sample.value),),
                )
            )

    by_identity: dict[PhysicalIdentity, dict[str, PhysicalSample]] = {}
    for sample in items:
        by_identity.setdefault(sample.identity, {})[sample.variable] = sample

    for values in by_identity.values():
        temperature = values.get("temperature_2m")
        dew_point = values.get("dew_point_2m")
        if temperature is not None and dew_point is not None:
            excess = dew_point.value - temperature.value
            if excess > 0.0:
                severity = _severity(excess, DEWPOINT_TOLERANCE_DEGC)
                findings.append(
                    PhysicalFinding(
                        severity=severity,
                        reason_code=_cross_reason(
                            "DEWPOINT_ABOVE_TEMPERATURE", severity
                        ),
                        variables=("dew_point_2m", "temperature_2m"),
                        identity=dew_point.identity,
                        values=(
                            ("dew_point_2m", dew_point.value),
                            ("temperature_2m", temperature.value),
                        ),
                    )
                )

        wind = values.get("wind_speed_10m")
        gust = values.get("wind_gust_10m")
        if wind is not None and gust is not None:
            deficit = wind.value - gust.value
            if deficit > 0.0:
                severity = _severity(deficit, GUST_TOLERANCE_MS)
                findings.append(
                    PhysicalFinding(
                        severity=severity,
                        reason_code=_cross_reason(
                            "GUST_BELOW_SUSTAINED_WIND", severity
                        ),
                        variables=("wind_gust_10m", "wind_speed_10m"),
                        identity=gust.identity,
                        values=(
                            ("wind_gust_10m", gust.value),
                            ("wind_speed_10m", wind.value),
                        ),
                    )
                )

    if any(item.severity == "BLOCKED" for item in findings):
        state = "BLOCKED"
    elif findings:
        state = "SUSPECT"
    else:
        state = "PASS"
    return PhysicalConsistencyReport(state=state, findings=tuple(findings))


def validate_forecast_run(run: ForecastRun) -> PhysicalConsistencyReport:
    return report_physical_consistency(forecast_run_samples(run))


def enforce_forecast_run_physical_consistency(
    run: ForecastRun,
) -> PhysicalConsistencyReport:
    report = validate_forecast_run(run)
    if report.state == "BLOCKED":
        raise PhysicalConsistencyError(report)
    return report
