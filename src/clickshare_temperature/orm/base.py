from __future__ import annotations

import datetime
import enum
from abc import abstractmethod
from collections.abc import Sequence
from typing import Any, ClassVar, Self

import sqlalchemy
from sqlalchemy import Float, String, inspect, select
from sqlalchemy.orm import (
    DeclarativeBase,
    Session,
)
from sqlalchemy_utc import UtcDateTime

from ..types import LogLevel, SensorType
from .types import (
    DeserializationError,
    FullySerializedModelTD,
    SelectOf,
    _BaseModelSerializeTD,
)


class Base[NaturalKeyType, SerializeType: (_BaseModelSerializeTD[Any])](DeclarativeBase):
    """Base class for SQLAlchemy ORM models."""
    type_annotation_map: ClassVar[dict[Any, Any]] = {
        # int: BIGINT,
        str: String(),
        float: Float,
        # datetime.datetime: TIMESTAMP(timezone=True),
        datetime.datetime: UtcDateTime(),
        SensorType: sqlalchemy.Enum(enum.Enum),
        LogLevel: sqlalchemy.Enum(enum.Enum),
    }
    # __tablename__: ClassVar[ModelTableName]

    @property
    @abstractmethod
    def natural_key(self) -> NaturalKeyType:
        """Return the natural key for this model instance"""
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def select_by_natural_key(cls, key: NaturalKeyType) -> SelectOf[Self]:
        """Get a select statement to retrieve a model instance by its natural key
        """
        raise NotImplementedError

    @classmethod
    def get_by_natural_key(cls, session: Session, key: NaturalKeyType) -> Self|None:
        """Get a model instance by its natural key"""
        stmt = cls.select_by_natural_key(key)
        return session.execute(stmt).scalar_one_or_none()

    @classmethod
    def get_scalars_all(cls, session: Session) -> Sequence[Self]:
        """Get a sequence of all instances of this model
        """
        return session.execute(select(cls)).scalars().all()

    @abstractmethod
    def serialize(self) -> SerializeType:
        """Serialize the model instance"""
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def deserialize(cls, data: SerializeType, session: Session) -> Self|None:
        """Deserialize the model from serialized data

        If the data references related models (e.g. foreign keys) and the related
        models do not exist in the database, ``None`` is returned.
        This allows for iterative deserialization of multiple models with interdependencies.
        """
        raise NotImplementedError

    def serialize_fully(self) -> FullySerializedModelTD[SerializeType]:
        """Serialize the model instance, including the model's table name and serialized data."""
        data = self.serialize()
        obj = FullySerializedModelTD(
            model=self.__tablename__,
            data=data,
        )
        return obj

    @classmethod
    def deserialize_fully(
        cls,
        data: FullySerializedModelTD[SerializeType],
        session: Session
    ) -> tuple[Self|None, bool]:
        """Deserialize the model from fully serialized data, which includes
        the model's table name and serialized data
        """
        if data["model"] != cls.__tablename__:
            raise DeserializationError(f"Cannot deserialize data for model {data['model']} with class {cls.__name__}")

        nk = data["data"]["natural_key"]
        obj = cls.get_by_natural_key(session, key=nk)
        if obj is not None:
            return obj, False
        return cls.deserialize(data["data"], session=session), True

    def _get_current_orm_session(self) -> Session:
        session = inspect(self).session
        if session is None:
            raise RuntimeError("Model instance is not attached to a session")
        assert isinstance(session, Session)
        return session
