# infrastructure/database/models.py
"""
SQLAlchemy ORM models for Learning Connection Time project.

These models map to the PostgreSQL tables defined in schema.sql.
They provide Pythonic access to database records with validation and relationships.
"""

from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


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
    enrollment: Mapped[Optional[int]] = mapped_column(Integer)
    instructional_staff: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    total_staff: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    schools_count: Mapped[Optional[int]] = mapped_column(Integer)
    year: Mapped[str] = mapped_column(String(10), nullable=False)
    data_source: Mapped[str] = mapped_column(String(50), default="nces_ccd")

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
