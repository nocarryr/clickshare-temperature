from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal, NamedTuple, Self, TypedDict, TypeIs

if TYPE_CHECKING:
    from .models import ModelTableName


from sqlalchemy.sql.expression import CompoundSelect, Select

type SelectOf[T] = Select[T]
"""Type alias for a SQLAlchemy Select object"""

type CompoundSelectOf[T] = CompoundSelect[T]
"""Type alias for a SQLAlchemy CompoundSelect object"""


type Ordering = Literal["asc", "desc"]

type LocationSiblingType = Literal["first", "middle", "last", "only"]
"""A type representing the sibling status of a :class:`.Location` among its siblings
with the same parent location.

- "first": This Location is the first child among its siblings
  (i.e. it has the lowest position in the order of children under the same parent location).
- "middle": This Location is neither the first nor the last child among its siblings
  (i.e. it has at least one sibling before it and at least one sibling after it
  in the order of children under the same parent location).
- "last": This Location is the last child among its siblings
  (i.e. it has the highest position in the order of children under the same parent location).
- "only": This Location is the only child under its parent location (i.e. it has no siblings).
"""


class DeserializationError(Exception):
    """Custom exception for errors during deserialization of ORM models."""



class RelationshipNaturalKeyTD[K](TypedDict):
    """A TypedDict for a natural key for a relationship between two models."""
    related_model_table: ModelTableName
    related_model_key: K
    _is_relation_: Literal[True]

class RelationshipNaturalKey[K](NamedTuple):
    """A natural key for a relationship between two models."""
    related_model_table: ModelTableName
    related_model_key: K

    def serialize(self) -> RelationshipNaturalKeyTD[K]:
        """Serialize the relationship natural key to a dictionary for JSON serialization."""
        return RelationshipNaturalKeyTD(
            related_model_table=self.related_model_table,
            related_model_key=self.related_model_key,
            _is_relation_=True,
        )

    @classmethod
    def deserialize(cls, data: RelationshipNaturalKeyTD[K]) -> Self:
        """Deserialize a relationship natural key from a dictionary."""
        if not data.get("_is_relation_", False):
            raise DeserializationError("Data does not appear to be a serialized relationship natural key: " + str(data))
        return cls(
            related_model_table=data["related_model_table"],
            related_model_key=data["related_model_key"],
        )

    @classmethod
    def is_relationship_natural_key(cls, data: object) -> TypeIs[RelationshipNaturalKeyTD[Any]]:
        """Check if a dictionary appears to be a serialized relationship natural key."""
        if not isinstance(data, dict):
            return False
        return data.get("_is_relation_", False) and "related_model_table" in data and "related_model_key" in data


class _BaseModelSerializeTD[K](TypedDict):
    natural_key: K

class FullySerializedModelTD[DataT: (_BaseModelSerializeTD[Any])](TypedDict):
    """TypedDict for a fully serialized model, including the model's table name and serialized data."""
    model: ModelTableName
    data: DataT
