from __future__ import annotations

import asyncio
import datetime
import warnings
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import click
import click_extra

# from yarl import URL
from aiohttp import ClientError, ClientSession
from sqlalchemy import and_, create_mock_engine, or_, select
from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from sqlalchemy.engine.mock import MockConnection
    from sqlalchemy.sql.ddl import BaseDDLElement

from .. import timezone
from ..baseunit_api import (
    create_session as create_aiohttp_session,
)
from ..baseunit_api import (
    get_baseunit_identity,
    get_baseunit_info,
    get_baseunit_status,
    get_power_management_info,
)
from ..click_extra_params import CLIRootContext, get_extra_params
from ..temperature_history import TemperatureHistory
from ..types import (
    AioHttpRequestOptions,
    AuthInfo,
    BaseUnitInfo,
    PowerModeStatus,
)
from ..utils import click_secho, get_baseunit_from_filename, is_valid_ip_or_hostname
from .base import Base
from .engine import (
    create_engine_uri,
    init_db,
    set_engine_uri,
)
from .engine import (
    get_session as get_db_session,
)
from .location_table import (
    DEFAULT_LOCATION_TABLE_KEYS,
    LOCATION_TABLE_TITLES,
    LocationTableKey,
    show_locations_table,
)
from .models import (
    BaseUnit,
    BaseUnitIdentity,
    BaseUnitOnlineStatus,
    BaseUnitStatus,
    BaseUnitUsageStatus,
    Location,
    LocationType,
    PowerManagementSettings,
    PowerManagementStatus,
    SensorReading,
)
from .serialization import deserialize_database, serialize_database
from .types import SelectOf
from .utils import get_count_for_select


class CommunicationError(UserWarning):
    """Warning raised when there is a communication error with a BaseUnit
    """


COMMUNICATION_ERROR_EXIT_CODE: int = 2
"""Exit code to use when a :class:`CommunicationError` is raised and causes the program to exit"""


def catch_communication_errors[**P, ResultT](
    func: Callable[P, ResultT],
    *args: P.args,
    **kwargs: P.kwargs
) -> tuple[ResultT, bool]:
    """Helper function to catch :class:`CommunicationError`

    Arguments:
        func: The function to call
        *args: Positional arguments to pass to the function
        **kwargs: Keyword arguments to pass to the function

    Returns:
        A tuple of:

        - **result**: The result of the function call
        - **had_error**: A boolean indicating whether a CommunicationError was caught
    """
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always", CommunicationError)
        result = func(*args, **kwargs)
        had_error = False
        for warning in w:
            if issubclass(warning.category, CommunicationError):
                click_secho(str(warning.message), fg="red")
                had_error = True
        return result, had_error


def raise_communication_errors[**P, ResultT](
    func: Callable[P, ResultT],
    *args: P.args,
    **kwargs: P.kwargs
) -> ResultT:
    """Helper function to catch :class:`CommunicationError` and raise a SystemExit
    if any are found

    Arguments:
        func: The function to call
        *args: Positional arguments to pass to the function
        **kwargs: Keyword arguments to pass to the function

    Returns the result of the function call if no CommunicationErrors were caught

    Raises:
        SystemExit: If any CommunicationErrors were caught, with an exit code of
            :data:`COMMUNICATION_ERROR_EXIT_CODE`
    """
    result, had_error = catch_communication_errors(func, *args, **kwargs)
    if had_error:
        raise SystemExit(COMMUNICATION_ERROR_EXIT_CODE)
    return result


db_option_group = click_extra.option_group(
    "Database Options",
    click_extra.option(
        "-d", "--db-url",
        envvar="CLICKSHARE_DB_URL",
        type=str,
        help="Database URL for SQLAlchemy (e.g. 'sqlite:///clickshare_data.db').",
        show_envvar=True,
    ),
)


@dataclass
class CLIDbContext(CLIRootContext):
    """Context object for the ORM CLI

    This extends :class:`CLIRootContext`
    """
    db_url: str|None
    """Database URL for SQLAlchemy"""



@click_extra.group(name="orm", params=get_extra_params())
@db_option_group
@click_extra.pass_context
def cli(ctx: click.Context, db_url: str|None) -> None:
    """CLI for ClickShare ORM commands"""
    root_ctx: CLIRootContext = ctx.obj
    ctx.obj = CLIDbContext(
        auth_info=root_ctx.auth_info,
        aiohttp_request_options=root_ctx.aiohttp_request_options,
        aiohttp_session_options=root_ctx.aiohttp_session_options,
        db_url=db_url,
    )
    if db_url is not None:
        set_engine_uri(db_url)


@cli.group(name="baseunit")
@click_extra.pass_context
def baseunit_cli(ctx: click.Context) -> None:
    """CLI for managing BaseUnits in the database"""


@cli.group(name="manage")
@click_extra.pass_context
def manage_cli(ctx: click.Context) -> None:
    """CLI for managing the database (e.g. initializing, resetting, etc.)"""


@cli.group(name="update")
@click_extra.pass_context
def update_cli(ctx: click.Context) -> None:
    """CLI for updating information in the database by fetching data from the BaseUnits"""


@cli.group(name="location")
@click_extra.pass_context
def location_cli(ctx: click.Context) -> None:
    """CLI for managing Locations in the database"""



@update_cli.command(name="from-files")
@click_extra.argument(
    "directory",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
)
@click_extra.pass_obj
def backfill_from_files(ctx_obj: CLIDbContext, directory: Path) -> None:
    """Backfill sensor readings from all files in a directory to the database."""
    with get_db_session() as session:
        for filepath in directory.glob("*.txt"):
            click_secho(f"Processing file {filepath}...", fg="blue")
            base_unit_info = get_baseunit_from_filename(filepath)
            base_unit = BaseUnit.get_by_hostname(base_unit_info.hostname, session=session)
            if base_unit is None:
                base_unit = BaseUnit(
                    hostname=base_unit_info.hostname,
                    room_name=base_unit_info.room_name,
                    ip_address=base_unit_info.ip_address,
                )
                session.add(base_unit)

                click_secho(f"Created new BaseUnit '{base_unit.hostname}' in the database", fg="green")
        session.commit()

        for filepath in directory.glob("*.txt"):
            click_secho(f"Processing file {filepath}...", fg="blue")
            base_unit_info = get_baseunit_from_filename(filepath)
            base_unit = BaseUnit.get_by_hostname(base_unit_info.hostname, session=session, raise_if_absent=True)
            temperature_history = TemperatureHistory.deserialize_str(base_unit_info, filepath.read_text())
            num_added, num_skipped = base_unit.add_sensor_readings(temperature_history.readings, session)
            click_secho(
                f"Finished processing file {filepath}. Added {num_added} readings, skipped {num_skipped} readings.",
                fg="blue",
            )
        session.commit()




@baseunit_cli.command(name="add")
@click_extra.argument("base_unit_ips", nargs=-1)
@click_extra.pass_obj
def add_baseunit(ctx_obj: CLIDbContext, base_unit_ips: tuple[str, ...]) -> None:
    """Add a BaseUnit to the database without fetching sensor readings."""
    session_options = ctx_obj.aiohttp_session_options
    request_options = ctx_obj.aiohttp_request_options

    async def get_all_baseunit_infos() -> list[BaseUnitInfo]:
        infos: list[BaseUnitInfo] = []
        async with create_aiohttp_session(**session_options) as aiohttp_session:
            for base_unit_ip in base_unit_ips:
                try:
                    info = await get_baseunit_info(
                        base_unit_ip,
                        auth_info=ctx_obj.auth_info,
                        session=aiohttp_session,
                        **request_options,
                    )
                    infos.append(info)
                except (TimeoutError, ClientError) as e:
                    warnings.warn(
                        f"Connection to BaseUnit at IP '{base_unit_ip}' failed: {e}, skipping",
                        CommunicationError,
                    )
        return infos
    exit_code = 0
    base_unit_infos, had_error = catch_communication_errors(
        asyncio.run,
        get_all_baseunit_infos(),
    )
    if had_error:
        exit_code = COMMUNICATION_ERROR_EXIT_CODE

    with get_db_session() as session:
        for baseunit_info in base_unit_infos:
            base_unit = BaseUnit.get_by_hostname(baseunit_info.hostname, session=session)
            if base_unit is not None:
                if base_unit.room_name != baseunit_info.room_name or base_unit.ip_address != baseunit_info.ip_address:
                    confirm_msg = '\n'.join([
                        f"BaseUnit with hostname '{base_unit.hostname}' already exists but has different information:",
                        f"Existing room name: '{base_unit.room_name}', IP address: '{base_unit.ip_address}'",
                        f"New room name: '{baseunit_info.room_name}', IP address: '{baseunit_info.ip_address}'",
                        "Do you want to update the existing BaseUnit with the new information?",
                    ])
                    if click.confirm(confirm_msg, default=True):
                        base_unit.room_name = baseunit_info.room_name
                        base_unit.ip_address = baseunit_info.ip_address
                        session.commit()
                        click_secho(
                            f"Updated BaseUnit '{base_unit.hostname}' in the database",
                            fg="green",
                        )
                else:
                    click_secho(
                        f"BaseUnit '{base_unit.hostname}' already exists, skipping",
                        fg="yellow",
                    )
            else:
                base_unit = BaseUnit(
                    hostname=baseunit_info.hostname,
                    room_name=baseunit_info.room_name,
                    ip_address=baseunit_info.ip_address,
                )
                session.add(base_unit)
                session.flush()
                base_unit.set_online_status(True)
                session.commit()
                click_secho(
                    f"Created new BaseUnit '{base_unit.hostname}'",
                    fg="green",
                )
    if exit_code != 0:
        raise SystemExit(exit_code)



@baseunit_cli.command(name="list")
@click_extra.table_format_option
@click_extra.pass_obj
@click_extra.pass_context
def list_baseunits(ctx: click_extra.Context, ctx_obj: CLIDbContext) -> None:
    """List all BaseUnits in the database."""
    header = ("Room Name", "Hostname", "IP Address", "Location")
    data = []
    with get_db_session() as session:
        base_units = BaseUnit.get_scalars_all(session)
        if len(base_units) == 0:
            click_secho("No BaseUnits found.", fg="yellow")
            return
        click_secho(f"Found {len(base_units)} BaseUnits:", fg="green")
        for base_unit in base_units:
            data.append((
                base_unit.room_name,
                base_unit.hostname,
                base_unit.ip_address,
                base_unit.location.path if base_unit.location else "None",
            ))
    ctx.print_table(data, header)



def location_table_option_group(
    default_keys: Sequence[LocationTableKey] | None = None
) -> Callable[[Callable[..., None]], Callable[..., None]]:
    """Factory function to create a click option group decorator for location
    table options with a specified default for the header keys

    Arguments:
        default_keys: The default header keys to use for the location table options
            if not specified in the command line arguments.
            If None, no default will be set and the header keys will be required.

    """
    if default_keys is None:
        default_keys = DEFAULT_LOCATION_TABLE_KEYS

    def decorator(func: Callable[..., None]) -> Callable[..., None]:
        return click_extra.option_group(
            "Location Table Options",
            click_extra.table_format_option,
            click_extra.option(
                '-k', '--header-keys',
                multiple=True,
                type=click.Choice(LOCATION_TABLE_TITLES.keys()),
                default=default_keys,
                help="Keys to include in the table header and the order to display them." \
                f" Defaults to {default_keys} if not specified.",
            ),
        )(func)
    return decorator




@location_cli.command(name="list")
@location_table_option_group()
@click_extra.pass_obj
@click_extra.pass_context
def list_locations(
    ctx: click.Context,
    ctx_obj: CLIDbContext,
    header_keys: list[LocationTableKey] | None,
) -> None:
    """List all Locations in the database."""
    with get_db_session() as session:
        show_locations_table(ctx, session, header_keys=header_keys)


@location_cli.command(name="add")
@click_extra.argument("name")
@click_extra.option("--parent-id", help="ID of the parent location (optional)")
@click_extra.option(
    "--type",
    "location_type_name",
    help="Name of the LocationType for this Location (optional)",
)
@click_extra.pass_obj
def add_location(
    ctx_obj: CLIDbContext,
    name: str,
    parent_id: int|None,
    location_type_name: str|None
) -> None:
    """Add a Location to the database, optionally as a child of an existing Location."""
    with get_db_session() as session:
        parent_location = None
        if parent_id is not None:
            parent_location = Location.get_by_id(parent_id, session=session)
            if parent_location is None:
                click_secho(f"Parent location with ID {parent_id} not found, aborting", fg="red")
                raise click.Abort()
        if location_type_name is not None:
            location_type = LocationType.get_by_name(location_type_name, session=session)
            if location_type is None:
                location_type = LocationType(name=location_type_name)
                session.add(location_type)
                session.flush()
        else:
            location_type = None
        new_location = Location(
            name=name,
            parent_location=parent_location,
            location_type=location_type,
        )
        session.add(new_location)
        session.commit()
        click_secho(f"Added {new_location} with ID {new_location.id}", fg="green")


@location_cli.command(name="set-type")
@click_extra.argument("name", help="The name of the LocationType to set for the Location")
@click_extra.argument("location_id", type=int, required=False, default=None)
@location_table_option_group(default_keys=("index_", "name", "type"))
@click_extra.pass_obj
@click_extra.pass_context
def set_location_type(
    ctx: click.Context,
    ctx_obj: CLIDbContext,
    name: str,
    location_id: int|None,
    header_keys: Sequence[LocationTableKey] | None,
) -> None:
    """Set the LocationType for a Location in the database."""
    with get_db_session() as session:
        if location_id is None:
            click_secho(
                "No location ID provided. "\
                "Please choose a location to set the LocationType for from the table below:",
                fg="yellow",
            )
            location_data = show_locations_table(ctx, session, header_keys=header_keys)
            location_data_by_index = {row.index_: row for row in location_data}
            location_index = click.prompt(
                "Enter the index of the location to set the LocationType for",
                type=int,
            )
            location_row = location_data_by_index.get(location_index)
            if location_row is None:
                click_secho(f"Invalid location index {location_index}, aborting", fg="red")
                raise click.Abort()
            location_id = location_row.id

        location = Location.get_by_id(location_id, session=session)
        if location is None:
            click_secho(f"Location with ID {location_id} not found, aborting", fg="red")
            raise click.Abort()
        location_type = LocationType.get_by_name(name, session=session)
        if location_type is None:
            location_type = LocationType(name=name)
            session.add(location_type)
            session.flush()
            click_secho(f"Created new LocationType '{name}' with ID {location_type.id}", fg="green")
        location.location_type = location_type
        session.commit()
        click_secho(f"Set LocationType of {location} to '{name}'", fg="green")


@location_cli.command(name="delete")
@click_extra.argument("location_id", type=int)
@click_extra.pass_obj
def delete_location(ctx_obj: CLIDbContext, location_id: int) -> None:
    """Delete a Location from the database. Child locations will also be deleted."""
    with get_db_session() as session:
        location = Location.get_by_id(location_id, session=session)
        if location is None:
            click_secho(f"Location with ID {location_id} not found, aborting", fg="red")
            raise click.Abort()

        if len(location.child_locations) > 0:
            descendant_select = location.select_descendants()
            descendant_ids_and_paths = {
                (loc.id, loc.path)
                for loc in session.execute(descendant_select).scalars().all()
            }
            descendant_count = len(descendant_ids_and_paths)
            msg = [
                f"{location} has {descendant_count} descendant location(s) that will also be deleted:",
            ]
            for i, (desc_id, desc_path) in enumerate(descendant_ids_and_paths):
                if i >= 10:
                    msg.append(f"... and {descendant_count - i} more")
                    break
                msg.append(f"- ID {desc_id}, path: {desc_path}")
            click_secho("\n".join(msg), fg="yellow")
            if not click.confirm(
                "Are you sure you want to delete this location and all its descendants?",
                default=False
            ):
                raise click.Abort()

        location_str = str(location)
        session.delete(location)
        session.commit()
        click_secho(f"Deleted {location_str} and all its child locations", fg="green")


@location_cli.command(name="assign")
@click_extra.argument("baseunit_hostname")
@click_extra.argument("location_id", type=int, default=None, required=False)
@location_table_option_group(default_keys=("index_", "name", "baseunit_count"))
@click_extra.pass_obj
@click_extra.pass_context
def assign_baseunit_location(
    ctx: click.Context,
    ctx_obj: CLIDbContext,
    baseunit_hostname: str,
    location_id: int|None,
    header_keys: Sequence[LocationTableKey] | None,
) -> None:
    """Assign a Location to a BaseUnit."""
    required_keys: tuple[LocationTableKey, ...] = ("index_",)
    if header_keys is None:
        header_keys = ("index_", "name", "baseunit_count")
    elif not all(key in header_keys for key in required_keys):
        click_secho(
            f"Warning: header keys {header_keys} do not include all required keys {required_keys}. " \
            "Adding missing required keys to header keys for location selection.",
            fg="yellow",
        )
        header_keys = list(header_keys) + [key for key in required_keys if key not in header_keys]

    with get_db_session() as session:
        base_unit = BaseUnit.get_by_hostname(baseunit_hostname, session=session)
        if base_unit is None:
            click_secho(f"BaseUnit with hostname '{baseunit_hostname}' not found, aborting", fg="red")
            raise click.Abort()

        if location_id is None:
            # Show the location table to allow the user to choose a location to assign to the BaseUnit
            click_secho(
                "No location ID provided. " \
                "Please choose a location to assign to the BaseUnit from the table below:",
            )
            highlight_location_id = base_unit.location.id if base_unit.location is not None else None
            location_data = show_locations_table(
                ctx=ctx,
                session=session,
                header_keys=header_keys,
                highlight_location_id=highlight_location_id,
            )
            location_data_by_index = {row.index_: row for row in location_data}
            location_index = click.prompt(
                "Enter the index of the location to assign to the BaseUnit",
                type=int,
            )
            location_row = location_data_by_index.get(location_index)
            if location_row is None:
                click_secho(f"Invalid location index {location_index}, aborting", fg="red")
                raise click.Abort()
            location_id = location_row.id

        location = Location.get_by_id(location_id, session=session)
        if location is None:
            click_secho(f"Location with ID {location_id} not found, aborting", fg="red")
            raise click.Abort()
        if base_unit.location is not None and base_unit.location.id == location_id:
            click_secho(
                f"BaseUnit '{base_unit.hostname}' is already assigned to {location}, skipping",
                fg="yellow",
            )
            return
        if base_unit.location is not None and base_unit.location.id != location_id:
            click_secho(
                f"BaseUnit '{base_unit.hostname}' is already assigned to location "
                f"{base_unit.location} (ID {base_unit.location.id}). ",
                fg="yellow",
            )
            if not click.confirm(
                f"Do you want to reassign it to {location}?",
                default=False,
            ):
                raise click.Abort()
        base_unit.location = location
        session.commit()
        click_secho(f"Assigned location {location} to BaseUnit '{base_unit.hostname}'", fg="green")


@location_cli.command(name="unassign")
@click_extra.argument("baseunit_hostname")
@click_extra.pass_obj
def unassign_baseunit_location(ctx_obj: CLIDbContext, baseunit_hostname: str) -> None:
    """Unassign the Location from a BaseUnit."""
    with get_db_session() as session:
        base_unit = BaseUnit.get_by_hostname(baseunit_hostname, session=session)
        if base_unit is None:
            click_secho(f"BaseUnit with hostname '{baseunit_hostname}' not found, aborting", fg="red")
            raise click.Abort()
        base_unit.location = None
        session.commit()
        click_secho(f"Unassigned location from BaseUnit '{base_unit.hostname}'", fg="green")



@update_cli.command(name="baseunit-info")
@click_extra.pass_obj
def update_baseunit_info(ctx_obj: CLIDbContext) -> None:
    session_options = ctx_obj.aiohttp_session_options
    request_options = ctx_obj.aiohttp_request_options

    async def update_baseunit_info(base_unit: BaseUnit, session: Session, aiohttp_session: ClientSession) -> bool:
        if not is_valid_ip_or_hostname(base_unit.ip_address):
            click_secho(
                f"BaseUnit '{base_unit.hostname}' has invalid IP address '{base_unit.ip_address}', skipping",
                fg="red",
            )
            return False
        changed = False
        try:
            info = await get_baseunit_info(
                base_unit.ip_address,
                auth_info=ctx_obj.auth_info,
                session=aiohttp_session,
                **request_options,
            )
            base_unit.set_online_status(True)
            if base_unit.room_name != info.room_name:
                base_unit.room_name = info.room_name
                changed = True
            if base_unit.ip_address != info.ip_address:
                base_unit.ip_address = info.ip_address
                changed = True
            identity_info = await get_baseunit_identity(
                base_unit.ip_address,
                auth_info=ctx_obj.auth_info,
                session=aiohttp_session,
                **request_options,
            )
            identity_model = base_unit.identity
            if identity_model is None:
                identity_model = BaseUnitIdentity.from_data(base_unit, identity_info, session)
                session.add(identity_model)
                changed = True
            else:
                if identity_model.to_data() != identity_info:
                    raise ValueError(f"Identity mismatch for BaseUnit '{base_unit.hostname}'")
            click_secho(
                f"Updated information for BaseUnit '{base_unit.hostname}'",
                fg="green",
            )
        except (TimeoutError, ClientError) as e:
            warnings.warn(
                f"Connection to BaseUnit at IP '{base_unit.ip_address}' failed: {e}, skipping",
                CommunicationError,
            )
            base_unit.set_online_status(False)
        return changed

    async def update_all_baseunit_infos() -> None:
        async with create_aiohttp_session(**session_options) as aiohttp_session:
            with get_db_session() as session:
                base_units = BaseUnit.get_scalars_all(session)
                if len(base_units) == 0:
                    click_secho("No BaseUnits found.", fg="yellow")
                    return
                click_secho(
                    f"Updating information for {len(base_units)} BaseUnits...",
                    fg="green",
                )
                update_coros = [
                    update_baseunit_info(base_unit, session, aiohttp_session)
                    for base_unit in base_units
                ]
                results = await asyncio.gather(*update_coros)
                num_updated = sum(1 for r in results if r)
                click_secho(
                    f"Updated information for {num_updated} BaseUnits.",
                    fg="green",
                )
                session.commit()

    raise_communication_errors(asyncio.run, update_all_baseunit_infos())


@update_cli.command(name="power-management")
@click_extra.pass_obj
def update_power_management_info(ctx_obj: CLIDbContext) -> None:
    """Fetch the power management settings and statuses for all BaseUnits in the database and update the database."""
    session_options = ctx_obj.aiohttp_session_options
    request_options = ctx_obj.aiohttp_request_options
    now = timezone.utcnow()


    async def update_power_management_info(base_unit: BaseUnit, session: Session, aiohttp_session: ClientSession) -> bool:
        if not is_valid_ip_or_hostname(base_unit.ip_address):
            click_secho(
                f"BaseUnit '{base_unit.hostname}' has invalid IP address '{base_unit.ip_address}', skipping",
                fg="red",
            )
            return False
        try:
            power_info = await get_power_management_info(
                base_unit.ip_address,
                auth_info=ctx_obj.auth_info,
                session=aiohttp_session,
                **request_options,
            )
            base_unit.set_online_status(True)
            settings_model = base_unit.power_management_settings
            if settings_model is None:
                settings_model = PowerManagementSettings.from_data(base_unit, power_info, session)
                session.add(settings_model)
            else:
                settings_model.update_from_data(power_info)
            status_model = PowerManagementStatus.from_data(base_unit, power_info, now)
            session.add(status_model)
            click_secho(
                f"Updated power management information for BaseUnit '{base_unit.hostname}'",
                fg="green",
            )
            return True
        except (TimeoutError, ClientError) as e:
            warnings.warn(
                f"Connection to BaseUnit at IP '{base_unit.ip_address}' failed: {e}, skipping",
                CommunicationError,
            )
            base_unit.set_online_status(False)
            return False

    async def update_all_power_management_infos() -> None:
        async with create_aiohttp_session(**session_options) as aiohttp_session:
            with get_db_session() as session:
                base_units = BaseUnit.get_scalars_all(session)
                if len(base_units) == 0:
                    click_secho("No BaseUnits found.", fg="yellow")
                    return
                click_secho(
                    f"Updating power management information for {len(base_units)} BaseUnits...",
                    fg="green",
                )
                update_coros = [
                    update_power_management_info(base_unit, session, aiohttp_session)
                    for base_unit in base_units
                ]
                results = await asyncio.gather(*update_coros)
                num_updated = sum(1 for r in results if r)
                click_secho(
                    f"Updated power management information for {num_updated} BaseUnits.",
                    fg="green",
                )
                session.commit()

    raise_communication_errors(asyncio.run, update_all_power_management_infos())




@update_cli.command(name="statuses")
# @click.option(
#     "--upload-influx",
#     is_flag=True,
#     help="Whether to upload statuses to InfluxDB after fetching them from the BaseUnits.",
# )
@click_extra.option(
    "--usage-only",
    is_flag=True,
    help="Whether to fetch only usage statuses instead of full statuses.",
)
# @click.option(
#     "--backfill-readings",
#     is_flag=True,
# )
@click_extra.pass_obj
def update_statuses(ctx_obj: CLIDbContext, usage_only: bool) -> None:
    """Fetch the status for all BaseUnits in the database and print it to the console."""
    # if upload_influx:
    #     from ..influxdb import upload_baseunit_status
    session_options = ctx_obj.aiohttp_session_options
    request_options = ctx_obj.aiohttp_request_options

    model_cls = BaseUnitUsageStatus if usage_only else BaseUnitStatus

    async def update_all_statuses() -> None:
        async with create_aiohttp_session(**session_options) as aiohttp_session:
            with get_db_session() as session:
                base_units = BaseUnit.get_scalars_all(session)
                if len(base_units) == 0:
                    click_secho("No BaseUnits found.", fg="yellow")
                    return
                click_secho(f"Updating statuses for {len(base_units)} BaseUnits...", fg="green")
                # update_coros = [
                #     update_basunit_status(base_unit, auth_info, usage_only, session, aiohttp_session, request_options)
                #     for base_unit in base_units
                # ]
                update_coros = [
                    update_baseunit_status(
                        base_unit, ctx_obj.auth_info, model_cls, session,
                        aiohttp_session, request_options
                    )
                    for base_unit in base_units
                ]
                statuses = await asyncio.gather(*update_coros)
                num_updated = sum(1 for s in statuses if s is not None)
                click_secho(f"Updated statuses for {num_updated} BaseUnits.", fg="green")
                session.commit()

    raise_communication_errors(asyncio.run, update_all_statuses())



async def update_baseunit_status[T: BaseUnitStatus|BaseUnitUsageStatus](
    base_unit: BaseUnit,
    auth_info: AuthInfo,
    model_cls: type[T],
    session: Session,
    aiohttp_session: ClientSession,
    request_options: AioHttpRequestOptions
) -> BaseUnitStatus|BaseUnitUsageStatus|None:
    if not is_valid_ip_or_hostname(base_unit.ip_address):
        click_secho(
            f"BaseUnit '{base_unit.hostname}' has invalid IP address '{base_unit.ip_address}', skipping",
            fg="red",
        )
        return None
    try:
        status_data = await get_baseunit_status(
            base_unit.ip_address,
            auth_info=auth_info,
            session=aiohttp_session,
            **request_options
        )
        base_unit.set_online_status(True)
        status = model_cls.from_data(base_unit, status_data)
        session.add(status)
        return status
    except (TimeoutError, ClientError) as e:
        warnings.warn(
            f"Connection to BaseUnit at IP '{base_unit.ip_address}' failed: {e}, skipping",
            CommunicationError,
        )
        base_unit.set_online_status(False)
        return None


def get_online_statuses_for_influx_backfill(
    session: Session,
    time_series_window: datetime.timedelta = datetime.timedelta(hours=1),
    now: datetime.datetime|None = None,
) -> SelectOf[BaseUnitOnlineStatus]:
    """Build a select statement containing BaseUnitOnlineStatus rows requiring Influx backfill

    Selection includes either:

    1. Any status that has not been uploaded yet.
    2. The latest status per BaseUnit when its last upload is missing or stale.

    Arguments:
        session: The database session to use for querying.
        time_series_window: A :class:`datetime.timedelta` representing the maximum
            allowed age of the last upload for a status to be considered "fresh".
        now: The current time to use when determining if the last upload is stale.
            If None, the current UTC time will be used.

    Returns:
        A SQLAlchemy Select object selecting the BaseUnitOnlineStatus rows that
        require Influx backfill

    """
    if now is None:
        now = timezone.utcnow()

    last_online_status_ids: set[int] = set()
    for base_unit in BaseUnit.get_scalars_all(session):
        last_status = base_unit.last_online_status_instance()
        if last_status is not None and last_status.id is not None:
            last_online_status_ids.add(last_status.id)

    latest_stale_or_missing = and_(
        BaseUnitOnlineStatus.id.in_(last_online_status_ids),
        or_(
            BaseUnitOnlineStatus.last_upload_to_influx.is_(None),
            BaseUnitOnlineStatus.last_upload_to_influx < now - time_series_window,
        ),
    )

    return select(BaseUnitOnlineStatus).filter(
        or_(
            BaseUnitOnlineStatus.uploaded_to_influx.is_(False),
            latest_stale_or_missing,
        )
    )


@update_cli.command(name="fetch-readings-bulk")
@click_extra.option(
    "--baseunit-ip-file",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=False,
    help="Path to a text file containing a list of BaseUnit IP addresses, one per line.",
)
@click_extra.option(
    "--usage-only",
    is_flag=True,
    help="Whether to fetch only usage statuses instead of full statuses.",
)
@click_extra.pass_obj
def fetch_readings_bulk(
    ctx_obj: CLIDbContext,
    baseunit_ip_file: Path|None,
    usage_only: bool,
) -> None:
    """Fetch sensor readings for multiple BaseUnits and add them to the database."""
    session_options = ctx_obj.aiohttp_session_options
    request_options = ctx_obj.aiohttp_request_options
    baseunit_ips: list[str]|None = None
    if baseunit_ip_file is not None:
        baseunit_ips = []
        with baseunit_ip_file.open() as f:
            for line in f:
                if line.startswith(("#", "//")):
                    continue
                base_unit_ip = line.strip()
                if base_unit_ip:
                    baseunit_ips.append(base_unit_ip)


    model_cls = BaseUnitUsageStatus if usage_only else BaseUnitStatus

    async def fetch_all() -> None:
        async with create_aiohttp_session(**session_options) as aiohttp_session:
            with get_db_session() as orm_session:
                base_unit_select = select(BaseUnit)
                if baseunit_ips is not None:
                    base_unit_select = base_unit_select.filter(BaseUnit.ip_address.in_(baseunit_ips))
                status_coros = [
                    update_baseunit_status(
                        base_unit, ctx_obj.auth_info, model_cls, orm_session,
                        aiohttp_session, request_options,
                    )
                    for base_unit in orm_session.execute(base_unit_select).scalars()
                ]
                await asyncio.gather(*status_coros)
                orm_session.commit()  # Commit status updates before fetching sensor readings

                async def _do_fetch(base_unit: BaseUnit) -> None:
                    click_secho(f"Processing BaseUnit '{base_unit.hostname}' (ID: {base_unit.id})", fg="blue")
                    if not is_valid_ip_or_hostname(base_unit.ip_address):
                        click_secho(
                            f"BaseUnit '{base_unit.hostname}' has invalid IP address '{base_unit.ip_address}', skipping",
                            fg="red",
                        )
                        return
                    try:
                        await base_unit.add_sensor_readings_from_api(
                            auth_info=ctx_obj.auth_info,
                            session=orm_session,
                            aiohttp_session=aiohttp_session,
                            request_options=request_options,
                        )
                        base_unit.set_online_status(True)
                        click_secho(
                            f"Finished processing BaseUnit '{base_unit.hostname}' (ID: {base_unit.id})",
                            fg="blue",
                        )
                    except (TimeoutError, ClientError) as e:
                        warnings.warn(
                            f"Connection to BaseUnit '{base_unit.hostname}' failed: {e}, skipping",
                            CommunicationError,
                        )
                        base_unit.set_online_status(False)

                fetch_coros = set()
                for base_unit in orm_session.execute(base_unit_select).scalars():
                    if base_unit is None:
                        continue
                    assert base_unit.id is not None, "BaseUnit ID should not be None after commit"
                    fetch_coros.add(_do_fetch(base_unit))
                await asyncio.gather(*fetch_coros)

                orm_session.commit()

    raise_communication_errors(asyncio.run, fetch_all())



@update_cli.command(name="backfill-influx")
@click_extra.option(
    "--max-days",
    type=click.IntRange(min=0),
    default=None,
    required=False,
    help="The maximum age of statuses to backfill, in days. If not specified, all statuses will be backfilled",
)
@click_extra.option(
    "--max-points-per-batch",
    type=click.IntRange(min=1),
    default=5000,
    required=False,
    help="The maximum number of points to write to InfluxDB in a single batch",
    show_default=True,
)
@click_extra.pass_obj
def backfill_influx(
    ctx_obj: CLIDbContext,
    max_days: int | None = None,
    max_points_per_batch: int = 5000
) -> None:
    """Backfill all existing statuses in the database to InfluxDB."""
    from ..influxdb import (
        backfill_readings,
        upload_baseunit_online_statuses,
        upload_baseunit_status,
        upload_power_management_statuses,
    )

    def iter_select_chunks[T](select: SelectOf[T], chunk_size: int) -> Iterator[SelectOf[T]]:
        """Generic iterator to yield chunks of a SQLAlchemy select statement

        Assumes each yielded chunk is excluded from ``select`` (e.g. via an
        updated status column that is committed) before the next chunk is
        requested; otherwise this will loop forever.
        """
        while True:
            chunk = select.limit(chunk_size)
            if get_count_for_select(chunk, session=session) == 0:
                break
            yield chunk

    def get_earliest_backfill_time() -> datetime.datetime:
        now = timezone.utcnow()
        if max_days is not None:
            max_backfill_window = datetime.timedelta(days=max_days)
            return now - max_backfill_window
        return datetime.datetime.min.replace(tzinfo=datetime.UTC)


    def get_extra_tags_for_baseunit(base_unit: BaseUnit, session: Session) -> dict[str, str]:
        tags: dict[str, str] = {}
        if base_unit.location is None:
            return tags
        if base_unit.location_type_name is not None:
            tags[base_unit.location_type_name] = base_unit.location.name
        ancestor_locations_q = base_unit.location.select_ancestors()
        for ancestor in session.execute(ancestor_locations_q).scalars().all():
            if ancestor.location_type_name is not None:
                tags[ancestor.location_type_name] = ancestor.name
        return tags

    def backfill_base_unit(session: Session, base_unit: BaseUnit) -> None:
        earliest_backfill_time = get_earliest_backfill_time()
        sensor_select = select(SensorReading).where(
            SensorReading.base_unit_id == base_unit.id,
            SensorReading.uploaded_to_influx.is_(False),
        ).where(SensorReading.timestamp >= earliest_backfill_time)
        sensor_count = get_count_for_select(sensor_select, session=session)
        if sensor_count == 0:
            return
        click_secho(
            f"Backfilling {sensor_count} sensor readings for BaseUnit '{base_unit.hostname}'...",
            fg="blue",
        )

        def inner_backfill(sensor_select: SelectOf[SensorReading]) -> int:
            """Inner function to backfill a chunk of sensor readings"""
            temperature_history = base_unit.to_temperature_history_data(
                session,
                sensor_select=sensor_select,
            )
            num_backfilled = backfill_readings(
                temperature_history.base_unit,
                temperature_history,
                ignore_last_readings_info=True,
                tags_callback=lambda base_unit_info, reading: {
                    **get_extra_tags_for_baseunit(base_unit, session=session)
                },
            )
            for reading in session.execute(sensor_select).scalars().all():
                reading.uploaded_to_influx = True
            session.commit()
            return num_backfilled

        num_backfilled = 0
        for sensor_select_chunk in iter_select_chunks(sensor_select, max_points_per_batch):
            click_secho(
                f"  Backfilling next batch of up to {max_points_per_batch} readings for BaseUnit '{base_unit.hostname}'...",
                fg="blue",
            )
            num_backfilled += inner_backfill(sensor_select_chunk)
        click_secho(
            f"Backfill complete for BaseUnit '{base_unit.hostname}'. Backfilled {num_backfilled} readings.",
            fg="green",
        )

    def backfill_online_statuses(session: Session) -> None:
        now = timezone.utcnow()
        time_series_window = datetime.timedelta(hours=1)
        online_status_select = get_online_statuses_for_influx_backfill(
            session,
            time_series_window=time_series_window,
            now=now,
        )
        online_status_count = get_count_for_select(online_status_select, session=session)
        if online_status_count == 0:
            return
        click_secho(
            f"Backfilling {online_status_count} BaseUnitOnlineStatus entries...",
            fg="blue",
        )
        status_args: list[tuple[BaseUnitInfo, bool, datetime.datetime]] = []
        for online_status in session.execute(online_status_select).scalars().all():
            base_unit_info = online_status.base_unit.to_data()
            # If this is a "re-upload" of a stale last status, use the current
            # time as the uploaded timestamp.
            # Otherwise, use the original timestamp of the status to preserve the
            # historical online/offline changes as accurately as possible.
            if online_status.uploaded_to_influx and (
                online_status.last_upload_to_influx is None or
                online_status.last_upload_to_influx < now - time_series_window
            ):
                upload_timestamp = now
            else:
                upload_timestamp = online_status.timestamp
            status_args.append((base_unit_info, online_status.online, upload_timestamp))
        upload_baseunit_online_statuses(
            status_args,
            tags_callback=lambda base_unit_info: get_extra_tags_for_baseunit(
                BaseUnit.get_by_hostname(
                    base_unit_info.hostname, session=session, raise_if_absent=True,
                ),
                session=session,
            ),
        )
        for online_status in session.execute(online_status_select).scalars().all():
            online_status.uploaded_to_influx = True
            online_status.last_upload_to_influx = now
        session.commit()
        click_secho(
            "Backfill complete for BaseUnitOnlineStatus",
            fg="green",
        )

    def backfill_statuses[T: BaseUnitStatus | BaseUnitUsageStatus](session: Session, model_cls: type[T]) -> None:
        earliest_backfill_time = get_earliest_backfill_time()
        statuses_select = select(model_cls).where(
            model_cls.uploaded_to_influx.is_(False)
        ).where(model_cls.timestamp >= earliest_backfill_time)
        statuses_select = statuses_select.order_by(model_cls.timestamp.asc())
        statuses_count = get_count_for_select(statuses_select, session=session)
        if statuses_count == 0:
            return
        click_secho(
            f"Backfilling and uploading {statuses_count} {model_cls.__name__} entries...",
            fg="blue",
        )
        def backfill_inner(status_select: SelectOf[T]) -> None:
            """Inner function to backfill a chunk of statuses"""
            statuses = session.execute(status_select).scalars().all()
            upload_baseunit_status(
                [(s.to_data(), s.timestamp) for s in statuses],
                tags_callback=lambda status_data: get_extra_tags_for_baseunit(
                    BaseUnit.get_by_hostname(
                        status_data.base_unit.hostname, session=session, raise_if_absent=True,
                    ),
                    session=session,
                ),
            )
            for status in statuses:
                status.uploaded_to_influx = True
            session.commit()

        for status_chunk in iter_select_chunks(statuses_select, max_points_per_batch):
            click_secho(
                f"  Backfilling next batch of up to {max_points_per_batch} {model_cls.__name__} entries...",
                fg="blue",
            )
            backfill_inner(status_chunk)

        click_secho(
            f"Backfill complete for {model_cls.__name__}",
            fg="green",
        )

    def backfill_power_statuses(session: Session) -> None:
        earliest_backfill_time = get_earliest_backfill_time()
        power_status_select = select(PowerManagementStatus).where(
            PowerManagementStatus.uploaded_to_influx.is_(False)
        ).where(PowerManagementStatus.timestamp >= earliest_backfill_time)
        power_status_select = power_status_select.order_by(PowerManagementStatus.timestamp.asc())
        power_status_count = get_count_for_select(power_status_select, session=session)
        if power_status_count == 0:
            return
        click_secho(
            f"Backfilling and uploading {power_status_count} PowerManagementStatus entries...",
            fg="blue",
        )

        def backfill_inner(power_status_select: SelectOf[PowerManagementStatus]) -> None:
            """Inner function to backfill a chunk of PowerManagementStatus entries"""
            power_statuses = session.execute(power_status_select).scalars().all()
            if len(power_statuses) == 0:
                return
            power_status_args: list[tuple[BaseUnitInfo, PowerModeStatus, datetime.datetime]] = [
                (s.base_unit.to_data(), s.power_mode_status, s.timestamp)
                for s in power_statuses
            ]
            upload_power_management_statuses(
                power_status_args,
                tags_callback=lambda base_unit_info: get_extra_tags_for_baseunit(
                    BaseUnit.get_by_hostname(
                        base_unit_info.hostname, session=session, raise_if_absent=True,
                    ),
                    session=session,
                ),
            )
            for power_status in power_statuses:
                power_status.uploaded_to_influx = True
            session.commit()

        for power_status_chunk in iter_select_chunks(power_status_select, max_points_per_batch):
            click_secho(
                f"  Backfilling next batch of up to {max_points_per_batch} PowerManagementStatus entries...",
                fg="blue",
            )
            backfill_inner(power_status_chunk)

        click_secho(
            "Backfill complete for PowerManagementStatus",
            fg="green",
        )

    with get_db_session() as session:
        for base_unit in session.execute(select(BaseUnit)).scalars().all():
            backfill_base_unit(session, base_unit)

        backfill_online_statuses(session)
        backfill_statuses(session, BaseUnitUsageStatus)
        backfill_statuses(session, BaseUnitStatus)
        backfill_power_statuses(session)




@manage_cli.command(name="show-schema")
@click_extra.option(
    "--dialect",
    type=click.Choice(["sqlite", "postgresql", "mysql"], case_sensitive=False),
    default="sqlite",
)
def show_db_schema(dialect: str) -> None:
    """Print the SQL CREATE TABLE statements for all tables in the database schema.
    """
    mock_engine: MockConnection|None = None

    def executor(sql: BaseDDLElement, *multiparams: object, **params: object) -> None:
        assert mock_engine is not None
        click.echo(sql.compile(dialect=mock_engine.dialect))

    # This will print the CREATE TABLE statements for all tables in the schema
    # using a mocked engine.
    uri = create_engine_uri(scheme=dialect, path="")
    mock_engine = create_mock_engine(uri, executor)
    Base.metadata.create_all(mock_engine)


@manage_cli.command(name="init-db")
@click_extra.pass_obj
def init_database(ctx_obj: CLIDbContext) -> None:
    """Initialize the database by creating all tables."""
    init_db()


@manage_cli.command(name="dump-db")
@click_extra.argument(
    'output_file',
    type=click.Path(dir_okay=False, path_type=Path),
)
@click_extra.option(
    "--pretty",
    is_flag=True,
    help="Whether to pretty-print the JSON output with indentation.",
)
@click_extra.pass_obj
def dump_database(ctx_obj: CLIDbContext, output_file: Path, pretty: bool) -> None:
    """Dump the entire database to a JSON file."""
    with get_db_session() as session:
        serialize_database(session, filename=output_file, indent=2 if pretty else None)



@manage_cli.command(name="load-db")
@click_extra.argument(
    'input_file',
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click_extra.option(
    "--limit-to-models",
    type=str,
    multiple=True,
    help="Limit deserialization to specific models by name.",
)
@click_extra.pass_obj
def load_database(ctx_obj: CLIDbContext, input_file: Path, limit_to_models: list[str]) -> None:
    """Load the entire database from a JSON file."""
    with get_db_session() as session:
        deserialize_database(
            session,
            input_file,
            limit_to_models=limit_to_models if len(limit_to_models) > 0 else None,
        )
