from __future__ import annotations

import datetime
from collections.abc import Sequence
from typing import ClassVar, Literal, NewType, Self, overload

from aiohttp import ClientSession
from sqlalchemy import ForeignKey, Index, func, null, select, tuple_
from sqlalchemy.orm import (
    Mapped,
    Session,
    aliased,
    mapped_column,
    relationship,
)
from sqlalchemy.schema import UniqueConstraint

from .. import timezone
from ..baseunit_api import DEFAULT_REQUEST_OPTIONS
from ..temperature_history import (
    SensorReading as SensorReadingData,
)
from ..temperature_history import (
    TemperatureHistory as TemperatureHistoryData,
)
from ..timezone import ensure_aware
from ..types import (
    AioHttpRequestOptions,
    AuthInfo,
    BaseUnitInfo,
    BaseUnitStatusErrorCode,
    PowerManagementInfo,
    PowerMode,
    PowerModeStatus,
    SensorType,
)
from ..types import (
    BaseUnitIdentity as BaseUnitIdentityData,
)
from ..types import (
    BaseUnitStatus as BaseUnitStatusData,
)
from ..types import (
    BaseUnitUsageStatus as BaseUnitUsageStatusData,
)
from ..utils import click_secho
from .base import Base
from .types import (
    CompoundSelectOf,
    LocationSiblingType,
    Ordering,
    RelationshipNaturalKey,
    SelectOf,
    _BaseModelSerializeTD,
)
from .utils import get_count_for_select

DtIsoStr = NewType("DtIsoStr", str)

type LocationTypeNaturalKey = str
type LocationNaturalKey = tuple[str, ...]
type BaseUnitNaturalKey = str
type BaseUnitOnlineStatusNaturalKey = tuple[BaseUnitNaturalKey, int]
type BaseUnitIdentityNaturalKey = BaseUnitNaturalKey
type PowerManagementStatusNaturalKey = tuple[BaseUnitNaturalKey, int]
type PowerManagementSettingsNaturalKey = BaseUnitNaturalKey
type BaseUnitStatusNaturalKey = tuple[BaseUnitNaturalKey, int]
type BaseUnitUsageStatusNaturalKey = tuple[BaseUnitNaturalKey, int]
type SensorReadingNaturalKey = tuple[BaseUnitNaturalKey, int]

class _LocationTypeSerializeTD(_BaseModelSerializeTD[LocationTypeNaturalKey]):
    name: str


class _LocationSerializeTD(_BaseModelSerializeTD[LocationNaturalKey]):
    name: str
    description: str|None
    parent_location_pathlist: LocationNaturalKey|None
    location_type: RelationshipNaturalKey[LocationTypeNaturalKey]|None


class _BaseUnitSerializeTD(_BaseModelSerializeTD[BaseUnitNaturalKey]):
    ip_address: str
    hostname: str
    room_name: str
    location: RelationshipNaturalKey[LocationNaturalKey]|None

class _BaseUnitOnlineStatusSerializeTD(_BaseModelSerializeTD[BaseUnitOnlineStatusNaturalKey]):
    base_unit: RelationshipNaturalKey[BaseUnitNaturalKey]
    timestamp: DtIsoStr
    online: bool
    uploaded_to_influx: bool

class _BaseUnitIdentitySerializeTD(_BaseModelSerializeTD[BaseUnitIdentityNaturalKey]):
    base_unit: RelationshipNaturalKey[BaseUnitNaturalKey]
    article_number: str
    hardware_version: str
    model_name: str
    product_name: str
    serial_number: str

class _PowerManagementStatusSerializeTD(_BaseModelSerializeTD[PowerManagementStatusNaturalKey]):
    base_unit: RelationshipNaturalKey[BaseUnitNaturalKey]
    timestamp: DtIsoStr
    power_mode_status: PowerModeStatus
    uploaded_to_influx: bool


class _PowerManagementSettingsSerializeTD(_BaseModelSerializeTD[PowerManagementSettingsNaturalKey]):
    base_unit: RelationshipNaturalKey[BaseUnitNaturalKey]
    mode: PowerMode
    standby_timeout: int|None


class _BaseUnitStatusSerializeTD(_BaseModelSerializeTD[BaseUnitStatusNaturalKey]):
    base_unit: RelationshipNaturalKey[BaseUnitNaturalKey]
    timestamp: DtIsoStr
    current_uptime: int
    total_uptime: int
    error_code: BaseUnitStatusErrorCode
    error_message: str|None
    first_used: DtIsoStr
    in_use: bool
    sharing: bool
    uploaded_to_influx: bool


class _SensorReadingSerializeTD(_BaseModelSerializeTD[SensorReadingNaturalKey]):
    base_unit: RelationshipNaturalKey[BaseUnitNaturalKey]
    timestamp: DtIsoStr
    sensor_type: SensorType
    value: float
    uploaded_to_influx: bool


class _BaseUnitUsageStatusSerializeTD(_BaseModelSerializeTD[BaseUnitUsageStatusNaturalKey]):
    base_unit: RelationshipNaturalKey[BaseUnitNaturalKey]
    timestamp: DtIsoStr
    in_use: bool
    sharing: bool
    uploaded_to_influx: bool


class LocationType(Base[LocationTypeNaturalKey, _LocationTypeSerializeTD]):
    """ORM model for a type of Location, which can be used to categorize :class:`Location` instances
    (e.g. "Building", "Floor", "Room", etc.)
    """
    __tablename__ = "location_types"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(unique=True, nullable=False)
    """Name of the location type"""
    locations: Mapped[list[Location]] = relationship(
        back_populates="location_type",
        lazy="selectin",
    )
    """The list of Location instances that have this location type"""

    @overload
    @classmethod
    def get_by_name(cls, name: str, session: Session, raise_if_not_found: Literal[True]) -> Self:
        ...
    @overload
    @classmethod
    def get_by_name(cls, name: str, session: Session, raise_if_not_found: Literal[False] = False) -> Self|None:
        ...
    @classmethod
    def get_by_name(cls, name: str, session: Session, raise_if_not_found: bool = False) -> Self|None:
        """Get a LocationType by its name"""
        stmt = select(cls).where(cls.name == name)
        if raise_if_not_found:
            return session.execute(stmt).scalar_one()
        return session.execute(stmt).scalar_one_or_none()

    @property
    def natural_key(self) -> LocationTypeNaturalKey:
        """The natural key for this instance"""
        return self.name

    @classmethod
    def select_by_natural_key(cls, key: LocationTypeNaturalKey) -> SelectOf[Self]:
        """Get a select statement to retrieve a model instance by its natural key
        """
        return select(cls).where(cls.name == key)

    def serialize(self) -> _LocationTypeSerializeTD:
        """Serialize this instance to a dictionary for JSON serialization"""
        return _LocationTypeSerializeTD(
            natural_key=self.natural_key,
            name=self.name,
        )

    @classmethod
    def deserialize(cls, data: _LocationTypeSerializeTD, session: Session) -> Self|None:
        """Deserialize a dictionary into an instance of this model"""
        instance = cls(
            name=data["name"],
        )
        return instance

    def __repr__(self) -> str:
        return f"<LocationType(id={self.id}, name={self.name})>"

    def __str__(self) -> str:
        return f"LocationType '{self.name}'"


class Location(Base[LocationNaturalKey, _LocationSerializeTD]):
    """ORM model for a physical location where ClickShare BaseUnits are located

    This model uses a self-referential relationship to represent a hierarchy of
    locations, where each Location can have a :attr:`parent_location` and multiple :attr:`child_locations`.

    The hierarchy can be of arbitrary depth, allowing for flexible organization
    of locations (e.g. building -> floor -> room).
    """
    __tablename__ = "locations"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(nullable=False)
    """Name of the location"""
    location_type_id: Mapped[int|None] = mapped_column(ForeignKey("location_types.id"), nullable=True)
    location_type: Mapped[LocationType|None] = relationship(
        back_populates="locations",
        lazy="selectin",
    )
    """The type of the location, or None if no type is assigned"""
    parent_location_id: Mapped[int|None] = mapped_column(ForeignKey("locations.id"), nullable=True)
    parent_location: Mapped[Location|None] = relationship(
        remote_side=[id],
        back_populates="child_locations",
        lazy="selectin",
    )
    """The parent location of this location, or None if this location has no parent"""
    child_locations: Mapped[list[Location]] = relationship(
        back_populates="parent_location",
        cascade="all, delete-orphan",
    )
    """The list of child locations that have this location as their parent"""

    description: Mapped[str|None] = mapped_column(nullable=True)
    """Description of the location"""

    base_units: Mapped[list[BaseUnit]] = relationship(
        back_populates="location",
        passive_deletes=True,
    )
    """The list of :class:`BaseUnit` instances at this location"""

    __table_args__ = (
        # Unique constraint to ensure that there are no duplicate location
        # names with the same parent location.
        #
        # A typical `UniqueConstraint` can't be used here because of the
        # nullable `parent_location_id`.
        # We have to use a unique index on the coalesced value of `parent_location_id`
        # to treat NULL as a distinct value for the purposes of uniqueness.
        Index(
            "uix_name_parent_coalesce",
            "name",
            func.coalesce(parent_location_id, 0),
            unique=True
        ),
    )

    PATH_DELIMITER: ClassVar[str] = " -> "
    """Delimiter used to separate location names in the full path of a location"""

    @property
    def location_type_name(self) -> str|None:
        """The name of the :attr:`location_type` of this location, if one is assigned"""
        return self.location_type.name if self.location_type is not None else None

    @property
    def is_root(self) -> bool:
        """Whether this location is a root location (i.e. has no parent location)"""
        return self.parent_location is None

    @property
    def root_location(self) -> Location:
        """The root location of this location (i.e. the top-level parent location)"""
        if self.parent_location is None:
            return self
        return self.parent_location.root_location

    @property
    def nest_level(self) -> int:
        """The nest level of this location, where root locations have a nest level of 0,
        their children have a nest level of 1, and so on.
        """
        if self.parent_location is None:
            return 0
        return self.parent_location.nest_level + 1

    @property
    def pathlist(self) -> tuple[str, ...]:
        """The full path of this location as a list of location names.

        Starts with the top-level parent location and ends with this location.
        """
        if self.parent_location is None:
            return (self.name,)
        return self.parent_location.pathlist + (self.name,)

    @property
    def path(self) -> str:
        """The full path of this location, including parent locations,
        separated by :attr:`PATH_DELIMITER`.

        For example, a location with name "Room 101" and a parent location with name
        "First Floor" would have a path of "First Floor -> Room 101".
        """
        return self.join_pathlist(*self.pathlist)

    @classmethod
    def join_pathlist(cls, *names: str) -> str:
        """Join a list of location names into a full path string using the
        :attr:`PATH_DELIMITER`
        """
        return cls.PATH_DELIMITER.join(names)

    @classmethod
    def split_path(cls, path: str) -> tuple[str, ...]:
        """Split a full path string into a list of location names using the
        :attr:`PATH_DELIMITER`

        This is the inverse of :func:`join_pathlist`, so that for any list of names, calling
        ``split_path(join_pathlist(*names))`` will return the original list of names.
        """
        return tuple(part for part in path.split(cls.PATH_DELIMITER))

    @overload
    @classmethod
    def get_by_id(cls, location_id: int, session: Session, raise_if_absent: Literal[True]) -> Self:
        ...
    @overload
    @classmethod
    def get_by_id(cls, location_id: int, session: Session, raise_if_absent: Literal[False] = False) -> Self|None:
        ...
    @classmethod
    def get_by_id(cls, location_id: int, session: Session, raise_if_absent: bool = False) -> Self|None:
        """Get a Location by its ID

        Arguments:
            location_id: The ID of the Location to get
            session: The SQLAlchemy session to use for database operations
            raise_if_absent: Whether to raise an exception if no Location with the given ID is found

        Returns:
            The Location instance with the given ID, or None if no such Location exists
                and ``raise_if_absent`` is False

        Raises:
            sqlalchemy.exc.NoResultFound: If no Location with the given ID
                exists and *raise_if_absent* is True
        """
        stmt = select(cls).where(cls.id == location_id)
        if raise_if_absent:
            return session.execute(stmt).scalar_one()
        return session.execute(stmt).scalar_one_or_none()

    @classmethod
    def get_by_location_type(cls, location_type: LocationType|str, session: Session) -> Sequence[Self]:
        """Get a list of Location instances that have the given location type

        Arguments:
            location_type: The LocationType instance or name to filter by
            session: The SQLAlchemy session to use for database operations

        Returns:
            A list of Location instances that have the given location type
        """
        if isinstance(location_type, str):
            location_type = LocationType.get_by_name(
                location_type,
                session=session,
                raise_if_not_found=True,
            )
        return session.execute(
            select(cls).where(cls.location_type_id == location_type.id)
        ).scalars().all()

    @classmethod
    def create_from_pathlist(cls, *names: str, session: Session) -> Self:
        """Create a Location and any necessary parent Locations from a list of
        location names

        Each name given in the arguments (variable-length) will be used to either
        find an existing Location with that name and the appropriate parent location, or
        create a new one if it doesn't already exist.

        Arguments:
            *names: A variable number of location names, starting with the
                top-level parent location and ending with the desired location
                to create
            session: The SQLAlchemy session to use for database operations

        Returns:
            The Location instance corresponding to the last name in the list,
            which is the desired location to create
        """
        if not len(names):
            raise ValueError("At least one location name must be provided")
        with session.begin_nested():
            parent_location = None
            for name in names:
                parent_id = parent_location.id if parent_location is not None else None
                location = session.execute(
                    select(cls).where(
                        cls.name == name,
                        cls.parent_location_id == parent_id,
                    )
                ).scalar_one_or_none()
                if location is None:
                    location = cls(name=name, parent_location=parent_location)
                    session.add(location)
                    session.flush()
                parent_location = location
            assert parent_location is not None
            return parent_location

    @classmethod
    def get_by_pathlist(cls, *names: str, session: Session) -> Self|None:
        """Get a Location by its pathlist

        This is similar to :meth:`create_from_pathlist`, but it only searches
        for existing Locations and does not create any new ones.
        If any location in the path does not exist, None is returned.

        Arguments:
            *names: A variable number of location names, starting with the
                top-level parent location and ending with the desired location to get
            session: The SQLAlchemy session to use for database operations

        Returns:
            The Location instance corresponding to the last name in the list,
            or None if no such Location exists
        """
        if not len(names):
            raise ValueError("At least one location name must be provided")
        parent_location = None
        for name in names:
            parent_id = parent_location.id if parent_location is not None else None
            location = session.execute(
                select(cls).where(
                    cls.name == name,
                    cls.parent_location_id == parent_id,
                )
            ).scalar_one_or_none()
            if location is None:
                return None
            parent_location = location
        assert parent_location is not None
        return parent_location

    @classmethod
    def select_root_locations(cls) -> SelectOf[Self]:
        """Get a select statement for all root locations (i.e. locations with
        no parent location)
        """
        return select(cls).where(cls.parent_location_id.is_(None))

    @classmethod
    def get_root_locations(cls, session: Session) -> Sequence[Self]:
        """Get all root locations (i.e. locations with no parent location)
        """
        return session.execute(cls.select_root_locations()).scalars().all()

    def get_sibling_type(self, session: Session) -> LocationSiblingType:
        """Get the :type:`LocationSiblingType` of this Location among its
        siblings with the same parent location
        """
        if self.get_sibling_count(session) == 1:
            return "only"
        if self.get_is_first_child(session):
            return "first"
        elif self.get_is_last_child(session):
            return "last"
        else:
            return "middle"

    def get_is_first_child(self, session: Session) -> bool:
        """Check whether this Location is the first child of its parent location
        """
        if self.parent_location is None:
            stmt = self.select_root_locations().order_by(self.__class__.id)
            sibling_count = get_count_for_select(stmt, session=session)
            if sibling_count == 0:
                return True
            stmt = stmt.slice(0, 1)
            first_sibling = session.execute(stmt).scalar_one()
            return self.id == first_sibling.id
        first_sibling = self.parent_location.child_locations[0]
        return self.id == first_sibling.id

    def get_is_last_child(self, session: Session) -> bool:
        """Check whether this Location is the last child of its parent location
        """
        if self.parent_location is None:
            stmt = self.select_root_locations().order_by(self.__class__.id)
            sibling_count = get_count_for_select(session=session, select_stmt=stmt)
            if sibling_count == 0:
                return True
            stmt = stmt.slice(sibling_count - 1, sibling_count)
            last_sibling = session.execute(stmt).scalar_one()
            return self.id == last_sibling.id
        sibling_count = len(self.parent_location.child_locations)
        if sibling_count == 0:
            return True
        last_sibling = self.parent_location.child_locations[-1]
        return self.id == last_sibling.id

    def select_siblings(self) -> SelectOf[Self]:
        """Get a select statement for all siblings of this Location, including itself
        """
        if self.parent_location is None:
            return self.select_root_locations()
        cls = self.__class__
        return select(cls).where(cls.parent_location_id == self.parent_location_id)

    def get_sibling_count(self, session: Session) -> int:
        """Get the number of siblings of this Location, including itself
        """
        return get_count_for_select(self.select_siblings(), session=session)

    def select_ancestors(self) -> SelectOf[Self]:
        """Get a select statement for all ancestor Locations of this Location,
        starting with the parent location and ending with the top-level parent location
        """
        cls = self.__class__
        base_q = select(cls.id, cls.parent_location_id).where(cls.id == self.parent_location_id)
        cte = base_q.cte(name="ancestors", recursive=True)

        node_alias = aliased(cls, name="n")
        recursive_q = select(node_alias.id, node_alias.parent_location_id).join(
            cte, node_alias.id == cte.c.parent_location_id
        )
        cte_stmt = cte.union_all(recursive_q)
        return select(cls).join(cte_stmt, cls.id == cte_stmt.c.id)

    def select_descendants(self) -> SelectOf[Location]:
        """Get a select statement for all descendant Locations of this Location in depth-first order
        """
        cls = Location
        base_q = select(cls.id, cls.parent_location_id).where(cls.parent_location_id == self.id)
        cte = base_q.cte(name="descendants", recursive=True)

        node_alias = aliased(cls, name="n")
        recursive_q = select(node_alias.id, node_alias.parent_location_id).join(
            cte, node_alias.parent_location_id == cte.c.id
        )
        cte_stmt = cte.union_all(recursive_q)
        return select(cls).join(cte_stmt, cls.id == cte_stmt.c.id)

    def select_base_units(self, include_descendants: bool = False) -> SelectOf[BaseUnit]:
        """Get a select statement for all BaseUnits at this Location and optionally at all
        descendant Locations

        Arguments:
            include_descendants: Whether to include BaseUnits at descendant Locations

        Returns:
            A SQLAlchemy Select object for the BaseUnits at this Location and
                optionally at descendant Locations
        """
        base_q = select(Location.id).where(Location.id == self.id)
        location_ids_q: SelectOf[int] | CompoundSelectOf[int]
        if include_descendants:
            descendant_ids_q = self.select_descendants().with_only_columns(Location.id)
            location_ids_q = base_q.union_all(descendant_ids_q)
        else:
            location_ids_q = base_q
        return select(BaseUnit).where(BaseUnit.location_id.in_(location_ids_q))

    def get_base_units(self, session: Session, include_descendants: bool = False) -> Sequence[BaseUnit]:
        """Get a list of all BaseUnits at this Location and optionally at all
        descendant Locations

        Arguments:
            session: The SQLAlchemy session to use for database operations
            include_descendants: Whether to include BaseUnits at descendant Locations

        Returns:
            A list of BaseUnit instances at this Location and optionally at
                descendant Locations
        """
        stmt = self.select_base_units(include_descendants=include_descendants)
        return session.execute(stmt).scalars().all()

    @property
    def natural_key(self) -> LocationNaturalKey:
        """The natural key for this instance
        """
        return self.pathlist

    @classmethod
    def select_by_natural_key(cls, key: LocationNaturalKey) -> SelectOf[Self]:
        """Get a select statement to retrieve a model instance by its natural key
        """
        path_iter = iter(key)
        root_name = next(path_iter, None)
        if root_name is None:
            raise ValueError("Location natural key cannot be an empty pathlist")
        first_child_name = next(path_iter, None)
        if first_child_name is None:
            # Easy case: we can filter by name and parent_location_id is null
            # to get the root location with the given name
            return select(cls).where(cls.name == root_name, cls.parent_location_id.is_(None))

        # We can only filter by the full pathlist, so we have to create a complex query
        # that traverses the location hierarchy and filters by each level of the pathlist.
        root_alias = aliased(cls, name="loc_0", flat=True)
        stmt = select(root_alias).filter(
            root_alias.name == root_name,
            root_alias.parent_location_id.is_(null()),
        )
        parent_alias = root_alias
        current_alias = root_alias
        for i, name in enumerate((first_child_name, *path_iter), start=1):
            current_alias = aliased(cls, name=f"loc_{i}", flat=True)
            stmt = stmt.join(
                current_alias,
                current_alias.parent_location_id == parent_alias.id,
            ).filter(current_alias.name == name)
            parent_alias = current_alias
        return stmt.with_only_columns(current_alias)

    def serialize(self) -> _LocationSerializeTD:
        """Serialize this instance to a dictionary for JSON serialization
        """
        return _LocationSerializeTD(
            natural_key=self.natural_key,
            name=self.name,
            description=self.description,
            parent_location_pathlist=self.parent_location.pathlist if self.parent_location is not None else None,
            location_type=RelationshipNaturalKey(
                related_model_table="location_types",
                related_model_key=self.location_type.natural_key,
            ) if self.location_type is not None else None,
        )

    @classmethod
    def deserialize(cls, data: _LocationSerializeTD, session: Session) -> Self|None:
        """Deserialize a dictionary into an instance of this model
        """
        parent_location = None
        if data["parent_location_pathlist"] is not None:
            parent_location = cls.get_by_pathlist(*data["parent_location_pathlist"], session=session)
            if parent_location is None:
                return None
        location_type = None
        if data["location_type"] is not None:
            location_type = LocationType.get_by_natural_key(session, data["location_type"].related_model_key)
            if location_type is None:
                return None
        instance = cls(
            name=data["name"],
            description=data["description"],
            parent_location=parent_location,
            location_type=location_type,
        )
        return instance

    def __repr__(self) -> str:
        return f"<Location(id={self.id}, name={self.name}, path={self.path})>"

    def __str__(self) -> str:
        return f"Location '{self.path}'"


class BaseUnit(Base[BaseUnitNaturalKey, _BaseUnitSerializeTD]):
    """ORM model for a ClickShare BaseUnit
    """
    # __tablename__: ClassVar[ModelTableName] = "base_units"
    __tablename__ = "base_units"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ip_address: Mapped[str] = mapped_column(nullable=False)
    """IP address of the BaseUnit"""
    hostname: Mapped[str] = mapped_column(unique=True, nullable=False)
    """Hostname of the BaseUnit, which is used as the natural key"""
    room_name: Mapped[str] = mapped_column(nullable=False)
    """Name of the room where the BaseUnit is located"""
    location_id: Mapped[int|None] = mapped_column(
        ForeignKey("locations.id", ondelete="SET NULL"),
        nullable=True,
    )
    location: Mapped[Location|None] = relationship(back_populates="base_units")
    """The :class:`Location` for this BaseUnit, or None if no location is assigned"""

    identity: Mapped[BaseUnitIdentity] = relationship(
        uselist=False,
        back_populates="base_unit",
    )
    """The :class:`BaseUnitIdentity` associated with this BaseUnit"""

    power_management_settings: Mapped[PowerManagementSettings] = relationship(
        uselist=False,
        back_populates="base_unit",
    )
    """The :class:`PowerManagementSettings` associated with this BaseUnit"""

    online_statuses: Mapped[list[BaseUnitOnlineStatus]] = relationship(
        back_populates="base_unit",
        cascade="all, delete-orphan",
    )
    """The list of :class:`BaseUnitOnlineStatus` entries associated with this BaseUnit"""

    power_management_statuses: Mapped[list[PowerManagementStatus]] = relationship(
        back_populates="base_unit",
        cascade="all, delete-orphan",
    )
    """The list of :class:`PowerManagementStatus` entries associated with this BaseUnit"""

    statuses: Mapped[list[BaseUnitStatus]] = relationship(
        back_populates="base_unit",
        cascade="all, delete-orphan",
    )
    """The list of :class:`BaseUnitStatus` entries associated with this BaseUnit"""

    usage_statuses: Mapped[list[BaseUnitUsageStatus]] = relationship(
        back_populates="base_unit",
        cascade="all, delete-orphan",
    )
    """The list of :class:`BaseUnitUsageStatus` entries associated with this BaseUnit"""

    sensor_readings: Mapped[list[SensorReading]] = relationship(
        back_populates="base_unit",
        cascade="all, delete-orphan",
    )
    """The list of :class:`SensorReading` entries associated with this BaseUnit"""

    @property
    def location_type(self) -> LocationType|None:
        """The :class:`LocationType` of the :attr:`location` of this BaseUnit,
        or None if no location or location type is assigned
        """
        return self.location.location_type if self.location is not None else None

    @property
    def location_type_name(self) -> str|None:
        """The name of the :class:`LocationType` of the :attr:`location` of this BaseUnit,
        or None if no location or location type is assigned
        """
        return self.location_type.name if self.location_type is not None else None

    @property
    def natural_key(self) -> BaseUnitNaturalKey:
        """The natural key for this instance
        """
        return self.hostname

    @classmethod
    def select_by_natural_key(cls, key: BaseUnitNaturalKey) -> SelectOf[Self]:
        """Get a select statement to retrieve a model instance by its natural key
        """
        return select(cls).where(cls.hostname == key)

    def serialize(self) -> _BaseUnitSerializeTD:
        """Serialize this instance to a dictionary for JSON serialization
        """
        location_key = self.location.natural_key if self.location is not None else None
        return {
            "natural_key": self.natural_key,
            "ip_address": self.ip_address,
            "hostname": self.hostname,
            "room_name": self.room_name,
            "location": RelationshipNaturalKey(
                related_model_table="locations",
                related_model_key=location_key,
            ) if location_key is not None else None,
        }

    @classmethod
    def deserialize(cls, data: _BaseUnitSerializeTD, session: Session) -> Self|None:
        """Deserialize a dictionary into a an instance of this model
        """
        if data["location"] is not None:
            location = Location.get_by_natural_key(session, data["location"].related_model_key)
            if location is None:
                return None
        else:
            location = None
        return cls(
            ip_address=data["ip_address"],
            hostname=data["hostname"],
            room_name=data["room_name"],
            location=location,
        )

    @classmethod
    def from_info(cls, info: BaseUnitInfo) -> Self:
        """Create a BaseUnit ORM instance from a :class:`.types.BaseUnitInfo` instance
        """
        return cls(
            ip_address=info.ip_address,
            hostname=info.hostname,
            room_name=info.room_name,
        )

    @overload
    @classmethod
    def get_by_hostname(cls, hostname: str, session: Session, raise_if_absent: Literal[True]) -> Self:
        ...
    @overload
    @classmethod
    def get_by_hostname(cls, hostname: str, session: Session, raise_if_absent: Literal[False] = False) -> Self|None:
        ...
    @classmethod
    def get_by_hostname(cls, hostname: str, session: Session, raise_if_absent: bool = False) -> Self|None:
        """Get a BaseUnit by its hostname

        Arguments:
            hostname: The hostname of the BaseUnit to retrieve
            session: The SQLAlchemy session to use for database operations
            raise_if_absent: If True, raise a ValueError if no BaseUnit with the given hostname exists.
                If False (the default), return None instead.

        Returns:
            The BaseUnit instance with the given hostname, or None if no such
                BaseUnit exists (and *raise_if_absent* is False)

        Raises:
            sqlalchemy.exc.NoResultFound: If no BaseUnit with the given hostname
                exists and *raise_if_absent* is True
        """
        stmt = select(cls).where(cls.hostname == hostname)
        if raise_if_absent:
            return session.execute(stmt).scalar_one()
        return session.execute(stmt).scalar_one_or_none()

    @classmethod
    def get_or_create(cls, info: BaseUnitInfo, session: Session) -> tuple[Self, bool]:
        """Get a BaseUnit from the database matching the given :class:`.types.BaseUnitInfo`,
        or create it if it doesn't exist
        """
        created = False
        instance = cls.get_by_hostname(info.hostname, session=session)
        if instance is not None:
            changed = False
            if instance.ip_address != info.ip_address:
                instance.ip_address = info.ip_address
                changed = True
            if instance.room_name != info.room_name:
                instance.room_name = info.room_name
                changed = True
            if changed:
                session.add(instance)
            return instance, created
        else:
            instance = cls.from_info(info)
            created = True
            return instance, created

    def to_data(self) -> BaseUnitInfo:
        """Convert this instance into a :class:`.types.BaseUnitInfo` instance
        """
        return BaseUnitInfo(
            ip_address=self.ip_address,
            hostname=self.hostname,
            room_name=self.room_name,
        )

    def last_online_status(self) -> bool|None:
        """Get the most recent online status for this BaseUnit, or None if no statuses exist
        """
        last_status = self.last_online_status_instance()
        if last_status is None:
            return None
        return last_status.online

    def last_online_status_instance(self) -> BaseUnitOnlineStatus|None:
        """Get the most recent :class:`BaseUnitOnlineStatus` for this BaseUnit, or None if no statuses exist
        """
        session = self._get_current_orm_session()
        stmt = select(BaseUnitOnlineStatus).where(
            BaseUnitOnlineStatus.base_unit_id == self.id
        ).order_by(BaseUnitOnlineStatus.timestamp.desc()).limit(1)
        return session.execute(stmt).scalar_one_or_none()

    def set_online_status(
        self,
        online: bool,
        timestamp: datetime.datetime|None = None
    ) -> None:
        """Set the online status for this BaseUnit, creating a new
        :class:`BaseUnitOnlineStatus` entry in the database

        Arguments:
            online (bool): Whether the BaseUnit is online or offline
            timestamp (datetime.datetime|None): The timestamp for the new status entry.
                If None, the current time is used.
        """
        session = self._get_current_orm_session()
        with session.begin_nested():
            last_status = self.last_online_status()
            if last_status is not None and last_status == online:
                # No need to create a new status entry if the online status hasn't changed
                return
            if timestamp is None:
                timestamp = timezone.utcnow()
            else:
                timezone.ensure_aware(timestamp)
            online_status = BaseUnitOnlineStatus(
                base_unit_id=self.id,
                timestamp=timestamp,
                online=online,
            )
            session.add(online_status)
            session.flush()

    async def add_sensor_readings_from_api(
        self,
        auth_info: AuthInfo,
        session: Session,
        aiohttp_session: ClientSession,
        request_options: AioHttpRequestOptions|None = None,
    ) -> None:
        """Fetch sensor readings for this BaseUnit from the API and add them to the database
        """
        request_options = request_options or DEFAULT_REQUEST_OPTIONS
        temperature_history_data = await TemperatureHistoryData.from_baseunit(
            self.ip_address,
            auth_info=auth_info,
            session=aiohttp_session,
            **request_options,
        )
        dt_sensor_keys = {
            (timezone.ensure_aware(r.timestamp), r.sensor)
            for r in temperature_history_data.readings
        }

        existing_readings = session.execute(
            select(SensorReading).where(
                SensorReading.base_unit_id == self.id,
                tuple_(SensorReading.timestamp, SensorReading.sensor_type).in_(dt_sensor_keys),
            )
        ).scalars().all()
        existing_keys = {(r.timestamp, r.sensor_type) for r in existing_readings}
        click_secho(f"Fetched {len(temperature_history_data.readings)} sensor readings for BaseUnit '{self.hostname}'", fg="blue")
        num_added = 0
        for reading in temperature_history_data.readings:
            key = (timezone.ensure_aware(reading.timestamp), reading.sensor)
            if key in existing_keys:
                continue
            instance = self.add_sensor_reading(reading, session)
            session.add(instance)
            num_added += 1
        click_secho(f"Added {num_added} sensor readings for BaseUnit '{self.hostname}' to the database", fg="green")

    def add_sensor_readings(
        self,
        readings: list[SensorReadingData[SensorType]],
        session: Session
    ) -> tuple[int, int]:
        """Add multiple sensor readings to this BaseUnit

        Returns:
            A tuple of (num_added, num_skipped) indicating how many readings
                were added and how many were skipped due to already existing in the database.
        """
        dt_sensor_keys = {
            (timezone.ensure_aware(r.timestamp), r.sensor)
            for r in readings
        }
        existing_readings = session.execute(
            select(SensorReading).where(
                SensorReading.base_unit_id == self.id,
                tuple_(SensorReading.timestamp, SensorReading.sensor_type).in_(dt_sensor_keys),
            )
        ).scalars().all()
        existing_keys = {(r.timestamp, r.sensor_type) for r in existing_readings}
        num_added = 0
        num_skipped = 0
        for reading in readings:
            key = (timezone.ensure_aware(reading.timestamp), reading.sensor)
            if key in existing_keys:
                num_skipped += 1
                continue
            instance = self.add_sensor_reading(reading, session)
            assert not instance.uploaded_to_influx, "New sensor reading should not be marked as uploaded to InfluxDB"
            session.add(instance)
            num_added += 1
        return num_added, num_skipped

    def add_sensor_reading(self, reading: SensorReadingData[SensorType], session: Session) -> SensorReading:
        """Add a :class:`SensorReading` to this BaseUnit."""
        sensor_reading = SensorReading.from_data(self, reading, session)
        session.add(sensor_reading)
        return sensor_reading

    def has_sensor_reading(self, reading: SensorReadingData[SensorType], session: Session) -> bool:
        """Check if a :class:`SensorReading` already exists for this BaseUnit

        The reading's timestamp and sensor type are used to determine if it
        already exists in the database.
        """
        timestamp = timezone.ensure_aware(reading.timestamp)
        existing_reading = session.execute(
            select(SensorReading).where(
                SensorReading.base_unit_id == self.id,
                SensorReading.timestamp == timestamp,
                SensorReading.sensor_type == reading.sensor,
            )
        ).scalars().one_or_none()
        return existing_reading is not None

    def select_sensor_readings(
        self,
        sensor_type: SensorType|None = None,
        order_by: Ordering|None = None
    ) -> SelectOf[SensorReading]:
        """Get a select statement for sensor readings for this BaseUnit, optionally filtered by sensor type
        """
        stmt = select(SensorReading).where(SensorReading.base_unit_id == self.id)
        if sensor_type is not None:
            stmt = stmt.where(SensorReading.sensor_type == sensor_type)
        if order_by == "desc":
            stmt = stmt.order_by(SensorReading.timestamp.desc())
        elif order_by == "asc":
            stmt = stmt.order_by(SensorReading.timestamp.asc())
        return stmt

    def to_temperature_history_data(
        self,
        session: Session,
        sensor_select: SelectOf[SensorReading]|None = None
    ) -> TemperatureHistoryData:
        """Convert this BaseUnit and its sensor readings to a
        :class:`.temperature_history.TemperatureHistory` instance
        """
        if sensor_select is None:
            sensor_select = self.select_sensor_readings()
        results = session.execute(sensor_select).scalars().all()
        readings = [
            r.to_data() for r in results
        ]
        return TemperatureHistoryData(
            base_unit=self.to_data(),
            readings=readings,
        )

    def __repr__(self) -> str:
        return f"<BaseUnit(id={self.id}, ip_address={self.ip_address}, hostname={self.hostname}, room_name={self.room_name})>"

    def __str__(self) -> str:
        return f"BaseUnit '{self.room_name}' ({self.hostname}) - {self.ip_address}"



class BaseUnitOnlineStatus(Base[BaseUnitOnlineStatusNaturalKey, _BaseUnitOnlineStatusSerializeTD]):
    """ORM model for the online status of a ClickShare BaseUnit at a given point in time
    """
    __tablename__ = "base_unit_online_statuses"
    __table_args__ = (
        UniqueConstraint("base_unit_id", "timestamp", name="uix_base_unit_online_status_base_unit_timestamp"),
    )
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime.datetime] = mapped_column(index=True, nullable=False)
    """Timestamp of the online status entry"""
    online: Mapped[bool] = mapped_column(nullable=False)
    """Whether the BaseUnit is online (True) or offline (False)"""
    uploaded_to_influx: Mapped[bool] = mapped_column(nullable=False, default=False)
    """Whether this status entry has been uploaded to InfluxDB"""
    last_upload_to_influx: Mapped[datetime.datetime|None] = mapped_column(nullable=True)
    """The timestamp of the last time this status entry was uploaded to InfluxDB,
    or None if it has never been uploaded

    This field can be used to ensure there is a record within a certain time range
    to avoid gaps in the time series data in InfluxDB, even if the online
    status hasn't changed.
    """
    base_unit_id: Mapped[int] = mapped_column(ForeignKey("base_units.id"), nullable=False)

    base_unit: Mapped[BaseUnit] = relationship(back_populates="online_statuses")
    """The :class:`BaseUnit` that this instance is associated with"""

    @property
    def natural_key(self) -> BaseUnitOnlineStatusNaturalKey:
        """Get the natural key for this instance
        """
        return (
            self.base_unit.natural_key,
            self.id,
        )

    @classmethod
    def select_by_natural_key(cls, key: BaseUnitOnlineStatusNaturalKey) -> SelectOf[Self]:
        """Get a select statement to retrieve a model instance by its natural key
        """
        base_unit_hostname, pk = key
        return select(cls).join(BaseUnit).filter(
            BaseUnit.hostname == base_unit_hostname,
            cls.id == pk,
        )

    def serialize(self) -> _BaseUnitOnlineStatusSerializeTD:
        """Serialize this instance to a dictionary for JSON serialization
        """
        return _BaseUnitOnlineStatusSerializeTD(
            natural_key=self.natural_key,
            base_unit=RelationshipNaturalKey(
                related_model_table="base_units",
                related_model_key=self.base_unit.natural_key,
            ),
            timestamp=DtIsoStr(self.timestamp.isoformat()),
            online=self.online,
            uploaded_to_influx=self.uploaded_to_influx,
        )

    @classmethod
    def deserialize(cls, data: _BaseUnitOnlineStatusSerializeTD, session: Session) -> Self|None:
        """Deserialize a dictionary into an instance of this model
        """
        assert isinstance(data["base_unit"], RelationshipNaturalKey), f"Expected 'base_unit' to be a RelationshipNaturalKey, got {data['base_unit']}"
        base_unit = BaseUnit.get_by_natural_key(session, data["base_unit"].related_model_key)
        if base_unit is None:
            return None
        return cls(
            base_unit_id=base_unit.id,
            timestamp=timezone.ensure_aware(datetime.datetime.fromisoformat(data["timestamp"])),
            online=data["online"],
            uploaded_to_influx=data["uploaded_to_influx"],
        )

    def __repr__(self) -> str:
        return f"<BaseUnitOnlineStatus(id={self.id}, base_unit={self.base_unit}, timestamp={self.timestamp}, online={self.online})>"

    def __str__(self) -> str:
        return f"BaseUnitOnlineStatus for {self.base_unit} at {self.timestamp}: {'Online' if self.online else 'Offline'}"


class BaseUnitIdentity(Base[BaseUnitIdentityNaturalKey, _BaseUnitIdentitySerializeTD]):
    """ORM model for the identity information of a ClickShare BaseUnit
    """
    __tablename__ = "base_unit_identities"
    __table_args__ = (
        UniqueConstraint("serial_number", name="uix_serial_number"),
    )
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    base_unit_id: Mapped[int] = mapped_column(ForeignKey("base_units.id"), unique=True, nullable=False)
    article_number: Mapped[str]
    """Article number of the BaseUnit (e.g. "R9861622US")"""

    hardware_version: Mapped[str]
    """Hardware version of the BaseUnit"""

    model_name: Mapped[str]
    """Model name of the BaseUnit (e.g. "C50118")"""

    product_name: Mapped[str]
    """Product name of the BaseUnit (e.g. "CX-50")"""

    serial_number: Mapped[str]
    """Serial number of the BaseUnit"""

    base_unit: Mapped[BaseUnit] = relationship(back_populates="identity")
    """The :class:`BaseUnit` that this instance is associated with"""

    @property
    def natural_key(self) -> BaseUnitIdentityNaturalKey:
        """Get the natural key for this instance
        """
        return self.base_unit.natural_key

    @classmethod
    def select_by_natural_key(cls, key: BaseUnitIdentityNaturalKey) -> SelectOf[Self]:
        """Get a select statement to retrieve a model instance by its natural key
        """
        return select(cls).join(BaseUnit).filter(
            BaseUnit.hostname == key,
        )

    def serialize(self) -> _BaseUnitIdentitySerializeTD:
        """Serialize this instance to a dictionary for JSON serialization
        """
        return {
            "natural_key": self.natural_key,
            "base_unit": RelationshipNaturalKey(
                related_model_table="base_units",
                related_model_key=self.base_unit.natural_key,
            ),
            "article_number": self.article_number,
            "hardware_version": self.hardware_version,
            "model_name": self.model_name,
            "product_name": self.product_name,
            "serial_number": self.serial_number,
        }

    @classmethod
    def deserialize(cls, data: _BaseUnitIdentitySerializeTD, session: Session) -> Self|None:
        """Deserialize a dictionary into a an instance of this model
        """
        assert isinstance(data["base_unit"], RelationshipNaturalKey), f"Expected 'base_unit' to be a RelationshipNaturalKey, got {data['base_unit']}"
        base_unit = BaseUnit.get_by_natural_key(session, data["base_unit"].related_model_key)
        if base_unit is None:
            return None
        return cls(
            base_unit_id=base_unit.id,
            article_number=data["article_number"],
            hardware_version=data["hardware_version"],
            model_name=data["model_name"],
            product_name=data["product_name"],
            serial_number=data["serial_number"],
        )

    @classmethod
    def from_data(cls, base_unit: int|BaseUnit, data: BaseUnitIdentityData, session: Session) -> Self:
        """Create an instance of this model from a :class:`.types.BaseUnitIdentityData` instance
        """
        if isinstance(base_unit, BaseUnit):
            base_unit = base_unit.id
        return cls(
            base_unit_id=base_unit,
            article_number=data.article_number,
            hardware_version=data.hardware_version,
            model_name=data.model_name,
            product_name=data.product_name,
            serial_number=data.serial_number,
        )

    def to_data(self) -> BaseUnitIdentityData:
        """Convert this instance to a :class:`.types.BaseUnitIdentityData` instance
        """
        return BaseUnitIdentityData(
            article_number=self.article_number,
            hardware_version=self.hardware_version,
            model_name=self.model_name,
            product_name=self.product_name,
            serial_number=self.serial_number,
        )

    def __repr__(self) -> str:
        return f"<BaseUnitIdentity(id={self.id}, base_unit={self.base_unit})>"

    def __str__(self) -> str:
        return f"BaseUnitIdentity for {self.base_unit}"




class PowerManagementSettings(Base[PowerManagementSettingsNaturalKey, _PowerManagementSettingsSerializeTD]):
    """ORM model for the power management settings of a ClickShare BaseUnit
    """
    __tablename__ = "power_management_settings"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    base_unit_id: Mapped[int] = mapped_column(ForeignKey("base_units.id"), unique=True, nullable=False)
    mode: Mapped[PowerMode]
    """The power management :type:`mode <.types.PowerMode>` of the BaseUnit

    This can be one of "EcoStandby", "NetworkedStandby", or "DeepStandby".
    """

    standby_timeout: Mapped[int|None]
    """The standby timeout in minutes for the BaseUnit

    The possible values are listed in :type:`.types.PowerStandbyTimeout` except
    in the case of "Infinite" which is represented as None for this field.
    """

    base_unit: Mapped[BaseUnit] = relationship(back_populates="power_management_settings")
    """The :class:`BaseUnit` that this instance is associated with"""


    @property
    def natural_key(self) -> PowerManagementSettingsNaturalKey:
        """Get the natural key for this instance
        """
        return self.base_unit.natural_key

    @classmethod
    def select_by_natural_key(cls, key: PowerManagementSettingsNaturalKey) -> SelectOf[Self]:
        """Get a select statement to retrieve a model instance by its natural key
        """
        return select(cls).join(BaseUnit).filter(
            BaseUnit.hostname == key,
        )

    def serialize(self) -> _PowerManagementSettingsSerializeTD:
        """Serialize this instance to a dictionary for JSON serialization
        """
        return {
            "natural_key": self.natural_key,
            "base_unit": RelationshipNaturalKey(
                related_model_table="base_units",
                related_model_key=self.base_unit.natural_key,
            ),
            "mode": self.mode,
            "standby_timeout": self.standby_timeout,
        }

    @classmethod
    def deserialize(cls, data: _PowerManagementSettingsSerializeTD, session: Session) -> Self|None:
        """Deserialize a dictionary into a an instance of this model
        """
        assert isinstance(data["base_unit"], RelationshipNaturalKey), f"Expected 'base_unit' to be a RelationshipNaturalKey, got {data['base_unit']}"
        base_unit = BaseUnit.get_by_natural_key(session, data["base_unit"].related_model_key)
        if base_unit is None:
            return None
        return cls(
            base_unit_id=base_unit.id,
            mode=data["mode"],
            standby_timeout=data["standby_timeout"],
        )

    @classmethod
    def from_data(cls, base_unit: int|BaseUnit, data: PowerManagementInfo, session: Session) -> Self:
        """Create an instance of this model from a :class:`.types.PowerManagementInfo` instance
        """
        if isinstance(base_unit, BaseUnit):
            base_unit = base_unit.id
        return cls(
            base_unit_id=base_unit,
            mode=data.power_mode,
            standby_timeout=data.standby_timeout_minutes,
        )

    def update_from_data(self, data: PowerManagementInfo) -> bool:
        """Update this instance from a :class:`.types.PowerManagementInfo` instance

        Returns:
            bool: True if any fields were updated, False otherwise
        """
        changed = False
        if self.mode != data.power_mode:
            self.mode = data.power_mode
            changed = True

        if self.standby_timeout != data.standby_timeout_minutes:
            self.standby_timeout = data.standby_timeout_minutes
            changed = True
        return changed

    def __repr__(self) -> str:
        return f"<PowerManagementSettings(id={self.id}, base_unit={self.base_unit}, mode={self.mode}, standby_timeout={self.standby_timeout})>"

    def __str__(self) -> str:
        return f"PowerManagementSettings for {self.base_unit}"




class PowerManagementStatus(Base[PowerManagementStatusNaturalKey, _PowerManagementStatusSerializeTD]):
    """ORM model for the power state of a ClickShare BaseUnit at a given point in time
    """
    __tablename__ = "power_management_status"
    __table_args__ = (
        UniqueConstraint("base_unit_id", "timestamp", name="uix_power_management_status_base_unit_timestamp"),
    )
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    base_unit_id: Mapped[int] = mapped_column(ForeignKey("base_units.id"), nullable=False)
    timestamp: Mapped[datetime.datetime] = mapped_column(index=True, nullable=False)
    """Timestamp of the power management status entry"""

    power_mode_status: Mapped[PowerModeStatus]
    """The :type:`power mode status <.types.PowerModeStatus>` of the BaseUnit

    This can be one of "On" or "Standby".
    """

    uploaded_to_influx: Mapped[bool] = mapped_column(nullable=False, default=False)
    """Whether this status entry has been uploaded to InfluxDB"""

    base_unit: Mapped[BaseUnit] = relationship(back_populates="power_management_statuses")
    """The :class:`BaseUnit` that this instance is associated with"""

    @property
    def natural_key(self) -> PowerManagementStatusNaturalKey:
        """Get the natural key for this instance
        """
        return (
            self.base_unit.natural_key,
            self.id,
        )

    @classmethod
    def select_by_natural_key(cls, key: PowerManagementStatusNaturalKey) -> SelectOf[Self]:
        """Get a select statement to retrieve a model instance by its natural key
        """
        base_unit_key, pk = key
        return select(cls).join(BaseUnit).filter(
            BaseUnit.hostname == base_unit_key,
            cls.id == pk,
        )

    def serialize(self) -> _PowerManagementStatusSerializeTD:
        """Serialize this instance to a dictionary for JSON serialization
        """
        return {
            "natural_key": self.natural_key,
            "base_unit": RelationshipNaturalKey(
                related_model_table="base_units",
                related_model_key=self.base_unit.natural_key,
            ),
            "timestamp": DtIsoStr(self.timestamp.isoformat()),
            "power_mode_status": self.power_mode_status,
            "uploaded_to_influx": self.uploaded_to_influx,
        }

    @classmethod
    def deserialize(cls, data: _PowerManagementStatusSerializeTD, session: Session) -> Self|None:
        """Deserialize a dictionary into an instance of this model
        """
        assert isinstance(data["base_unit"], RelationshipNaturalKey), f"Expected 'base_unit' to be a RelationshipNaturalKey, got {data['base_unit']}"
        base_unit = BaseUnit.get_by_natural_key(session, data["base_unit"].related_model_key)
        if base_unit is None:
            return None
        return cls(
            base_unit_id=base_unit.id,
            timestamp=timezone.ensure_aware(datetime.datetime.fromisoformat(data["timestamp"])),
            power_mode_status=data["power_mode_status"],
            uploaded_to_influx=data["uploaded_to_influx"],
        )

    @classmethod
    def from_data(cls, base_unit: int|BaseUnit, data: PowerManagementInfo, now: datetime.datetime|None = None) -> Self:
        """Create an instance of this model from a :class:`.types.PowerManagementInfo` instance
        """
        if isinstance(base_unit, BaseUnit):
            base_unit = base_unit.id
        if now is None:
            now = timezone.utcnow()
        else:
            timezone.ensure_aware(now)
        return cls(
            base_unit_id=base_unit,
            timestamp=now,
            power_mode_status=data.status,
        )

    def __repr__(self) -> str:
        return f"<PowerManagementStatus(id={self.id}, base_unit={self.base_unit}, timestamp={self.timestamp}, power_mode_status={self.power_mode_status})>"

    def __str__(self) -> str:
        return f"PowerManagementStatus for {self.base_unit} at {self.timestamp}: {self.power_mode_status}"


class BaseUnitStatus(Base[BaseUnitStatusNaturalKey, _BaseUnitStatusSerializeTD]):
    """ORM model for the status of a ClickShare BaseUnit at a given point in time
    """
    __tablename__ = "base_unit_statuses"
    __table_args__ = (
        UniqueConstraint("base_unit_id", "timestamp", name="uix_base_unit_timestamp"),
    )
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime.datetime] = mapped_column(index=True, nullable=False)
    """Timestamp of the status entry"""

    base_unit_id: Mapped[int] = mapped_column(ForeignKey("base_units.id"), nullable=False)
    current_uptime: Mapped[int] = mapped_column(nullable=False)
    """The current uptime of the BaseUnit in seconds"""

    total_uptime: Mapped[int] = mapped_column(nullable=False)
    """The total uptime of the BaseUnit in seconds"""

    error_code: Mapped[BaseUnitStatusErrorCode] = mapped_column(nullable=False)
    """The :type:`error code <.types.BaseUnitStatusErrorCode>` of the BaseUnit status entry

    This can be one of "Ok", "Warning", or "Error".
    """

    error_message: Mapped[str] = mapped_column(nullable=True)
    """The error message of the BaseUnit status entry, if any"""

    first_used: Mapped[datetime.datetime] = mapped_column(nullable=False)
    """The timestamp of when the BaseUnit was first used"""

    in_use: Mapped[bool] = mapped_column(nullable=False)
    """Whether the BaseUnit is in use at the time of this status entry"""

    sharing: Mapped[bool] = mapped_column(nullable=False)
    """Whether the BaseUnit is sharing at the time of this status entry"""

    uploaded_to_influx: Mapped[bool] = mapped_column(nullable=False, default=False)
    """Whether this status entry has been uploaded to InfluxDB"""

    base_unit: Mapped[BaseUnit] = relationship(back_populates="statuses")
    """The :class:`BaseUnit` that this instance is associated with"""

    @property
    def natural_key(self) -> BaseUnitStatusNaturalKey:
        """Get the natural key for this instance
        """
        return (
            self.base_unit.natural_key,
            self.id,
        )

    def serialize(self) -> _BaseUnitStatusSerializeTD:
        """Serialize this instance to a dictionary for JSON serialization
        """
        return _BaseUnitStatusSerializeTD(
            natural_key=self.natural_key,
            base_unit=RelationshipNaturalKey(
                related_model_table="base_units",
                related_model_key=self.base_unit.natural_key,
            ),
            timestamp=DtIsoStr(self.timestamp.isoformat()),
            current_uptime=self.current_uptime,
            total_uptime=self.total_uptime,
            error_code=self.error_code,
            error_message=self.error_message,
            first_used=DtIsoStr(self.first_used.isoformat()),
            in_use=self.in_use,
            sharing=self.sharing,
            uploaded_to_influx=self.uploaded_to_influx,
        )

    @classmethod
    def deserialize(cls, data: _BaseUnitStatusSerializeTD, session: Session) -> Self|None:
        """Deserialize a dictionary into an instance of this model
        """
        assert isinstance(data["base_unit"], RelationshipNaturalKey), f"Expected 'base_unit' to be a RelationshipNaturalKey, got {data['base_unit']}"
        base_unit = BaseUnit.get_by_natural_key(session, data["base_unit"].related_model_key)
        if base_unit is None:
            return None
        return cls(
            base_unit_id=base_unit.id,
            timestamp=timezone.ensure_aware(datetime.datetime.fromisoformat(data["timestamp"])),
            current_uptime=data["current_uptime"],
            total_uptime=data["total_uptime"],
            error_code=data["error_code"],
            error_message=data["error_message"],
            first_used=timezone.ensure_aware(datetime.datetime.fromisoformat(data["first_used"])),
            in_use=data["in_use"],
            sharing=data["sharing"],
            uploaded_to_influx=data["uploaded_to_influx"],
        )

    @classmethod
    def select_by_natural_key(cls, key: BaseUnitStatusNaturalKey) -> SelectOf[Self]:
        """Get a select statement to retrieve a model instance by its natural key
        """
        base_unit_hostname, pk = key
        return select(cls).join(BaseUnit).filter(
            BaseUnit.hostname == base_unit_hostname,
            cls.id == pk,
        )

    @property
    def current_uptime_timedelta(self) -> datetime.timedelta:
        """Get the current uptime as a timedelta."""
        return datetime.timedelta(seconds=self.current_uptime)

    @classmethod
    def from_data(cls, base_unit: int|BaseUnit, data: BaseUnitStatusData, now: datetime.datetime|None = None) -> Self:
        """Create an instance of this model from a :class:`.types.BaseUnitStatus` instance
        """
        if isinstance(base_unit, BaseUnit):
            base_unit = base_unit.id
        if now is None:
            now = timezone.utcnow()
        else:
            timezone.ensure_aware(now)
        return cls(
            base_unit_id=base_unit,
            timestamp=now,
            current_uptime=int(data.current_uptime.total_seconds()),
            total_uptime=int(data.total_uptime.total_seconds()),
            error_code=data.error_code,
            error_message=data.error_message,
            first_used=timezone.ensure_aware(data.first_used),
            in_use=data.in_use,
            sharing=data.sharing,
        )

    def to_data(self) -> BaseUnitStatusData:
        """Convert this instance to a :class:`.types.BaseUnitStatus` instance
        """
        return BaseUnitStatusData(
            base_unit=self.base_unit.to_data(),
            current_uptime=self.current_uptime_timedelta,
            total_uptime=datetime.timedelta(seconds=self.total_uptime),
            error_code=self.error_code,
            error_message=self.error_message,
            first_used=self.first_used,
            in_use=self.in_use,
            sharing=self.sharing,
        )

    def __repr__(self) -> str:
        return f"<BaseUnitStatus(id={self.id}, base_unit={self.base_unit}, timestamp={self.timestamp})>"

    def __str__(self) -> str:
        return f"BaseUnitStatus for {self.base_unit} at {self.timestamp}"




class BaseUnitUsageStatus(Base[BaseUnitUsageStatusNaturalKey, _BaseUnitUsageStatusSerializeTD]):
    """ORM model for the usage status of a ClickShare BaseUnit at a given point in time
    """
    __tablename__ = "base_unit_usage_statuses"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime.datetime] = mapped_column(index=True, nullable=False)
    """Timestamp of the usage status entry"""

    base_unit_id: Mapped[int] = mapped_column(ForeignKey("base_units.id"), nullable=False)
    in_use: Mapped[bool] = mapped_column(nullable=False)
    """Whether the BaseUnit is in use at the time of this usage status entry"""

    sharing: Mapped[bool] = mapped_column(nullable=False)
    """Whether the BaseUnit is sharing at the time of this usage status entry"""

    uploaded_to_influx: Mapped[bool] = mapped_column(nullable=False, default=False)
    """Whether this usage status entry has been uploaded to InfluxDB"""

    base_unit: Mapped[BaseUnit] = relationship(back_populates="usage_statuses")
    """The :class:`BaseUnit` that this instance is associated with"""

    @property
    def natural_key(self) -> BaseUnitUsageStatusNaturalKey:
        """Get the natural key for this instance
        """
        return (
            self.base_unit.natural_key,
            self.id,
        )

    @classmethod
    def select_by_natural_key(cls, key: BaseUnitUsageStatusNaturalKey) -> SelectOf[Self]:
        """Get a select statement to retrieve a model instance by its natural key
        """
        base_unit_hostname, pk = key
        return select(cls).join(BaseUnit).filter(
            BaseUnit.hostname == base_unit_hostname,
            cls.id == pk,
        )

    def serialize(self) -> _BaseUnitUsageStatusSerializeTD:
        """Serialize this instance to a dictionary for JSON serialization
        """
        return _BaseUnitUsageStatusSerializeTD(
            natural_key=self.natural_key,
            base_unit=RelationshipNaturalKey(
                related_model_table="base_units",
                related_model_key=self.base_unit.natural_key,
            ),
            timestamp=DtIsoStr(self.timestamp.isoformat()),
            in_use=self.in_use,
            sharing=self.sharing,
            uploaded_to_influx=self.uploaded_to_influx,
        )

    @classmethod
    def deserialize(cls, data: _BaseUnitUsageStatusSerializeTD, session: Session) -> Self | None:
        """Deserialize a dictionary into an instance of this model

        If no instance can be created (e.g. due to missing related objects), ``None`` is returned.
        """
        assert isinstance(data["base_unit"], RelationshipNaturalKey), f"Expected 'base_unit' to be a RelationshipNaturalKey, got {data['base_unit']}"
        base_unit = BaseUnit.get_by_natural_key(session, data["base_unit"].related_model_key)
        if base_unit is None:
            return None
        return cls(
            base_unit_id=base_unit.id,
            timestamp=timezone.ensure_aware(datetime.datetime.fromisoformat(data["timestamp"])),
            in_use=data["in_use"],
            sharing=data["sharing"],
            uploaded_to_influx=data["uploaded_to_influx"],
        )

    @classmethod
    def from_data(cls, base_unit: int|BaseUnit, data: BaseUnitStatusData|BaseUnitUsageStatusData, now: datetime.datetime|None = None) -> Self:
        """Create an instance of this model from a :class:`.types.BaseUnitStatus` instance
        """
        if isinstance(base_unit, BaseUnit):
            base_unit = base_unit.id
        if now is None:
            now = timezone.utcnow()
        else:
            timezone.ensure_aware(now)
        return cls(
            base_unit_id=base_unit,
            timestamp=now,
            in_use=data.in_use,
            sharing=data.sharing,
        )

    def to_data(self) -> BaseUnitUsageStatusData:
        """Convert this instance to a :class:`.types.BaseUnitUsageStatus` instance
        """
        return BaseUnitUsageStatusData(
            base_unit=self.base_unit.to_data(),
            in_use=self.in_use,
            sharing=self.sharing,
        )

    @classmethod
    def _create_from_base_unit_status(cls, base_unit_status: BaseUnitStatus) -> Self:
        """Temporary method to create a BaseUnitUsageStatus from a BaseUnitStatus, for migration purposes."""
        return cls(
            base_unit_id=base_unit_status.base_unit_id,
            timestamp=base_unit_status.timestamp,
            in_use=base_unit_status.in_use,
            sharing=base_unit_status.sharing,
        )

    def __repr__(self) -> str:
        return f"<BaseUnitUsageStatus(id={self.id}, base_unit={self.base_unit}, timestamp={self.timestamp}, in_use={self.in_use}, sharing={self.sharing})>"

    def __str__(self) -> str:
        return f"BaseUnitUsageStatus for {self.base_unit} at {self.timestamp}"



class SensorReading(Base[SensorReadingNaturalKey, _SensorReadingSerializeTD]):
    """ORM model for a sensor reading."""
    __tablename__ = "sensor_readings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    base_unit_id: Mapped[int] = mapped_column(ForeignKey("base_units.id"), nullable=False)
    timestamp: Mapped[datetime.datetime] = mapped_column(index=True, nullable=False)
    """Timestamp of the sensor reading"""

    sensor_type: Mapped[SensorType] = mapped_column(index=True, nullable=False)
    """The :type:`sensor type <.types.SensorType>` of the sensor reading

    This can be one of "CPU", "WLAN0", "WLAN1", or "CPU_FAN".
    """
    value: Mapped[float] = mapped_column(nullable=False)
    """The value of the sensor reading"""

    uploaded_to_influx: Mapped[bool] = mapped_column(nullable=False, default=False)
    """Whether this sensor reading has been uploaded to InfluxDB"""

    base_unit: Mapped[BaseUnit] = relationship(back_populates="sensor_readings")
    """The :class:`BaseUnit` that this instance is associated with"""

    # Add a unique constraint to prevent duplicate readings for the same base unit, timestamp, and sensor type
    __table_args__ = (
        UniqueConstraint("base_unit_id", "timestamp", "sensor_type", name="uix_base_unit_timestamp_sensor"),
    )

    @property
    def natural_key(self) -> SensorReadingNaturalKey:
        """Get the natural key for this instance
        """
        return (
            self.base_unit.natural_key,
            self.id,
        )

    def serialize(self) -> _SensorReadingSerializeTD:
        """Serialize this instance to a dictionary for JSON serialization
        """
        return {
            "natural_key": self.natural_key,
            "base_unit": RelationshipNaturalKey(
                related_model_table="base_units",
                related_model_key=self.base_unit.natural_key,
            ),
            "timestamp": DtIsoStr(self.timestamp.isoformat()),
            "sensor_type": self.sensor_type,
            "value": self.value,
            "uploaded_to_influx": self.uploaded_to_influx,
        }

    @classmethod
    def deserialize(cls, data: _SensorReadingSerializeTD, session: Session) -> SensorReading|None:
        """Deserialize a dictionary into an instance of this model

        If no instance can be created (e.g. due to missing related objects), ``None`` is returned.
        """
        base_unit = BaseUnit.get_by_natural_key(session, data["base_unit"].related_model_key)
        if base_unit is None:
            return None
        return cls(
            base_unit_id=base_unit.id,
            timestamp=timezone.ensure_aware(datetime.datetime.fromisoformat(data["timestamp"])),
            sensor_type=data["sensor_type"],
            value=data["value"],
            uploaded_to_influx=data["uploaded_to_influx"],
        )

    @classmethod
    def select_by_natural_key(cls, key: SensorReadingNaturalKey) -> SelectOf[Self]:
        """Get a select statement to retrieve a model instance by its natural key
        """
        base_unit_hostname, pk = key
        return select(cls).join(BaseUnit).filter(
            BaseUnit.hostname == base_unit_hostname,
            cls.id == pk,
        )

    @classmethod
    def select_by_sensor_type(cls, sensor_type: SensorType) -> SelectOf[SensorReading]:
        """Get a select statement for SensorReadings of a specific sensor type
        """
        return select(SensorReading).where(SensorReading.sensor_type == sensor_type)

    @classmethod
    def from_data(
        cls,
        base_unit: BaseUnit|BaseUnitInfo|int,
        reading: SensorReadingData[SensorType],
        session: Session
    ) -> Self:
        """Create an instance of this model from a :class:`.types.SensorReading` instance
        """
        if isinstance(base_unit, BaseUnitInfo):
            base_unit, _ = BaseUnit.get_or_create(base_unit, session)
        elif isinstance(base_unit, BaseUnit):
            base_unit = base_unit.id
        return cls(
            base_unit_id=base_unit,
            timestamp=ensure_aware(reading.timestamp),
            sensor_type=reading.sensor,
            value=reading.value,
        )

    def to_data(self) -> SensorReadingData[SensorType]:
        """Convert this instance to a :class:`.types.SensorReading` instance
        """
        assert self.timestamp.tzinfo is not None, "SensorReading timestamp must be timezone-aware"
        return SensorReadingData(
            timestamp=self.timestamp,
            sensor=self.sensor_type,
            value=self.value,
        )

    def __repr__(self) -> str:
        return f"<SensorReading(id={self.id}, base_unit={self.base_unit}, timestamp={self.timestamp}, sensor_type={self.sensor_type}, value={self.value})>"

    def __str__(self) -> str:
        return f"SensorReading for {self.base_unit} at {self.timestamp}: {self.sensor_type}={self.value}"



type ModelInstance = (
    LocationType
    | Location
    | BaseUnit
    | BaseUnitOnlineStatus
    | BaseUnitStatus
    | BaseUnitUsageStatus
    | SensorReading
    | BaseUnitIdentity
    | PowerManagementSettings
    | PowerManagementStatus
)
type ModelClass = type[ModelInstance]
type ModelTableName = Literal[
    "location_types",
    "locations",
    "base_units",
    "base_unit_online_statuses",
    "base_unit_statuses",
    "base_unit_usage_statuses",
    "sensor_readings",
    "base_unit_identities",
    "power_management_settings",
    "power_management_status"
]
MODEL_CLASSES = (
    LocationType,
    Location,
    BaseUnit,
    BaseUnitOnlineStatus,
    BaseUnitIdentity,
    PowerManagementSettings,
    PowerManagementStatus,
    BaseUnitStatus,
    BaseUnitUsageStatus,
    SensorReading,
)
