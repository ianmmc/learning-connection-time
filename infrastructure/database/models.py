# infrastructure/database/models.py
"""
SQLAlchemy ORM models for Learning Connection Time project.

These models map to the PostgreSQL tables defined in schema.sql.
They provide Pythonic access to database records with validation and relationships.
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Enum as SQLAlchemyEnum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, validates


class CalculationMode(str, Enum):
    """
    Calculation mode for LCT runs.

    BLENDED: Use most recent available data within REQ-026 3-year window.
             No specific year anchor - picks best available data per district.

    TARGET_YEAR: Enrollment anchored to target year, staff and bell schedule
                 data can come from within REQ-026 3-year window.
    """
    BLENDED = 'blended'
    TARGET_YEAR = 'target_year'


class Base(DeclarativeBase):
    """Base class for all models."""
    pass


class District(Base):
    """
    School district from NCES Common Core of Data.

    Represents a single school district with enrollment and staffing data.
    Primary source is the NCES CCD directory file.
    """
    __tablename__ = "districts"

    # Primary key
    nces_id: Mapped[str] = mapped_column(String(10), primary_key=True)

    # Core fields
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    state: Mapped[str] = mapped_column(String(2), nullable=False)
    st_leaid: Mapped[Optional[str]] = mapped_column(String(20))  # State-assigned LEA ID (e.g., "CA-6275796")
    enrollment: Mapped[Optional[int]] = mapped_column(Integer)
    instructional_staff: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    total_staff: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    schools_count: Mapped[Optional[int]] = mapped_column(Integer)
    year: Mapped[str] = mapped_column(String(10), nullable=False)
    data_source: Mapped[str] = mapped_column(String(50), default="nces_ccd")

    # Classification flags
    is_career_technical_center: Mapped[bool] = mapped_column(Boolean, default=False)
    is_shared_service_entity: Mapped[bool] = mapped_column(Boolean, default=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    bell_schedules: Mapped[List["BellSchedule"]] = relationship(
        back_populates="district", cascade="all, delete-orphan"
    )
    lct_calculations: Mapped[List["LCTCalculation"]] = relationship(
        back_populates="district", cascade="all, delete-orphan"
    )
    staff_counts: Mapped[List["StaffCounts"]] = relationship(
        back_populates="district", cascade="all, delete-orphan"
    )
    staff_counts_effective: Mapped[Optional["StaffCountsEffective"]] = relationship(
        back_populates="district", cascade="all, delete-orphan", uselist=False
    )
    enrollment_by_grade: Mapped[List["EnrollmentByGrade"]] = relationship(
        back_populates="district", cascade="all, delete-orphan"
    )

    # Layer 2: State-level enhancements
    ca_sped_environments: Mapped[List["CASpedDistrictEnvironments"]] = relationship(
        back_populates="district", cascade="all, delete-orphan"
    )
    socioeconomic_data: Mapped[List["DistrictSocioeconomic"]] = relationship(
        back_populates="district", cascade="all, delete-orphan"
    )
    funding_data: Mapped[List["DistrictFunding"]] = relationship(
        back_populates="district", cascade="all, delete-orphan"
    )
    ca_lcff_funding: Mapped[List["CALCFFFunding"]] = relationship(
        back_populates="district", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<District {self.nces_id}: {self.name} ({self.state})>"

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON export."""
        return {
            "nces_id": self.nces_id,
            "name": self.name,
            "state": self.state,
            "enrollment": self.enrollment,
            "instructional_staff": float(self.instructional_staff) if self.instructional_staff else None,
            "total_staff": float(self.total_staff) if self.total_staff else None,
            "schools_count": self.schools_count,
            "year": self.year,
            "data_source": self.data_source,
        }


class StateRequirement(Base):
    """
    State statutory requirements for instructional time.

    Contains minimum daily instructional minutes by grade level.
    Source: State education codes and regulations.
    """
    __tablename__ = "state_requirements"

    # Primary key
    state: Mapped[str] = mapped_column(String(2), primary_key=True)

    # Core fields
    state_name: Mapped[str] = mapped_column(String(50), nullable=False)
    elementary_minutes: Mapped[Optional[int]] = mapped_column(Integer)
    middle_minutes: Mapped[Optional[int]] = mapped_column(Integer)
    high_minutes: Mapped[Optional[int]] = mapped_column(Integer)
    default_minutes: Mapped[Optional[int]] = mapped_column(Integer)
    annual_days: Mapped[Optional[int]] = mapped_column(Integer)
    annual_hours: Mapped[Optional[float]] = mapped_column(Numeric(6, 2))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    source: Mapped[Optional[str]] = mapped_column(String(255))

    # Timestamp
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def __repr__(self) -> str:
        return f"<StateRequirement {self.state}: {self.state_name}>"

    def get_minutes(self, grade_level: str) -> Optional[int]:
        """Get instructional minutes for a specific grade level."""
        if grade_level == "elementary":
            return self.elementary_minutes or self.default_minutes
        elif grade_level == "middle":
            return self.middle_minutes or self.default_minutes
        elif grade_level == "high":
            return self.high_minutes or self.default_minutes
        return self.default_minutes

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON export."""
        return {
            "state": self.state,
            "state_name": self.state_name,
            "elementary_minutes": self.elementary_minutes,
            "middle_minutes": self.middle_minutes,
            "high_minutes": self.high_minutes,
            "default_minutes": self.default_minutes,
            "annual_days": self.annual_days,
            "annual_hours": float(self.annual_hours) if self.annual_hours else None,
            "notes": self.notes,
            "source": self.source,
        }


class BellSchedule(Base):
    """
    Enriched bell schedule data with actual instructional time.

    Contains actual start/end times and instructional minutes
    collected from district/school websites and documents.
    """
    __tablename__ = "bell_schedules"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Foreign key
    district_id: Mapped[str] = mapped_column(
        String(10), ForeignKey("districts.nces_id", ondelete="CASCADE"), nullable=False
    )

    # Core identification
    year: Mapped[str] = mapped_column(String(10), nullable=False)
    grade_level: Mapped[str] = mapped_column(String(20), nullable=False)

    # Schedule data
    instructional_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    start_time: Mapped[Optional[str]] = mapped_column(String(20))
    end_time: Mapped[Optional[str]] = mapped_column(String(20))
    lunch_duration: Mapped[Optional[int]] = mapped_column(Integer)
    passing_periods: Mapped[Optional[int]] = mapped_column(Integer)
    recess_duration: Mapped[Optional[int]] = mapped_column(Integer)

    # Source documentation (JSONB for flexibility)
    schools_sampled = Column(JSONB, default=list)
    source_urls = Column(JSONB, default=list)

    # Quality indicators
    confidence: Mapped[str] = mapped_column(String(10), default="high")
    method: Mapped[str] = mapped_column(String(30), nullable=False)
    source_description: Mapped[Optional[str]] = mapped_column(Text)
    notes: Mapped[Optional[str]] = mapped_column(Text)

    # Original import data preserved
    raw_import = Column(JSONB)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    district: Mapped["District"] = relationship(back_populates="bell_schedules")
    lct_calculations: Mapped[List["LCTCalculation"]] = relationship(
        back_populates="bell_schedule"
    )

    # Constraints
    __table_args__ = (
        UniqueConstraint("district_id", "year", "grade_level", name="uq_bell_schedule"),
        CheckConstraint("grade_level IN ('elementary', 'middle', 'high')", name="chk_grade_level"),
        CheckConstraint("confidence IN ('high', 'medium', 'low')", name="chk_confidence"),
        CheckConstraint(
            "method IN ('automated_enrichment', 'human_provided', 'statutory_fallback')",
            name="chk_method"
        ),
        CheckConstraint(
            "instructional_minutes BETWEEN 100 AND 600",
            name="chk_instructional_minutes"
        ),
    )

    def __repr__(self) -> str:
        return f"<BellSchedule {self.district_id}/{self.year}/{self.grade_level}: {self.instructional_minutes} min>"

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON export."""
        return {
            "district_id": self.district_id,
            "year": self.year,
            "grade_level": self.grade_level,
            "instructional_minutes": self.instructional_minutes,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "lunch_duration": self.lunch_duration,
            "passing_periods": self.passing_periods,
            "recess_duration": self.recess_duration,
            "schools_sampled": self.schools_sampled,
            "source_urls": self.source_urls,
            "confidence": self.confidence,
            "method": self.method,
            "source_description": self.source_description,
            "notes": self.notes,
        }


class LCTCalculation(Base):
    """
    Computed Learning Connection Time metrics.

    LCT = (instructional_minutes * instructional_staff) / enrollment

    This represents the theoretical average time each student could
    receive individual attention from a teacher per day.
    """
    __tablename__ = "lct_calculations"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Foreign keys
    district_id: Mapped[str] = mapped_column(
        String(10), ForeignKey("districts.nces_id", ondelete="CASCADE"), nullable=False
    )
    bell_schedule_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("bell_schedules.id")
    )

    # Calculation context
    year: Mapped[str] = mapped_column(String(10), nullable=False)
    grade_level: Mapped[Optional[str]] = mapped_column(String(20))

    # Input values (denormalized for query performance)
    instructional_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    enrollment: Mapped[int] = mapped_column(Integer, nullable=False)
    instructional_staff: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)

    # Calculated metric
    lct_value: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False)

    # Data quality
    data_tier: Mapped[int] = mapped_column(Integer, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text)

    # Timestamp
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )

    # Relationships
    district: Mapped["District"] = relationship(back_populates="lct_calculations")
    bell_schedule: Mapped[Optional["BellSchedule"]] = relationship(
        back_populates="lct_calculations"
    )

    # Constraints
    __table_args__ = (
        UniqueConstraint("district_id", "year", "grade_level", name="uq_lct_calculation"),
        CheckConstraint("data_tier IN (1, 2, 3)", name="chk_data_tier"),
        CheckConstraint("lct_value > 0", name="chk_lct_positive"),
        CheckConstraint("enrollment > 0", name="chk_enrollment_positive"),
        CheckConstraint("instructional_staff > 0", name="chk_staff_positive"),
    )

    def __repr__(self) -> str:
        return f"<LCTCalculation {self.district_id}/{self.year}: {self.lct_value:.2f} min>"

    @classmethod
    def calculate_lct(
        cls,
        instructional_minutes: int,
        enrollment: int,
        instructional_staff: float,
    ) -> float:
        """
        Calculate the LCT value.

        Args:
            instructional_minutes: Daily instructional minutes
            enrollment: Total student enrollment
            instructional_staff: Full-time equivalent instructional staff

        Returns:
            LCT value (minutes per student per day)
        """
        if enrollment <= 0 or instructional_staff <= 0:
            raise ValueError("Enrollment and staff must be positive")
        return (instructional_minutes * instructional_staff) / enrollment

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON export."""
        return {
            "district_id": self.district_id,
            "year": self.year,
            "grade_level": self.grade_level,
            "instructional_minutes": self.instructional_minutes,
            "enrollment": self.enrollment,
            "instructional_staff": float(self.instructional_staff),
            "lct_value": float(self.lct_value),
            "data_tier": self.data_tier,
            "notes": self.notes,
            "calculated_at": self.calculated_at.isoformat() if self.calculated_at else None,
        }


class CalculationRun(Base):
    """
    Tracks LCT calculation runs for incremental processing.

    Enables efficient recalculation by tracking what was processed when.

    Calculation Modes:
    - BLENDED: Uses most recent data within REQ-026 3-year window (default)
    - TARGET_YEAR: Enrollment anchored to target_year, staff/bell blended within window
    """
    __tablename__ = "calculation_runs"

    # Primary key
    run_id: Mapped[str] = mapped_column(String(50), primary_key=True)

    # Run metadata
    calculation_mode: Mapped[CalculationMode] = mapped_column(
        SQLAlchemyEnum(CalculationMode, name='calculation_mode_enum'),
        nullable=False,
        default=CalculationMode.BLENDED
    )
    target_year: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    run_type: Mapped[str] = mapped_column(String(30), nullable=False)  # full, incremental
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # running, completed, failed

    # Data range tracking (computed from actual sources used)
    data_year_min: Mapped[Optional[str]] = mapped_column(String(10))  # Earliest source year
    data_year_max: Mapped[Optional[str]] = mapped_column(String(10))  # Latest source year

    # Processing stats
    districts_processed: Mapped[int] = mapped_column(Integer, default=0)
    districts_skipped: Mapped[int] = mapped_column(Integer, default=0)
    calculations_created: Mapped[int] = mapped_column(Integer, default=0)

    # Input hashes for change detection
    input_hash: Mapped[Optional[str]] = mapped_column(String(64))  # Hash of source data state
    previous_run_id: Mapped[Optional[str]] = mapped_column(String(50))

    # Timing
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Output tracking
    output_files = Column(JSONB, default=list)  # List of generated files
    error_message: Mapped[Optional[str]] = mapped_column(Text)

    # QA summary
    qa_summary = Column(JSONB)  # QA report embedded

    def __repr__(self) -> str:
        mode_str = f"mode={self.calculation_mode.value}"
        year_str = f", target={self.target_year}" if self.target_year else ""
        return f"<CalculationRun {self.run_id}: {self.status} ({mode_str}{year_str})>"

    @validates('target_year')
    def validate_target_year(self, key, value):
        """
        Validate target_year consistency with calculation_mode.

        - TARGET_YEAR mode requires target_year to be set
        - BLENDED mode allows target_year to be NULL (or set for reference)
        """
        # Note: validation happens after assignment, so we check in start_run
        return value

    @classmethod
    def start_run(
        cls,
        session,
        calculation_mode: CalculationMode = CalculationMode.BLENDED,
        target_year: Optional[str] = None,
        run_type: str = "full",
        previous_run_id: Optional[str] = None,
    ) -> "CalculationRun":
        """
        Start a new calculation run.

        Args:
            session: Database session
            calculation_mode: BLENDED (default) or TARGET_YEAR
            target_year: Required for TARGET_YEAR mode, optional for BLENDED
            run_type: 'full' or 'incremental'
            previous_run_id: ID of previous run for incremental processing

        Raises:
            ValueError: If TARGET_YEAR mode specified without target_year
        """
        from datetime import timezone

        # Validate mode/year consistency
        if calculation_mode == CalculationMode.TARGET_YEAR and not target_year:
            raise ValueError("target_year is required when calculation_mode is TARGET_YEAR")

        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

        run = cls(
            run_id=run_id,
            calculation_mode=calculation_mode,
            target_year=target_year,
            run_type=run_type,
            status="running",
            previous_run_id=previous_run_id,
        )
        session.add(run)
        session.flush()
        return run

    def complete(
        self,
        districts_processed: int,
        calculations_created: int,
        output_files: List[str],
        qa_summary: Optional[dict] = None,
        data_year_min: Optional[str] = None,
        data_year_max: Optional[str] = None,
    ) -> None:
        """Mark run as completed with data range information."""
        self.status = "completed"
        self.completed_at = datetime.utcnow()
        self.districts_processed = districts_processed
        self.calculations_created = calculations_created
        self.output_files = output_files
        self.qa_summary = qa_summary
        self.data_year_min = data_year_min
        self.data_year_max = data_year_max

    def fail(self, error_message: str) -> None:
        """Mark run as failed."""
        self.status = "failed"
        self.completed_at = datetime.utcnow()
        self.error_message = error_message


class DataLineage(Base):
    """
    Audit trail for data changes and imports.

    Tracks the provenance of data for transparency and debugging.
    """
    __tablename__ = "data_lineage"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # What was affected
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(50), nullable=False)

    # What happened
    operation: Mapped[str] = mapped_column(String(30), nullable=False)
    source_file: Mapped[Optional[str]] = mapped_column(String(500))
    details = Column(JSONB)

    # When and by whom
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    created_by: Mapped[str] = mapped_column(String(100), default="system")

    def __repr__(self) -> str:
        return f"<DataLineage {self.entity_type}/{self.entity_id}: {self.operation}>"

    @classmethod
    def log(
        cls,
        session,
        entity_type: str,
        entity_id: str,
        operation: str,
        source_file: Optional[str] = None,
        details: Optional[dict] = None,
        created_by: str = "system",
    ) -> "DataLineage":
        """
        Create a lineage record.

        Args:
            session: SQLAlchemy session
            entity_type: Type of entity (district, bell_schedule, etc.)
            entity_id: ID of the entity
            operation: What happened (create, update, import, etc.)
            source_file: Optional source file path
            details: Optional additional details as dict
            created_by: Who/what performed the operation

        Returns:
            The created DataLineage instance
        """
        lineage = cls(
            entity_type=entity_type,
            entity_id=entity_id,
            operation=operation,
            source_file=source_file,
            details=details,
            created_by=created_by,
        )
        session.add(lineage)
        return lineage


class DataSourceRegistry(Base):
    """
    Registry of available data sources with metadata.

    Tracks federal, state, and other sources for staffing and enrollment data.
    """
    __tablename__ = "data_source_registry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    source_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_url: Mapped[Optional[str]] = mapped_column(Text)

    # Coverage
    geographic_scope: Mapped[Optional[str]] = mapped_column(String(50))
    state: Mapped[Optional[str]] = mapped_column(String(2))

    # Data availability
    latest_year_available: Mapped[Optional[str]] = mapped_column(String(10))
    years_available = Column(JSONB, default=list)

    # Update tracking
    last_checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    next_expected_release: Mapped[Optional[str]] = mapped_column(String(50))

    # Access information
    access_method: Mapped[Optional[str]] = mapped_column(String(50))
    access_notes: Mapped[Optional[str]] = mapped_column(Text)
    requires_authentication: Mapped[bool] = mapped_column(Boolean, default=False)

    # Quality assessment
    reliability_score: Mapped[Optional[int]] = mapped_column(Integer)
    notes: Mapped[Optional[str]] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def __repr__(self) -> str:
        return f"<DataSourceRegistry {self.source_code}: {self.source_name}>"


class StaffCounts(Base):
    """
    Historical staff counts by category from all sources.

    Multiple rows per district (one per source+year).
    Contains granular staff data for LCT calculations.
    """
    __tablename__ = "staff_counts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Foreign key
    district_id: Mapped[str] = mapped_column(
        String(10), ForeignKey("districts.nces_id", ondelete="CASCADE"), nullable=False
    )

    # Source tracking
    source_year: Mapped[str] = mapped_column(String(10), nullable=False)
    data_source: Mapped[str] = mapped_column(String(50), nullable=False)
    source_url: Mapped[Optional[str]] = mapped_column(Text)
    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )

    # === TIER 1: CLASSROOM TEACHERS ===
    teachers_total: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    teachers_elementary: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    teachers_kindergarten: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    teachers_secondary: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    teachers_prek: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    teachers_ungraded: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))

    # === TIER 2: INSTRUCTIONAL SUPPORT ===
    instructional_coordinators: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    librarians: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    library_support: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    paraprofessionals: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))

    # === TIER 3: STUDENT SUPPORT ===
    counselors_total: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    counselors_elementary: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    counselors_secondary: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    psychologists: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    student_support_services: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))

    # === TIER 4: ADMINISTRATIVE ===
    lea_administrators: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    school_administrators: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    lea_admin_support: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    school_admin_support: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))

    # === AGGREGATES ===
    lea_staff_total: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    school_staff_total: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    other_staff: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    all_other_support_staff: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))

    # === CRDC-SPECIFIC ===
    teachers_first_year: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    teachers_second_year: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    teachers_absent_10plus_days: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))

    # Quality tracking
    is_complete: Mapped[bool] = mapped_column(Boolean, default=True)
    quality_notes: Mapped[Optional[str]] = mapped_column(Text)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    district: Mapped["District"] = relationship(back_populates="staff_counts")

    # Constraints
    __table_args__ = (
        UniqueConstraint("district_id", "source_year", "data_source", name="uq_staff_counts"),
    )

    def __repr__(self) -> str:
        return f"<StaffCounts {self.district_id}/{self.source_year}/{self.data_source}>"


class StaffCountsEffective(Base):
    """
    Resolved current staff counts after precedence rules.

    One row per district. Primary query table for applications.
    Contains pre-calculated scope values for all 5 LCT variants.
    """
    __tablename__ = "staff_counts_effective"

    # Primary key (one row per district)
    district_id: Mapped[str] = mapped_column(
        String(10), ForeignKey("districts.nces_id", ondelete="CASCADE"), primary_key=True
    )

    # Source tracking
    effective_year: Mapped[str] = mapped_column(String(10), nullable=False)
    primary_source: Mapped[str] = mapped_column(String(50), nullable=False)
    sources_used = Column(JSONB, default=list)

    # === RESOLVED STAFF COUNTS ===
    teachers_total: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    teachers_elementary: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    teachers_kindergarten: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    teachers_secondary: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    teachers_prek: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    teachers_ungraded: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    instructional_coordinators: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    librarians: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    library_support: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    paraprofessionals: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    counselors_total: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    counselors_elementary: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    counselors_secondary: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    psychologists: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    student_support_services: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    lea_administrators: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    school_administrators: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    lea_admin_support: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    school_admin_support: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    lea_staff_total: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    school_staff_total: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    other_staff: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))

    # === TEACHER-LEVEL AGGREGATES (for level-based LCT) ===
    teachers_k12: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))  # elem + sec + kinder (NO prek, NO ungraded)
    teachers_elementary_k5: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))  # elem + kinder
    teachers_secondary_6_12: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))  # secondary only

    # === PRE-CALCULATED SCOPE VALUES ===
    scope_teachers_only: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))  # Same as teachers_k12
    scope_teachers_core: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))  # K-12 teachers + ungraded
    scope_instructional: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    scope_instructional_plus_support: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    scope_all: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))

    # Metadata
    last_resolved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    resolution_notes: Mapped[Optional[str]] = mapped_column(Text)

    # Relationships
    district: Mapped["District"] = relationship(back_populates="staff_counts_effective")

    def __repr__(self) -> str:
        return f"<StaffCountsEffective {self.district_id}: {self.effective_year}>"

    def calculate_scopes(self) -> None:
        """
        Calculate all scope values from individual staff counts.

        Key decisions (December 2025):
        - All scopes exclude Pre-K teachers and use K-12 enrollment
        - Ungraded teachers EXCLUDED from LCT-Teachers variants
        - Ungraded teachers INCLUDED in LCT-Core, Instructional, Support, All
        """
        import math
        from decimal import Decimal

        def safe_sum(*values):
            """Sum values, treating None and NaN as 0."""
            total = 0
            for v in values:
                if v is None:
                    continue
                try:
                    fv = float(v)
                    if not math.isnan(fv):
                        total += fv
                except (TypeError, ValueError):
                    continue
            return total

        # Teacher-level aggregates (for level-based LCT)
        # LCT-Teachers: elem + sec + kinder (NO prek, NO ungraded)
        self.teachers_k12 = safe_sum(
            self.teachers_elementary,
            self.teachers_secondary,
            self.teachers_kindergarten
        ) or None

        # LCT-Teachers-Elementary: elem + kinder
        self.teachers_elementary_k5 = safe_sum(
            self.teachers_elementary,
            self.teachers_kindergarten
        ) or None

        # LCT-Teachers-Secondary: just secondary
        self.teachers_secondary_6_12 = self.teachers_secondary

        # scope_teachers_only: Same as teachers_k12 (NO ungraded, NO prek)
        self.scope_teachers_only = self.teachers_k12

        # scope_teachers_core: K-12 teachers + ungraded (NO prek)
        self.scope_teachers_core = safe_sum(
            self.teachers_elementary,
            self.teachers_secondary,
            self.teachers_kindergarten,
            self.teachers_ungraded
        ) or None

        # scope_instructional: core + coordinators + paras
        self.scope_instructional = safe_sum(
            self.teachers_elementary,
            self.teachers_secondary,
            self.teachers_kindergarten,
            self.teachers_ungraded,
            self.instructional_coordinators,
            self.paraprofessionals
        ) or None

        # scope_instructional_plus_support: instructional + counselors + psych + support
        self.scope_instructional_plus_support = safe_sum(
            self.teachers_elementary,
            self.teachers_secondary,
            self.teachers_kindergarten,
            self.teachers_ungraded,
            self.instructional_coordinators,
            self.paraprofessionals,
            self.counselors_total,
            self.psychologists,
            self.student_support_services
        ) or None

        # scope_all: All staff EXCEPT Pre-K teachers
        self.scope_all = safe_sum(
            self.teachers_elementary,
            self.teachers_secondary,
            self.teachers_kindergarten,
            self.teachers_ungraded,
            self.instructional_coordinators,
            self.librarians,
            self.library_support,
            self.paraprofessionals,
            self.counselors_total,
            self.psychologists,
            self.student_support_services,
            self.lea_administrators,
            self.school_administrators,
            self.lea_admin_support,
            self.school_admin_support,
            self.other_staff
        ) or None


class EnrollmentByGrade(Base):
    """
    Grade-level enrollment for LCT-Core calculations.

    Allows excluding Pre-K from the denominator when using
    teachers_core (which excludes Pre-K teachers).
    """
    __tablename__ = "enrollment_by_grade"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Foreign key
    district_id: Mapped[str] = mapped_column(
        String(10), ForeignKey("districts.nces_id", ondelete="CASCADE"), nullable=False
    )

    # Source tracking
    source_year: Mapped[str] = mapped_column(String(10), nullable=False)
    data_source: Mapped[str] = mapped_column(String(50), default="nces_ccd")

    # Enrollment by grade
    enrollment_prek: Mapped[Optional[int]] = mapped_column(Integer)
    enrollment_kindergarten: Mapped[Optional[int]] = mapped_column(Integer)
    enrollment_grade_1: Mapped[Optional[int]] = mapped_column(Integer)
    enrollment_grade_2: Mapped[Optional[int]] = mapped_column(Integer)
    enrollment_grade_3: Mapped[Optional[int]] = mapped_column(Integer)
    enrollment_grade_4: Mapped[Optional[int]] = mapped_column(Integer)
    enrollment_grade_5: Mapped[Optional[int]] = mapped_column(Integer)
    enrollment_grade_6: Mapped[Optional[int]] = mapped_column(Integer)
    enrollment_grade_7: Mapped[Optional[int]] = mapped_column(Integer)
    enrollment_grade_8: Mapped[Optional[int]] = mapped_column(Integer)
    enrollment_grade_9: Mapped[Optional[int]] = mapped_column(Integer)
    enrollment_grade_10: Mapped[Optional[int]] = mapped_column(Integer)
    enrollment_grade_11: Mapped[Optional[int]] = mapped_column(Integer)
    enrollment_grade_12: Mapped[Optional[int]] = mapped_column(Integer)
    enrollment_grade_13: Mapped[Optional[int]] = mapped_column(Integer)
    enrollment_ungraded: Mapped[Optional[int]] = mapped_column(Integer)
    enrollment_adult_ed: Mapped[Optional[int]] = mapped_column(Integer)

    # Aggregates
    enrollment_total: Mapped[Optional[int]] = mapped_column(Integer)
    enrollment_k12: Mapped[Optional[int]] = mapped_column(Integer)  # Total minus Pre-K
    enrollment_elementary: Mapped[Optional[int]] = mapped_column(Integer)  # K-5
    enrollment_secondary: Mapped[Optional[int]] = mapped_column(Integer)  # 6-12

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    district: Mapped["District"] = relationship(back_populates="enrollment_by_grade")

    # Constraints
    __table_args__ = (
        UniqueConstraint("district_id", "source_year", "data_source", name="uq_enrollment_by_grade"),
    )

    def __repr__(self) -> str:
        return f"<EnrollmentByGrade {self.district_id}/{self.source_year}>"

    def calculate_k12(self) -> None:
        """Calculate K-12 enrollment (total minus Pre-K)."""
        if self.enrollment_total is not None:
            prek = self.enrollment_prek or 0
            self.enrollment_k12 = self.enrollment_total - prek

    def calculate_level_enrollments(self) -> None:
        """Calculate level-based enrollment aggregates."""
        def safe_sum(*values):
            return sum(v or 0 for v in values)

        # Elementary = K + grades 1-5
        self.enrollment_elementary = safe_sum(
            self.enrollment_kindergarten,
            self.enrollment_grade_1,
            self.enrollment_grade_2,
            self.enrollment_grade_3,
            self.enrollment_grade_4,
            self.enrollment_grade_5
        )

        # Secondary = grades 6-12
        self.enrollment_secondary = safe_sum(
            self.enrollment_grade_6,
            self.enrollment_grade_7,
            self.enrollment_grade_8,
            self.enrollment_grade_9,
            self.enrollment_grade_10,
            self.enrollment_grade_11,
            self.enrollment_grade_12
        )

        # Also update K-12 if not already set
        if self.enrollment_k12 is None:
            self.calculate_k12()


# =============================================================================
# SPED SEGMENTATION BASELINE TABLES (2017-18 Pre-COVID Year)
# =============================================================================


class SpedStateBaseline(Base):
    """
    State-level SPED baseline data from IDEA 618 (2017-18).

    Contains state-level SPED teachers and students for calculating
    the state SPED teacher-to-student ratio (Ratio 4a).

    Sources:
    - IDEA 618 Personnel (State-level SPED teacher FTE)
    - IDEA 618 Child Count (State-level SPED student count ages 6-21)
    """
    __tablename__ = "sped_state_baseline"

    # Primary key
    state: Mapped[str] = mapped_column(String(2), primary_key=True)

    # Source tracking
    source_year: Mapped[str] = mapped_column(String(10), nullable=False, default="2017-18")

    # IDEA 618 Personnel: SPED Teachers (Ages 6-21)
    sped_teachers_certified: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    sped_teachers_not_certified: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    sped_teachers_total: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))

    # IDEA 618 Personnel: SPED Paraprofessionals (Ages 6-21)
    sped_paras_qualified: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    sped_paras_not_qualified: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    sped_paras_total: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))

    # Combined instructional staff (teachers + paras)
    sped_instructional_total: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))

    # IDEA 618 Child Count: SPED Students (Ages 6-21, school-age)
    sped_students_ages_3_5: Mapped[Optional[int]] = mapped_column(Integer)
    sped_students_ages_6_21: Mapped[Optional[int]] = mapped_column(Integer)
    sped_students_total: Mapped[Optional[int]] = mapped_column(Integer)

    # IDEA 618 Educational Environments: Self-Contained SPED (Ages 6-21)
    # Self-contained = Separate Class + Separate School + <40% in regular class
    # Excludes: Residential Facility, Correctional Facilities (not district-managed)
    sped_students_self_contained: Mapped[Optional[int]] = mapped_column(Integer)
    sped_students_mainstreamed: Mapped[Optional[int]] = mapped_column(Integer)  # 80%+ and 40-79% in regular class

    # Calculated Ratios
    # Ratio for estimating self-contained proportion at LEA level
    ratio_self_contained_proportion: Mapped[Optional[float]] = mapped_column(Numeric(10, 6))
    # Ratio for lct_core_sped: SPED Teachers / Self-Contained SPED Students
    ratio_sped_teachers_per_student: Mapped[Optional[float]] = mapped_column(Numeric(10, 6))
    # Ratio for lct_instructional_sped: (SPED Teachers + Paras) / Self-Contained SPED Students
    ratio_sped_instructional_per_student: Mapped[Optional[float]] = mapped_column(Numeric(10, 6))

    # Quality tracking
    personnel_source_file: Mapped[Optional[str]] = mapped_column(String(255))
    child_count_source_file: Mapped[Optional[str]] = mapped_column(String(255))
    data_quality_notes: Mapped[Optional[str]] = mapped_column(Text)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def __repr__(self) -> str:
        return f"<SpedStateBaseline {self.state}: {self.sped_teachers_total} teachers, {self.sped_students_ages_6_21} students>"

    def calculate_ratios(self) -> None:
        """Calculate SPED staff ratios using self-contained student counts."""
        # Calculate self-contained proportion (for LEA estimation)
        if self.sped_students_ages_6_21 and self.sped_students_ages_6_21 > 0:
            if self.sped_students_self_contained:
                self.ratio_self_contained_proportion = float(self.sped_students_self_contained) / self.sped_students_ages_6_21

        # Calculate staff ratios per self-contained student
        if self.sped_students_self_contained and self.sped_students_self_contained > 0:
            # Ratio for lct_core_sped: teachers / self-contained students
            if self.sped_teachers_total:
                self.ratio_sped_teachers_per_student = float(self.sped_teachers_total) / self.sped_students_self_contained

            # Ratio for lct_instructional_sped: (teachers + paras) / self-contained students
            if self.sped_instructional_total:
                self.ratio_sped_instructional_per_student = float(self.sped_instructional_total) / self.sped_students_self_contained


class SpedLeaBaseline(Base):
    """
    LEA-level SPED baseline data from CRDC and CCD (2017-18).

    Contains LEA-level enrollment for calculating the SPED student proportion
    (Ratio 4b: LEA SPED Students / LEA Total Students).

    Sources:
    - CRDC 2017-18 Enrollment (LEA-level SPED student counts)
    - CCD 2017-18 LEA Membership (LEA-level total enrollment)
    """
    __tablename__ = "sped_lea_baseline"

    # Primary key
    lea_id: Mapped[str] = mapped_column(String(10), primary_key=True)

    # LEA identification
    lea_name: Mapped[Optional[str]] = mapped_column(String(255))
    state: Mapped[str] = mapped_column(String(2), nullable=False)

    # Source tracking
    source_year: Mapped[str] = mapped_column(String(10), nullable=False, default="2017-18")

    # CRDC: SPED Enrollment (IDEA students)
    crdc_sped_enrollment_m: Mapped[Optional[int]] = mapped_column(Integer)
    crdc_sped_enrollment_f: Mapped[Optional[int]] = mapped_column(Integer)
    crdc_sped_enrollment_total: Mapped[Optional[int]] = mapped_column(Integer)

    # CRDC: Total Enrollment (for validation)
    crdc_total_enrollment_m: Mapped[Optional[int]] = mapped_column(Integer)
    crdc_total_enrollment_f: Mapped[Optional[int]] = mapped_column(Integer)
    crdc_total_enrollment: Mapped[Optional[int]] = mapped_column(Integer)

    # CCD: Total Enrollment (primary source for total)
    ccd_total_enrollment: Mapped[Optional[int]] = mapped_column(Integer)

    # Calculated Ratio 4b: LEA SPED Students / LEA Total Students
    ratio_sped_proportion: Mapped[Optional[float]] = mapped_column(Numeric(10, 6))

    # Quality tracking
    crdc_source_file: Mapped[Optional[str]] = mapped_column(String(255))
    ccd_source_file: Mapped[Optional[str]] = mapped_column(String(255))
    data_quality_notes: Mapped[Optional[str]] = mapped_column(Text)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def __repr__(self) -> str:
        return f"<SpedLeaBaseline {self.lea_id} ({self.state}): {self.crdc_sped_enrollment_total} SPED / {self.ccd_total_enrollment} total>"

    def calculate_ratio(self) -> None:
        """Calculate Ratio 4b: SPED proportion of total enrollment."""
        # Prefer CCD total enrollment, fall back to CRDC if not available
        total = self.ccd_total_enrollment or self.crdc_total_enrollment
        if self.crdc_sped_enrollment_total and total and total > 0:
            self.ratio_sped_proportion = float(self.crdc_sped_enrollment_total) / total


class SpedEstimate(Base):
    """
    Current-year SPED estimates derived from baseline ratios.

    Applies 2017-18 ratios to current year data to estimate:
    - LEA SPED enrollment
    - LEA SPED teachers
    - LEA GenEd teachers

    These estimates enable LCT-Teachers-SPED and LCT-Teachers-GenEd calculations.
    """
    __tablename__ = "sped_estimates"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Foreign key to current districts
    district_id: Mapped[str] = mapped_column(
        String(10), ForeignKey("districts.nces_id", ondelete="CASCADE"), nullable=False
    )

    # Estimation context
    estimate_year: Mapped[str] = mapped_column(String(10), nullable=False)
    baseline_year: Mapped[str] = mapped_column(String(10), nullable=False, default="2017-18")

    # Input values (from current year data)
    current_total_enrollment: Mapped[Optional[int]] = mapped_column(Integer)
    current_total_teachers: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))

    # Ratios used (denormalized for transparency)
    ratio_state_sped_teachers_per_student: Mapped[Optional[float]] = mapped_column(Numeric(10, 6))
    ratio_state_sped_instructional_per_student: Mapped[Optional[float]] = mapped_column(Numeric(10, 6))
    ratio_state_self_contained_proportion: Mapped[Optional[float]] = mapped_column(Numeric(10, 6))
    ratio_lea_sped_proportion: Mapped[Optional[float]] = mapped_column(Numeric(10, 6))

    # Fallback tracking (if LEA-specific ratio unavailable)
    used_state_average_for_proportion: Mapped[bool] = mapped_column(Boolean, default=False)

    # Estimated values
    estimated_sped_enrollment: Mapped[Optional[int]] = mapped_column(Integer)  # All SPED students
    estimated_self_contained_sped: Mapped[Optional[int]] = mapped_column(Integer)  # Self-contained SPED only
    estimated_gened_enrollment: Mapped[Optional[int]] = mapped_column(Integer)  # Total - Self-Contained
    estimated_sped_teachers: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    estimated_sped_instructional: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))  # Teachers + Paras
    estimated_gened_teachers: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))

    # Quality tracking
    estimation_method: Mapped[str] = mapped_column(String(50), nullable=False)
    confidence: Mapped[str] = mapped_column(String(20), default="medium")
    notes: Mapped[Optional[str]] = mapped_column(Text)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Constraints
    __table_args__ = (
        UniqueConstraint("district_id", "estimate_year", name="uq_sped_estimate"),
        CheckConstraint("confidence IN ('high', 'medium', 'low')", name="chk_sped_confidence"),
    )

    def __repr__(self) -> str:
        return f"<SpedEstimate {self.district_id}/{self.estimate_year}: {self.estimated_sped_teachers} SPED, {self.estimated_gened_teachers} GenEd>"

    def calculate_estimates(self) -> None:
        """
        Calculate SPED estimates from current year data and baseline ratios.

        Method (January 2026 - Self-Contained Focus):
        1. Estimated All SPED = Total Enrollment × LEA SPED Proportion
        2. Estimated Self-Contained SPED = All SPED × State Self-Contained Proportion
        3. Estimated GenEd Enrollment = Total - Self-Contained (includes mainstreamed SPED)
        4. Estimated SPED Teachers = Self-Contained × State Teacher Ratio
        5. Estimated SPED Instructional = Self-Contained × State Instructional Ratio
        6. Estimated GenEd Teachers = Total Teachers - SPED Teachers
        """
        if not all([
            self.current_total_enrollment,
            self.current_total_teachers,
            self.ratio_lea_sped_proportion,
            self.ratio_state_sped_teachers_per_student,
            self.ratio_state_self_contained_proportion
        ]):
            return

        # Step 1: Estimate all SPED enrollment (for intermediate calculation)
        sped_proportion = float(self.ratio_lea_sped_proportion)
        self.estimated_sped_enrollment = int(round(self.current_total_enrollment * sped_proportion))

        # Step 2: Estimate self-contained SPED (subset of all SPED)
        self_contained_proportion = float(self.ratio_state_self_contained_proportion)
        self.estimated_self_contained_sped = int(round(self.estimated_sped_enrollment * self_contained_proportion))

        # Step 3: Estimate GenEd enrollment (Total - Self-Contained)
        # GenEd now includes: non-SPED students + mainstreamed SPED students
        self.estimated_gened_enrollment = self.current_total_enrollment - self.estimated_self_contained_sped

        # Step 4: Estimate SPED teachers (ratio is per self-contained student)
        teachers_per_student = float(self.ratio_state_sped_teachers_per_student)
        self.estimated_sped_teachers = round(self.estimated_self_contained_sped * teachers_per_student, 2)

        # Step 5: Estimate SPED instructional (teachers + paras, per self-contained student)
        if self.ratio_state_sped_instructional_per_student:
            instructional_per_student = float(self.ratio_state_sped_instructional_per_student)
            self.estimated_sped_instructional = round(self.estimated_self_contained_sped * instructional_per_student, 2)

        # Step 5: Estimate GenEd teachers
        total_teachers = float(self.current_total_teachers)
        self.estimated_gened_teachers = round(total_teachers - float(self.estimated_sped_teachers), 2)

        # Validation: GenEd teachers should be positive
        if self.estimated_gened_teachers < 0:
            self.notes = (self.notes or "") + " WARNING: Negative GenEd teachers estimate."
            self.confidence = "low"


# =============================================================================
# LAYER 2: STATE-LEVEL ENHANCEMENTS (California Phase 2)
# =============================================================================


class CASpedDistrictEnvironments(Base):
    """
    California SPED enrollment by educational environment (district-level).

    Replaces estimated self-contained proportions with actual district data
    from California Department of Education SPED data files.

    Source: CA CDE Special Education Enrollment by Educational Environment
    Years: 2022-23, 2023-24, 2024-25
    """
    __tablename__ = "ca_sped_district_environments"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Foreign key to districts
    nces_id: Mapped[str] = mapped_column(
        String(10), ForeignKey("districts.nces_id", ondelete="CASCADE"), nullable=False
    )

    # California CDS code for crosswalk
    cds_code: Mapped[str] = mapped_column(String(7), nullable=False)

    # Source tracking
    year: Mapped[str] = mapped_column(String(10), nullable=False)
    data_source: Mapped[str] = mapped_column(String(50), default="ca_cde_sped")

    # Total SPED enrollment (with active IEPs)
    sped_enrollment_total: Mapped[Optional[int]] = mapped_column(Integer)

    # Educational environment breakdowns (5 categories from CA data)
    # MAINSTREAMED (80%+ and 40-79% in regular class)
    sped_mainstreamed: Mapped[Optional[int]] = mapped_column(Integer)
    sped_mainstreamed_80_plus: Mapped[Optional[int]] = mapped_column(Integer)  # PS_RCGT80_N
    sped_mainstreamed_40_79: Mapped[Optional[int]] = mapped_column(Integer)    # PS_RC4079_N

    # SELF-CONTAINED (<40% and separate school)
    sped_self_contained: Mapped[Optional[int]] = mapped_column(Integer)
    sped_self_contained_lt_40: Mapped[Optional[int]] = mapped_column(Integer)  # PS_RCL40_N
    sped_separate_school: Mapped[Optional[int]] = mapped_column(Integer)        # PS_SSOS_N

    # PRESCHOOL (Ages 3-5, excluded from K-12 calculations)
    sped_preschool: Mapped[Optional[int]] = mapped_column(Integer)             # PS_PSS_N

    # MISSING/UNREPORTED
    sped_missing: Mapped[Optional[int]] = mapped_column(Integer)               # PS_MUK_N

    # Calculated proportion (for comparison with state baseline)
    self_contained_proportion: Mapped[Optional[float]] = mapped_column(Numeric(10, 6))

    # Quality tracking
    confidence: Mapped[str] = mapped_column(String(20), default="high")
    notes: Mapped[Optional[str]] = mapped_column(Text)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    district: Mapped["District"] = relationship(back_populates="ca_sped_environments")

    # Constraints and Indexes
    __table_args__ = (
        UniqueConstraint("nces_id", "year", name="uq_ca_sped_environment"),
        CheckConstraint("confidence IN ('high', 'medium', 'low')", name="chk_ca_sped_confidence"),
        Index("ix_ca_sped_nces_id", "nces_id"),
        Index("ix_ca_sped_year", "year"),
        Index("ix_ca_sped_cds_code", "cds_code"),
    )

    def __repr__(self) -> str:
        return f"<CASpedDistrictEnvironments {self.nces_id}/{self.year}: {self.sped_enrollment_total} total, {self.sped_self_contained} self-contained>"

    def calculate_proportion(self) -> None:
        """Calculate self-contained proportion from actual counts."""
        if self.sped_enrollment_total and self.sped_enrollment_total > 0:
            if self.sped_self_contained:
                self.self_contained_proportion = float(self.sped_self_contained) / self.sped_enrollment_total


class DistrictSocioeconomic(Base):
    """
    District-level socioeconomic indicators (multi-state, multi-source).

    Supports multiple poverty indicators:
    - FRPM (Free/Reduced-Price Meal) - California, most states
    - ENI (Economic Need Index) - New York
    - Economically Disadvantaged - Texas, other states
    - Title I poverty counts - Federal

    Multiple sources per district allowed for comparison.
    """
    __tablename__ = "district_socioeconomic"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Foreign key
    nces_id: Mapped[str] = mapped_column(
        String(10), ForeignKey("districts.nces_id", ondelete="CASCADE"), nullable=False
    )

    # Source tracking
    year: Mapped[str] = mapped_column(String(10), nullable=False)
    state: Mapped[str] = mapped_column(String(2), nullable=False)

    # Core poverty indicator
    poverty_indicator_type: Mapped[str] = mapped_column(String(50), nullable=False)
    poverty_percent: Mapped[Optional[float]] = mapped_column(Numeric(10, 6))
    poverty_count: Mapped[Optional[int]] = mapped_column(Integer)
    enrollment: Mapped[Optional[int]] = mapped_column(Integer)  # For validation

    # Tiered/categorical data (e.g., Texas SCE tiers, NY poverty levels)
    tier_1_count: Mapped[Optional[int]] = mapped_column(Integer)
    tier_2_count: Mapped[Optional[int]] = mapped_column(Integer)
    tier_3_count: Mapped[Optional[int]] = mapped_column(Integer)
    tier_4_count: Mapped[Optional[int]] = mapped_column(Integer)
    tier_5_count: Mapped[Optional[int]] = mapped_column(Integer)
    tier_metadata = Column(JSONB)  # Flexible tier definitions

    # Funding-related flags
    title_i_eligible: Mapped[Optional[bool]] = mapped_column(Boolean)
    schoolwide_program: Mapped[Optional[bool]] = mapped_column(Boolean)

    # Source documentation
    data_source: Mapped[str] = mapped_column(String(50), nullable=False)
    source_url: Mapped[Optional[str]] = mapped_column(String(500))
    collection_method: Mapped[Optional[str]] = mapped_column(String(100))

    # Quality tracking
    certification_status: Mapped[Optional[str]] = mapped_column(String(20))
    notes: Mapped[Optional[str]] = mapped_column(Text)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )

    # Relationships
    district: Mapped["District"] = relationship(back_populates="socioeconomic_data")

    # Constraints and Indexes
    __table_args__ = (
        UniqueConstraint("nces_id", "year", "poverty_indicator_type", "data_source", name="uq_district_socioeconomic"),
        CheckConstraint("poverty_percent BETWEEN 0 AND 1", name="chk_poverty_percent"),
        Index("ix_socioeconomic_nces_id", "nces_id"),
        Index("ix_socioeconomic_year", "year"),
        Index("ix_socioeconomic_state", "state"),
        Index("ix_socioeconomic_poverty_type", "poverty_indicator_type"),
    )

    def __repr__(self) -> str:
        return f"<DistrictSocioeconomic {self.nces_id}/{self.year}: {self.poverty_indicator_type} = {self.poverty_percent:.1%}>"


class DistrictFunding(Base):
    """
    District-level funding data (multi-state, multi-source).

    Supports federal and state funding sources:
    - Federal: Title I, IDEA, Title III
    - State: LCFF (CA), SCE (TX), Foundation (other states)

    Multiple sources per district allowed for comparison.
    """
    __tablename__ = "district_funding"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Foreign key
    nces_id: Mapped[str] = mapped_column(
        String(10), ForeignKey("districts.nces_id", ondelete="CASCADE"), nullable=False
    )

    # Source tracking
    year: Mapped[str] = mapped_column(String(10), nullable=False)
    state: Mapped[str] = mapped_column(String(2), nullable=False)

    # Federal funding
    title_i_allocation: Mapped[Optional[float]] = mapped_column(Numeric(12, 2))
    idea_allocation: Mapped[Optional[float]] = mapped_column(Numeric(12, 2))
    title_iii_allocation: Mapped[Optional[float]] = mapped_column(Numeric(12, 2))
    other_federal: Mapped[Optional[float]] = mapped_column(Numeric(12, 2))

    # State funding (flexible structure)
    state_formula_type: Mapped[Optional[str]] = mapped_column(String(50))
    base_allocation: Mapped[Optional[float]] = mapped_column(Numeric(12, 2))
    equity_adjustment: Mapped[Optional[float]] = mapped_column(Numeric(12, 2))
    equity_adjustment_type: Mapped[Optional[str]] = mapped_column(String(100))
    total_state_funding: Mapped[Optional[float]] = mapped_column(Numeric(12, 2))

    # Local funding
    local_revenue: Mapped[Optional[float]] = mapped_column(Numeric(12, 2))

    # Per-pupil calculations
    total_per_pupil: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    instructional_per_pupil: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))

    # Source documentation
    data_source: Mapped[str] = mapped_column(String(50), nullable=False)
    source_url: Mapped[Optional[str]] = mapped_column(String(500))
    fiscal_year: Mapped[Optional[str]] = mapped_column(String(10))

    # Quality tracking
    notes: Mapped[Optional[str]] = mapped_column(Text)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )

    # Relationships
    district: Mapped["District"] = relationship(back_populates="funding_data")

    # Constraints and Indexes
    __table_args__ = (
        UniqueConstraint("nces_id", "year", "data_source", name="uq_district_funding"),
        Index("ix_funding_nces_id", "nces_id"),
        Index("ix_funding_year", "year"),
        Index("ix_funding_state", "state"),
        Index("ix_funding_data_source", "data_source"),
    )

    def __repr__(self) -> str:
        return f"<DistrictFunding {self.nces_id}/{self.year}: {self.data_source}>"


class CALCFFFunding(Base):
    """
    California-specific LCFF (Local Control Funding Formula) data.

    Contains detailed breakdown of California's equity-based funding formula.
    Source: CA CDE LCFF Summary Data Files
    """
    __tablename__ = "ca_lcff_funding"

    # Primary key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Foreign key
    nces_id: Mapped[str] = mapped_column(
        String(10), ForeignKey("districts.nces_id", ondelete="CASCADE"), nullable=False
    )

    # Source tracking
    year: Mapped[str] = mapped_column(String(10), nullable=False)

    # LCFF Components
    base_grant: Mapped[Optional[float]] = mapped_column(Numeric(12, 2))
    supplemental_grant: Mapped[Optional[float]] = mapped_column(Numeric(12, 2))
    concentration_grant: Mapped[Optional[float]] = mapped_column(Numeric(12, 2))
    total_lcff: Mapped[Optional[float]] = mapped_column(Numeric(12, 2))

    # Funded ADA (Average Daily Attendance)
    funded_ada: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))

    # Unduplicated Pupil Count (UPC) - for supplemental/concentration grants
    unduplicated_pupil_count: Mapped[Optional[int]] = mapped_column(Integer)
    upc_percentage: Mapped[Optional[float]] = mapped_column(Numeric(10, 6))

    # Grade span breakdowns
    base_tk_3: Mapped[Optional[float]] = mapped_column(Numeric(12, 2))
    base_4_6: Mapped[Optional[float]] = mapped_column(Numeric(12, 2))
    base_7_8: Mapped[Optional[float]] = mapped_column(Numeric(12, 2))
    base_9_12: Mapped[Optional[float]] = mapped_column(Numeric(12, 2))

    # Source documentation
    data_source: Mapped[str] = mapped_column(String(50), default="ca_cde_lcff")
    source_url: Mapped[Optional[str]] = mapped_column(String(500))

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )

    # Relationships
    district: Mapped["District"] = relationship(back_populates="ca_lcff_funding")

    # Constraints and Indexes
    __table_args__ = (
        UniqueConstraint("nces_id", "year", name="uq_ca_lcff_funding"),
        CheckConstraint("upc_percentage BETWEEN 0 AND 1", name="chk_upc_percentage"),
        Index("ix_lcff_nces_id", "nces_id"),
        Index("ix_lcff_year", "year"),
    )

    def __repr__(self) -> str:
        return f"<CALCFFFunding {self.nces_id}/{self.year}: ${self.total_lcff:,.0f}>"
