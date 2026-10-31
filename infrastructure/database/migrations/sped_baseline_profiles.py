"""Per-vintage source profiles for the SPED baseline (#999 / #1000 / #1001).

Data, not code: each baseline vintage names its files (sha256-pinned), the label vocabulary those
files spell, and the year cell their rows carry. The pure parsers in import_sped_baseline consume a
profile, so a new vintage is a new entry here — never a per-vintage code fork.

A baseline vintage is a SET of components whose own data years differ (the 2024-25 set pairs 2023-24
personnel with the 2024-25 child count); `baseline_year` names the set, and each SourceFile carries
its component's real year, which is what lands in the baseline rows' *_year columns.

Plan + findings: docs/technical-notes/production-quality-control-research/
2026-10-31-idea-crdc-sped-baseline-refresh-plan.md
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Optional

from infrastructure.utilities.data_guards import DataGuardError

FEDERAL_DIR = Path(__file__).resolve().parents[3] / "data" / "raw" / "federal"


@dataclass(frozen=True)
class SourceFile:
    relpath: str        # under data/raw/federal
    sha256: str         # pinned: ED revises files in place, so a changed file must be a deliberate re-pin
    data_year: str      # the school year this file's data describe

    @property
    def path(self) -> Path:
        return FEDERAL_DIR / self.relpath


@dataclass(frozen=True)
class PersonnelProfile:
    source: SourceFile
    year_cell: str      # the file's `Year` cell for the wanted data year ('2017' / '2023-2024')
    teacher_type: str
    para_type: str


@dataclass(frozen=True)
class ChildCountProfile:
    source: SourceFile
    year_cell: str
    school_age_total_row: str
    early_childhood_total_row: str
    early_childhood_col: str
    school_age_cols: Mapping[str, str]          # band ('6-21' / '5-21') -> the column that counts it
    age_5_school_age_col: Optional[str]         # kindergarten 5-year-olds (in School Age since 2020-21)
    self_contained: frozenset[str]
    mainstreamed: frozenset[str]
    other: frozenset[str]                       # excluded by name; the vocabulary is CLOSED (#982)

    @property
    def known_environments(self) -> frozenset[str]:
        return (self.self_contained | self.mainstreamed | self.other
                | {self.school_age_total_row, self.early_childhood_total_row})


@dataclass(frozen=True)
class BaselineProfile:
    baseline_year: str
    personnel: PersonnelProfile
    child_count: ChildCountProfile
    crdc: SourceFile
    ccd: SourceFile
    # Which school_age_cols band the stored counts and ratios use. None = not yet decided, and the
    # importer refuses to WRITE the vintage (it can still be parsed and measured) — for 2024-25 this
    # is one of the three T5 calls on #1003 (School Age 5-21 vs 6-21).
    school_age_band: Optional[str] = None
    notes: tuple[str, ...] = field(default=())


# Environments both vintages spell identically.
_MAINSTREAMED = frozenset({
    'Inside regular class 80% or more of the day',
    'Inside regular class 40% through 79% of the day',
})
_LESS_THAN_40 = 'Inside regular class less than 40% of the day'
_SHARED_OTHER = frozenset({
    'Correctional Facilities', 'Home', 'Homebound/Hospital', 'Parentally Placed in Private Schools',
    'Separate Class', 'Service Provider Location',
    'Services in Other Location than Regular Early Childhood Program (attend at least 10 hours)',
    'Services in Other Location than Regular Early Childhood Program (attend less than 10 hours)',
    'Services in Regular Early Childhood Program (attend at least 10 hours)',
    'Services in Regular Early Childhood Program (attend less than 10 hours)',
})

PROFILE_2017_18 = BaselineProfile(
    baseline_year="2017-18",
    personnel=PersonnelProfile(
        source=SourceFile("idea-618/2017_18/bpersonnel2017-18.csv",
                          "ddb0fb7c3b7163064dab5c3a8054a53cc1ae1c5e54e5b9cd49c04d7469fb5523", "2017-18"),
        year_cell="2017",
        teacher_type='Special Education Teachers for Ages 6-21',
        para_type='Special Education Paraprofessionals for Ages 6-21',
    ),
    child_count=ChildCountProfile(
        source=SourceFile("idea-618/2017_18/bchildcountandedenvironments2017-18.csv",
                          "e2a3ba581b7f2dc322ad41f60ff4e3be1dd5218e865116f6c84e803c84c51645", "2017-18"),
        year_cell="2017",
        school_age_total_row='Total, Age 6-21',
        early_childhood_total_row='Total, Age 3-5',
        early_childhood_col='Age 3 to 5',
        school_age_cols={'6-21': 'Ages 6-21'},
        age_5_school_age_col=None,
        # 'Separate School, Age 6-21' — not 'Separate School'; 'Separate Class' is an ages-3-5 setting (#970)
        self_contained=frozenset({_LESS_THAN_40, 'Separate School, Age 6-21'}),
        mainstreamed=_MAINSTREAMED,
        other=_SHARED_OTHER | {'Residential Facility, Age 3-5', 'Residential Facility, Age 6-21',
                               'Separate School, Age 3-5'},
    ),
    crdc=SourceFile("crdc/2017_18/Enrollment.csv",
                    "7a62a3b6634e1b2c375c4af1866317b6949bb3612bf912ec31f638dfe5adab76", "2017-18"),
    ccd=SourceFile("nces-ccd/2017_18/ccd_lea_052_1718_l_1a_083118.csv",
                   "2b604b0683d1fd2e28a1d03ce29f1aef31bd5ce120f721ac03f992f990c1d207", "2017-18"),
    school_age_band='6-21',
)

# The refresh set (#1000/#1001). ED relabelled 'Ages 6-21' → 'School Age' and, since the 2020-21
# collection, counts kindergarten 5-year-olds as school age (FS002/FS5003). Measured 2026-10-31: the
# 2024-25 child count STILL carries an 'Ages 6-21' column beside 'Age 5 (School Age)-21', both
# reconciling per state against 'Total, School Age' — so either band can be read. The 2023-24
# personnel file has no 6-21 split: its 'School Age' FTE serve 5-21. No 2024-25 personnel is published.
PROFILE_2024_25 = BaselineProfile(
    baseline_year="2024-25",
    personnel=PersonnelProfile(
        source=SourceFile("idea-618/2023_24/bpersonnel2023-24.csv",
                          "6614b2bb5d46a6f56bed5ef0c44f52ff11131060957bfd2f11b8f648a3c3c598", "2023-24"),
        year_cell="2023-2024",
        teacher_type='Special Education Teachers for School Age',
        para_type='Special Education Paraprofessionals for School Age',
    ),
    child_count=ChildCountProfile(
        source=SourceFile("idea-618/2024_25/bchildcountandedenvironment2024-25.csv",
                          "d77789297b594b20dd93561338fd09cbe68d6c6a4c5fa01b4d4142eb6d151f52", "2024-25"),
        year_cell="2024",
        school_age_total_row='Total, School Age',
        early_childhood_total_row='Total, Early Childhood',
        early_childhood_col='Age 3 to 5 (Early Childhood)',
        school_age_cols={'6-21': 'Ages 6-21', '5-21': 'Age 5 (School Age)-21'},
        age_5_school_age_col='Age 5 (School Age)',
        self_contained=frozenset({_LESS_THAN_40, 'Separate School, School Age'}),
        mainstreamed=_MAINSTREAMED,
        other=_SHARED_OTHER | {'Residential Facility, Early Childhood', 'Residential Facility, School Age',
                               'Separate School, Early Childhood'},
    ),
    crdc=SourceFile("crdc/2023_24/Enrollment.csv",
                    "81a210e4781ba7d86c96c4ec09c6ff8f26832367688da4c2341fd37787db317e", "2023-24"),
    # The CRDC denominator is paired with CCD membership of the CRDC's OWN year, never another (#1001).
    ccd=SourceFile("nces-ccd/2023_24/ccd_lea_052_2324_l_1a_073124.csv",
                   "b488e173764ea27a46dda2ff8e407d28058fd2e3c5c3ed56c32e0e4074ea1184", "2023-24"),
    school_age_band=None,
)

PROFILES: Mapping[str, BaselineProfile] = {p.baseline_year: p for p in (PROFILE_2017_18, PROFILE_2024_25)}


def get_profile(baseline_year: str) -> BaselineProfile:
    try:
        return PROFILES[baseline_year]
    except KeyError:
        raise DataGuardError(f"no SPED baseline profile for {baseline_year!r}; known: {sorted(PROFILES)}") from None


_SOURCE_MD_ROW = re.compile(r"^\|\s*(?:[^|]*/)?(?P<name>[^|/]+?)\s*\|\s*(?P<sha>[0-9a-f]{64})\s*\|", re.M)


def verify_source(src: SourceFile) -> None:
    """Refuse a file whose bytes are not the pinned ones. Where the folder carries a SOURCE.md that
    lists the file, the pin must also equal SOURCE.md's — so the download receipt and the code can
    never silently disagree about which bytes were reviewed."""
    path = src.path
    if not path.exists():
        raise DataGuardError(f"SPED baseline source missing: {path}")
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    actual = h.hexdigest()
    if actual != src.sha256:
        raise DataGuardError(f"{src.relpath}: sha256 {actual} != pinned {src.sha256} — the file changed "
                             f"(ED revises in place); re-pin deliberately after re-reviewing it")
    source_md = path.parent / "SOURCE.md"
    if source_md.exists():
        listed = {m["name"]: m["sha"] for m in _SOURCE_MD_ROW.finditer(source_md.read_text())}
        if path.name in listed and listed[path.name] != src.sha256:
            raise DataGuardError(f"{src.relpath}: pinned sha256 differs from {source_md} "
                                 f"({listed[path.name]}) — the receipt and the code disagree")
