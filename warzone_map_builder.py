#!/usr/bin/env python

from argparse import ArgumentParser
from enum import Enum
import json
import re
from typing import Dict, List, Set, Tuple, Union

import inkex
from inkex import AbortExtension, NSS
from inkex.utils import debug


Command = Dict[str, Union[str, int]]

SET_MAP_DETAILS_URL = 'https://www.warzone.com/API/SetMapDetails'


def get_uri(key: str) -> str:
    if ':' in key:
        namespace, key = key.split(':')
        key = f'{{{NSS[namespace]}}}{key}'
    return key


class Svg:
    ID = 'id'
    GROUP = 'svg:g'
    PATH = 'svg:path'
    TITLE = 'svg:title'
    CLONE = 'svg:use'
    ELLIPSE = 'svg:ellipse'
    RECTANGLE = 'svg:rect'
    TEXT = 'svg:text'
    TSPAN = 'svg:tspan'

    STYLE = 'style'
    FILL = 'fill'
    STROKE = 'stroke'
    STROKE_WIDTH = 'stroke-width'


class Inkscape:
    LABEL = 'inkscape:label'
    GROUP_MODE = 'inkscape:groupmode'
    CONNECTION_START = 'inkscape:connection-start'
    CONNECTION_END = 'inkscape:connection-end'
    CONNECTOR_CURVATURE = 'inkscape:connector-curvature'
    CONNECTOR_TYPE = 'inkscape:connector-type'

    LAYER = 'layer'


class XLink:
    HREF = 'xlink:href'


class MapLayers:
    BONUS_LINKS = 'WZ:BonusLinks'
    TERRITORIES = 'WZ:Territories'
    BACKGROUND = 'Background'

    METADATA = 'WZ:Metadata'
    BONUSES = 'WZ:Bonuses'
    DISTRIBUTION_MODES = 'WZ:DistributionModes'
    CONNECTIONS = 'WZ:Connections'
    WRAP_NORMAL = 'Normal'
    WRAP_HORIZONTAL = 'WrapHorizontally'
    WRAP_VERTICAL = 'WrapVertically'


class Color:
    BLACK = '#000000'
    WHITE = '#FFFFFF'

    CONNECTIONS = BLACK
    TERRITORY_FILL = WHITE
    DEFAULT_BONUS_COLOR = BLACK
    BONUS_LINK_STROKE = '#FFFF00'


class Warzone:
    TERRITORY_IDENTIFIER = 'Territory_'
    BONUS_LINK_IDENTIFIER = 'BonusLink_'

    UNNAMED_TERRITORY_NAME = 'Unnamed'

    BONUS_LINK_SIDE = 20

    RECT_WIDTH = 20
    RECT_HEIGHT = 15
    RECT_ROUNDING = 4

    ARMY_FONT_SIZE = 13     # px


class Operation(Enum):
    CREATE = 'create'
    UPDATE = 'update'
    DELETE = 'delete'
    ADD_TERRITORIES = 'add'
    REPLACE_TERRITORIES = 'replace'


class WZMapBuilder(inkex.EffectExtension):

    TAB_OPTIONS = ['about', 'territories', 'connections', 'bonuses', 'distributions', 'upload']
    TERRITORY_TAB_OPTIONS = ['create', 'name', 'center-point']
    BONUS_TAB_OPTIONS = ['create-update', 'bonus-territories', 'delete']
    BONUS_CREATE_UPDATE_TAB_OPTIONS = ['create', 'update']
    BONUS_TERRITORY_TAB_OPTIONS = ['add', 'replace']
    DISTRIBUTION_TAB_OPTIONS = ['crud', 'distribution-territories']
    DISTRIBUTION_CRUD_TAB_OPTIONS = ['create', 'update', 'delete']

    def add_arguments(self, ap: ArgumentParser) -> None:
        ap.add_argument("--tab", type=str, default='about')

        # arguments for territories
        ap.add_argument("--territory_tab", type=str, default='create')
        ap.add_argument("--territory_name", type=str, default=Warzone.UNNAMED_TERRITORY_NAME)
        ap.add_argument("--territory_layer", type=inkex.Boolean, default=True)
        ap.add_argument("--center_point_set_type", type=str, default='ellipse')

        # arguments for bonuses
        ap.add_argument("--bonus_name", type=str, default='')
        ap.add_argument("--bonus_tab", type=str, default='create-update')
        ap.add_argument("--bonus_properties_tab", type=str, default='create')
        ap.add_argument("--bonus_name_update", type=str, default='')
        ap.add_argument("--bonus_value", type=str, default='')
        ap.add_argument("--bonus_color", type=str, default='')
        ap.add_argument("--bonus_link_visible", type=inkex.Boolean, default=True)
        ap.add_argument("--bonus_territories_add_replace", type=str, default='add')

        # arguments for connections
        ap.add_argument("--connection_type", type=str, default='normal')

        # arguments for distribution modes
        ap.add_argument("--distribution_name", type=str, default='')
        ap.add_argument("--distribution_tab", type=str, default='crud')
        ap.add_argument("--distribution_crud_tab", type=str, default='create')
        ap.add_argument("--distribution_name_update", type=str, default='')
        ap.add_argument("--distribution_scenario_names", type=str, default='')
        ap.add_argument("--distribution_territories_add_replace", type=str, default='add')
        ap.add_argument("--distribution_territory_scenario_name", type=str, default='')

        # arguments for metadata upload
        ap.add_argument("--upload_email", type=str, default='')
        ap.add_argument("--upload_api_token", type=str, default='')
        ap.add_argument("--upload_map_id", type=int)
        ap.add_argument("--upload_territory_names", type=inkex.Boolean, default=False)
        ap.add_argument("--upload_territory_center_points", type=inkex.Boolean, default=False)
        ap.add_argument("--upload_connections", type=inkex.Boolean, default=False)
        ap.add_argument("--upload_bonuses", type=inkex.Boolean, default=False)
        ap.add_argument("--upload_territory_bonuses", type=inkex.Boolean, default=False)
        ap.add_argument("--upload_distribution_modes", type=inkex.Boolean, default=False)
        ap.add_argument("--upload_territory_distribution_modes", type=inkex.Boolean, default=False)

    def effect(self) -> None:
        self._clean_up_tab_inputs()
        self._setup_map_layers()
        return {
            'about': None,
            'territories': {
                'create': self._create_territories,
                'name': self._set_territory_name,
                'center-point': self._set_territory_center_point,
            }[self.options.territory_tab],
            'connections': self._set_connection,
            'bonuses': {
                'create-update': self._set_bonus,
                'bonus-territories': self._add_territories_to_bonus,
                'delete': self._delete_bonus,
            }[self.options.bonus_tab],
            'distributions': {
                'crud': self._set_distribution_mode,
                'distribution-territories': self._add_territories_to_distribution_mode
            }[self.options.distribution_tab],
            'upload': self._upload_metadata,
        }[self.options.tab]()

    ###########
    # EFFECTS #
    ###########

    def _create_territories(self) -> None:
        """
        Converts all selected paths to a Warzone Territories by setting a Warzone Territory ID and
        creating a territory group. Validates all existing territories as well as selected paths. If
        territory-layer checkbox is checked, move territories to the Territories layer.
        :return:
        """

        territory_layer = (
            self._get_metadata_layer(MapLayers.TERRITORIES)
            if self.options.territory_layer else None
        )
        existing_territories = set(get_territories(self.svg))
        max_id = self._get_max_territory_id(existing_territories)

        territories_to_process = existing_territories.union({
            selected for selected in self.svg.selection.filter(inkex.PathElement)
        })
        for territory in territories_to_process:
            territory_group = create_territory(territory, max_id, territory_layer)
            max_id = max(max_id, get_territory_id(territory_group))
        if not territories_to_process:
            raise AbortExtension("There are no territories selected. Territories must be paths.")

    def _set_territory_name(self) -> None:
        """
        Sets the title of the selected territory to the input name.
        :return:
        """

        if len(self.svg.selection) != 1:
            raise AbortExtension("Please select exactly one territory.")

        element = self.svg.selection.first()
        if isinstance(element, inkex.PathElement):
            raise AbortExtension(
                f"Please convert selected path into a territory before setting its name:"
                f" '{element.get_id()}'."
            )
        elif not is_territory_group(element):
            raise AbortExtension("You must select the territory group you want to name.")

        title = element.get_or_create(f"./{Svg.TITLE}", inkex.Title)
        title.text = self.options.territory_name

    def _set_territory_center_point(self) -> None:
        """
        Sets the center point of the selected territory to the center of the selected ellipse.
        :return:
        """
        if self.options.center_point_set_type == 'ellipse' and len(self.svg.selection) != 2:
            raise AbortExtension("Please select exactly one territory and one ellipse.")

        if elements := self.svg.selection.filter(inkex.PathElement):
            raise AbortExtension(
                f"Please convert selected path into a territory before setting its center point:"
                f" '{elements.pop().get_id()}'."
            )

        territories = [element for element in self.svg.selection if is_territory_group(element)]
        territory = territories.pop()
        bounding_box = self.find(f"./{Svg.PATH}", territory).bounding_box()

        if self.options.center_point_set_type == 'default':
            center = self.find(f'./{Svg.PATH}', territory).bounding_box().center
        else:
            ellipse = self.svg.selection.filter(inkex.Ellipse, inkex.Circle).first()

            if territory is None or ellipse is None:
                raise AbortExtension("Please select exactly one territory and one ellipse.")

            if (
                not (bounding_box.left < ellipse.center.x < bounding_box.right)
                or not (bounding_box.top < ellipse.center.y < bounding_box.bottom)
            ):
                raise AbortExtension("The center point must be within the territory.")

            center = ellipse.center

        territory.remove(self.find(f"./{Svg.GROUP}", territory))
        center_point = create_center_point_group(center)
        territory.add(center_point)

    def _set_bonus(self) -> None:
        """
        Creates or updates a bonus layer specified by a bonus name OR a selected bonus-link.
        Creates a bonus-link if necessary.
        :return:
        """
        operation = Operation(self.options.bonus_properties_tab)
        self._clean_up_bonus_inputs(operation)

        bonus_name = self.options.bonus_name
        bonus_value = self.options.bonus_value
        bonus_color = self.options.bonus_color
        bonus_link_path = self.options.bonus_link_path
        bonus_layer = self.options.bonus_layer

        if Operation.CREATE == operation:
            bonus_layer = inkex.Layer.new(f'{bonus_name}: {bonus_value}')
            bonus_layer.add(inkex.Title.new(bonus_color))
            self._get_metadata_layer(MapLayers.BONUSES).add(bonus_layer)
        else:
            bonus_value = bonus_value if bonus_value else get_bonus_value(bonus_layer)
            bonus_layer.label = f'{bonus_name}: {bonus_value}'
            self.find(Svg.TITLE, bonus_layer).text = bonus_color

        if self.options.bonus_link_visible:
            bonus_link = self._set_bonus_link(bonus_link_path, bonus_name, bonus_value, bonus_color)
            if find_clone(bonus_link, bonus_layer) is None:
                bonus_layer.add(inkex.Use.new(bonus_link, 0, 0))
        else:
            remove_bonus_link(bonus_link_path)

    def _add_territories_to_bonus(self) -> None:
        """
        Adds or replaces selected territories for bonus layer specified by a bonus name OR a
        selected bonus-link. Raises an error if both are provided and don't have compatible names.
        :return:
        """
        operation = Operation(self.options.bonus_territories_add_replace)
        self._clean_up_bonus_inputs(operation)

        bonus_layer = self.options.bonus_layer
        territory_groups = self.options.territories

        territory_clones = set()
        for element in bonus_layer.getchildren():
            if isinstance(element, inkex.Use):
                linked_element = element.href
                if is_territory_group(linked_element):
                    if operation == Operation.REPLACE_TERRITORIES:
                        bonus_layer.remove(element)
                    else:
                        territory_clones.add(linked_element.get_id())

        for territory_group in territory_groups:
            if not territory_group.get_id() in territory_clones:
                bonus_layer.insert(0, inkex.Use.new(territory_group, 0, 0))
        
        self._set_territory_stroke()

    def _delete_bonus(self) -> None:
        self._clean_up_bonus_inputs(Operation.DELETE)

        bonus_layer = self.options.bonus_layer
        bonus_link_path = self.options.bonus_link_path

        bonus_layer.getparent().remove(bonus_layer)
        if bonus_link_path is not None:
            remove_bonus_link(bonus_link_path)
        self._set_territory_stroke()

    def _set_connection(self) -> None:
        territory_groups = [group for group in self.svg.selection if is_territory_group(group)]
        territory_groups.extend([
            element.getparent() for element in self.svg.selection
            if is_territory_group(element.getparent())
        ])
        endpoint_ids = [
            self.find(f"./{Svg.GROUP}/{Svg.RECTANGLE}", group).get_id()
            for group in territory_groups
        ]

        if (count := len(endpoint_ids)) != 2:
            raise AbortExtension(
                f"Must have exactly 2 selected territories. {count} territories are selected."
            )

        connector = inkex.PathElement.new(
            "", style=inkex.Style(stroke=Color.CONNECTIONS, stroke_width=1.0),
        )

        connector.set(Inkscape.CONNECTION_START, f'#{endpoint_ids[0]}')
        connector.set(Inkscape.CONNECTION_END, f'#{endpoint_ids[1]}')
        connector.set(Inkscape.CONNECTOR_CURVATURE, 0)
        connector.set(Inkscape.CONNECTOR_TYPE, 'polyline')

        connection_type_layer = self._get_metadata_layer(
            self.options.connection_type,
            parent=self._get_metadata_layer(MapLayers.CONNECTIONS)
        )
        connection_type_layer.add(connector)

    def _set_distribution_mode(self) -> None:
        """
        Create, update, or delete distribution mode or scenarios.
        :return:
        """
        operation = Operation(self.options.distribution_crud_tab)
        self._clean_up_distribution_inputs(operation)

        distribution_name = self.options.distribution_name
        scenario_names = self.options.distribution_scenario_names
        distribution_layer = self.options.distribution_layer

        if operation == Operation.CREATE:
            distribution_layer = inkex.Layer.new(distribution_name)
            scenario_layers = [inkex.Layer.new(scenario_name) for scenario_name in scenario_names]
            distribution_layer.add(*scenario_layers)
            self._get_metadata_layer(MapLayers.DISTRIBUTION_MODES).add(distribution_layer)
        elif operation == Operation.UPDATE:
            distribution_layer.label = distribution_name
            if scenario_names:
                for child in distribution_layer.getchildren():
                    if not isinstance(child, inkex.Layer):
                        distribution_layer.remove(child)

                for scenario_name in scenario_names:
                    scenario_layer = distribution_layer.get_or_create(
                        f"./{Svg.GROUP}"
                        f"[@{Inkscape.GROUP_MODE}='{Inkscape.LAYER}'"
                        f" and @{Inkscape.LABEL}='{scenario_name}']",
                        inkex.Layer
                    )
                    scenario_layer.label = scenario_name
        elif operation == Operation.DELETE:
            if not scenario_names:
                distribution_layer.getparent().remove(distribution_layer)
            else:
                layers = {
                    layer.label: layer for layer in distribution_layer.getchildren()
                }

                for scenario_name in scenario_names:
                    distribution_layer.remove(layers[scenario_name])
        else:
            raise AbortExtension(
                f"Invalid distribution mode operation: '{self.options.distribution_crud_tab}'"
            )

    def _add_territories_to_distribution_mode(self) -> None:
        """
        Adds of replaces selected territories for distribution mode layer specified by distribution
        mode name. Raises and error if a scenario is named for a non-scenario distribution mode or
        if no scenario is named for a scenario distribution.
        :return:
        """
        operation = Operation(self.options.distribution_territories_add_replace)
        self._clean_up_distribution_inputs(operation)

        distribution_layer = self.options.distribution_layer
        territory_groups = self.options.territories

        if operation == Operation.REPLACE_TERRITORIES:
            distribution_layer.remove_all()

        existing_territory_ids = set()
        for element in distribution_layer.getchildren():
            linked_element = element.href
            existing_territory_ids.add(linked_element.get_id())

        for territory_group in territory_groups:
            if not territory_group.get_id() in existing_territory_ids:
                distribution_layer.add(inkex.Use.new(territory_group, 0, 0))

    def _upload_metadata(self) -> None:
        commands = self._get_set_metadata_commands()
        self._post_map_details(commands)

    ##################
    # HELPER METHODS #
    ##################

    def _post_map_details(self, commands: List[Command]) -> None:
        import requests
        response = requests.post(
            url=SET_MAP_DETAILS_URL,
            json={
                'email': self.options.upload_email,
                'APIToken': self.options.upload_api_token,
                'mapID': self.options.upload_map_id,
                'commands': commands,
            }
        )

        debug(json.loads(response.text))

    def _get_set_metadata_commands(self) -> List[Command]:
        commands = []
        if self.options.upload_territory_names:
            commands += self._get_set_territory_name_commands()
        if self.options.upload_territory_center_points:
            commands += self._get_set_territory_center_point_commands()
        if self.options.upload_connections:
            commands += self._get_add_territory_connections_commands()
        if self.options.upload_bonuses:
            commands += self._get_add_bonus_commands()
        if self.options.upload_territory_bonuses:
            commands += self._get_add_territory_to_bonus_commands()
        if self.options.upload_distribution_modes:
            commands += self._get_add_distribution_mode_commands()
        if self.options.upload_territory_distribution_modes:
            commands += self._get_add_territory_to_distribution_commands()
        return commands

    ###################
    # COMMAND GETTERS #
    ###################

    def _get_set_territory_name_commands(self) -> List[Command]:
        """
        Parses svg and creates setTerritoryName commands.

        A command is created for each territory group with a title.

        :return:
        List of setTerritoryName commands
        """
        return [
            {
                'command': 'setTerritoryName',
                'id': get_territory_id(territory_group),
                'name': get_territory_name(territory_group)
            }
            for territory_group in get_territory_groups(self.svg, is_recursive=True)
            if get_territory_name(territory_group)
        ]

    def _get_set_territory_center_point_commands(self) -> List[Command]:
        """
        Parses svg and sets territory center points.

        A command is created for each Territory
        :return:
        List of setTerritoryCenterPoint commands
        """
        territory_centers = {
            get_territory_id(territory_group): get_territory_center(territory_group)
            for territory_group in get_territory_groups(self.svg, is_recursive=True)
        }

        return [
            {
                'command': 'setTerritoryCenterPoint',
                'id': territory_id,
                'x': center_point.x,
                'y': center_point.y
            } for territory_id, center_point in territory_centers.items()
        ]

    def _get_add_territory_connections_commands(self) -> List[Command]:
        """
        Parses svg and creates addTerritoryConnection commands

        A command is created for each diagram connector that connects two groups containing a
        territory.
        :return:
        List of addTerritoryConnection commands
        """
        return [
            {
                'command': 'addTerritoryConnection',
                'id1': self.get_connection_endpoint_id(connection, Inkscape.CONNECTION_START),
                'id2': self.get_connection_endpoint_id(connection, Inkscape.CONNECTION_END),
                'wrap': connection.getparent().label
            }
            for connection in get_connections(self._get_metadata_layer(MapLayers.CONNECTIONS))
        ]

    def _get_add_bonus_commands(self) -> List[Command]:
        """
        Parses svg and creates addBonus commands.

        A command is created for each sub-layer of the WZ:Bonuses layer. Each of these sub-layers is
        assumed to have a name of the form `bonus_name: bonus_value`. If a path node exists with the
        id f"{Warzone.BONUS_IDENTIFIER}bonus_name" the fill color of that path is used as the bonus
        color, otherwise the bonus color is black.

        :return:
        List of addBonus commands
        """

        return [
            {
                'command': 'addBonus',
                'name': get_bonus_name(bonus),
                'armies': get_bonus_value(bonus),
                'color': get_bonus_color(bonus)
            }
            for bonus in self._get_metadata_type_layers(MapLayers.BONUSES)
        ]

    def _get_add_territory_to_bonus_commands(self) -> List[Command]:
        """
        Parses svg and creates addTerritoryToBonus commands.

        Each sub-layer of the WZ:Bonuses layer is assumed to contain clones of Territory nodes (i.e.
        path nodes whose id starts with Warzone.TERRITORY_IDENTIFIER). A command is created for the
        linked territory of each clone in each of these sub-layers adding that territory to the
        bonus of the layer it is in.

        :return:
        List of addTerritoryToBonus commands
        """
        bonus_layers = self._get_metadata_type_layers(MapLayers.BONUSES)

        commands = []
        for bonus_layer in bonus_layers:
            for element in bonus_layer.getchildren():
                if isinstance(element, inkex.Use):
                    linked_element = element.href
                    if is_territory_group(linked_element):
                        commands.append({
                            'command': 'addTerritoryToBonus',
                            'id': get_territory_id(linked_element),
                            'bonusName': get_bonus_name(bonus_layer)
                        })
        return commands

    def _get_add_distribution_mode_commands(self) -> List[Command]:
        """
        Parses svg and creates addDistributionMode commands.

        A command is created for each sub-layer of the WZ:DistributionModes layer. Each of these
        sub-layers should be named with the name of the distribution mode.

        :return:
        List of addDistributionMode commands
        """
        distribution_mode_layer = self._get_metadata_layer(MapLayers.DISTRIBUTION_MODES)
        commands = []
        for distribution_mode in distribution_mode_layer.getchildren():
            command = {
                'command': 'addDistributionMode',
                'name': distribution_mode.label
            }
            if is_scenario_distribution(distribution_mode):
                command['scenarios'] = [
                    scenario.label for scenario in distribution_mode.getchildren()
                ]
            commands.append(command)
        return commands

    def _get_add_territory_to_distribution_commands(self) -> List[Command]:
        """
        Parses svg and creates addTerritoryToDistribution commands.

        Each sub-layer of the WZ:DistributionModes layer is assumed to contain clones of Territory
        nodes (i.e. path nodes whose id starts with Warzone.TERRITORY_IDENTIFIER). A command is
        created for the linked territory of each clone in each of these sub-layers adding that
        territory to the distribution mode of the layer it is in.

        :return:
        List of addTerritoryToDistribution commands
        """
        distribution_mode_layer = self._get_metadata_layer(MapLayers.DISTRIBUTION_MODES)
        commands = []
        for distribution_mode in distribution_mode_layer.getchildren():
            if is_scenario_distribution(distribution_mode):
                for scenario in distribution_mode.getchildren():
                    for territory in scenario.getchildren():
                        commands.append({
                            'command': 'addTerritoryToDistribution',
                            'id': get_territory_id(territory.href),
                            'distributionName': distribution_mode.label,
                            'scenario': scenario.label
                        })
            else:
                for territory in distribution_mode.getchildren():
                    commands.append({
                        'command': 'addTerritoryToDistribution',
                        'id': get_territory_id(territory.href),
                        'distributionName': distribution_mode.label,
                    })
        return commands

    ####################
    # VALIDATION UTILS #
    ####################

    def _clean_up_tab_inputs(self) -> None:

        self.options.tab = self.options.tab if self.options.tab in self.TAB_OPTIONS else 'about'
        self.options.territory_tab = (
            self.options.territory_tab if self.options.territory_tab in self.TERRITORY_TAB_OPTIONS
            else 'create'
        )
        self.options.bonus_tab = (
            self.options.bonus_tab if self.options.bonus_tab in self.BONUS_TAB_OPTIONS
            else 'create-update'
        )
        self.options.bonus_properties_tab = (
            self.options.bonus_properties_tab
            if self.options.bonus_properties_tab in self.BONUS_CREATE_UPDATE_TAB_OPTIONS
            else 'create'
        )
        self.options.distribution_tab = (
            self.options.distribution_tab
            if self.options.distribution_tab in self.DISTRIBUTION_TAB_OPTIONS
            else 'crud'
        )
        self.options.distribution_crud_tab = (
            self.options.distribution_crud_tab
            if self.options.distribution_crud_tab in self.DISTRIBUTION_CRUD_TAB_OPTIONS
            else 'create'
        )

    def _clean_up_bonus_inputs(self, operation: Operation) -> None:
        """
        Gets true inputs for bonus name, bonus link, and bonus layer. Raises an informative
        exception if the bonus input doesn't validate.
        :return:
        """
        is_create_update = operation in [Operation.CREATE, Operation.UPDATE]
        is_update_territories = operation in [
            Operation.ADD_TERRITORIES, Operation.REPLACE_TERRITORIES
        ]

        bonus_name = self.options.bonus_name
        bonus_link = self._get_bonus_link_path_from_selection()

        if not bonus_name:
            if Operation.CREATE == operation:
                raise AbortExtension("Must provide a bonus name when creating a new bonus.")
            if bonus_link is None:
                raise AbortExtension(
                    "Either a bonus name must be provided or a bonus link must be selected."
                )
            else:
                bonus_name = bonus_link.get_id().split(Warzone.BONUS_LINK_IDENTIFIER)[-1]

        if bonus_link is not None and get_bonus_link_id(bonus_name) != bonus_link.get_id():
            raise AbortExtension(
                f"Bonus name '{bonus_name}' is not consistent with the selected bonus link"
                f" '{bonus_link.get_id()}'."
            )

        bonus_name_update = (
            self.options.bonus_name_update if Operation.UPDATE == operation else bonus_name
        )

        bonus_link = (
            bonus_link if bonus_link is not None
            else self._get_bonus_link_path_from_name(bonus_name)
        )

        if is_update_territories:
            self._validate_add_territory_inputs()

        target_bonus_layers = self._get_bonus_layers_with_name(bonus_name_update)

        if operation == Operation.CREATE:
            bonus_layer = None
        else:
            existing_bonus_layers = (
                target_bonus_layers if bonus_name == bonus_name_update
                else self._get_bonus_layers_with_name(bonus_name)
            )
            if not existing_bonus_layers:
                operation = 'delete' if operation == Operation.DELETE else 'modify'
                raise AbortExtension(f"Cannot {operation} non-existent bonus '{bonus_name}'.")
            elif len(existing_bonus_layers) > 1:
                raise AbortExtension(
                    f"Too many bonus layers match the bonus name {bonus_name}:"
                    f" {[layer.label for layer in existing_bonus_layers]}"
                )
            bonus_layer = existing_bonus_layers[0]

        if is_create_update and target_bonus_layers:
            raise AbortExtension(
                f"Cannot create bonus '{bonus_name_update}' as bonus layers for this name already"
                f" exist: {[layer.label for layer in target_bonus_layers]}."
            )

        if is_create_update:
            if not self.options.bonus_color:
                if bonus_link is not None:
                    self.options.bonus_color = bonus_link.effective_style().get_color()
                elif bonus_layer and (layer_color := bonus_layer.find(Svg.TITLE, NSS)) is not None:
                    self.options.bonus_color = layer_color.text
                else:
                    self.options.bonus_color = Color.DEFAULT_BONUS_COLOR

            if self.options.bonus_value != '':
                try:
                    int(self.options.bonus_value)
                except ValueError:
                    raise AbortExtension(
                        f"If a bonus value is provided it must be an integer."
                        f" Provided '{self.options.bonus_value}'."
                    )
            elif operation == Operation.CREATE:
                raise AbortExtension(f"Must provide a bonus value when creating a new bonus.")

            try:
                inkex.Color(self.options.bonus_color)
            except inkex.colors.ColorError:
                raise AbortExtension(
                    f"If a bonus color is provided if must be an RGB string in the form '#00EE33'."
                    f" Provided {self.options.bonus_color}"
                )

        self.options.bonus_name = bonus_name_update if bonus_name_update else bonus_name
        self.options.bonus_link_path = bonus_link
        self.options.bonus_layer = bonus_layer

    def _clean_up_distribution_inputs(self, operation: Operation) -> None:
        is_create_update = operation in [Operation.CREATE, Operation.UPDATE]
        is_update_territories = operation in [
            Operation.ADD_TERRITORIES, Operation.REPLACE_TERRITORIES
        ]

        distribution_name = self.options.distribution_name

        if not distribution_name:
            raise AbortExtension("Must provide a distribution mode name.")

        distribution_name_update = (
            self.options.distribution_name_update if Operation.UPDATE == operation
            else distribution_name
        )

        target_distribution_layers = (
            self._get_distribution_layers_with_name(distribution_name_update)
        )

        if operation == Operation.CREATE:
            distribution_layer = None
        else:
            existing_distribution_layers = (
                target_distribution_layers if distribution_name == distribution_name_update
                else self._get_distribution_layers_with_name(distribution_name)
            )
            if not existing_distribution_layers:
                operation = 'delete' if operation == Operation.DELETE else 'modify'
                raise AbortExtension(
                    f"Cannot {operation} non-existent bonus '{distribution_name}'."
                )
            elif len(existing_distribution_layers) > 1:
                raise AbortExtension(
                    f"Too many distribution mde layers match the distribution mode name"
                    f" {distribution_name}:"
                    f" {[layer.label for layer in existing_distribution_layers]}"
                )
            distribution_layer = existing_distribution_layers[0]

        if is_create_update and target_distribution_layers:
            raise AbortExtension(
                f"Cannot create distribution mode '{distribution_name_update}' as distribution mode"
                f" layers for this name already exist:"
                f" {[layer.label for layer in target_distribution_layers]}."
            )

        if is_update_territories:
            scenario_name = self.options.distribution_territory_scenario_name
            if is_scenario_distribution(distribution_layer):
                if not scenario_name:
                    raise AbortExtension(
                        "When adding a territory to a scenario distribution, you must provide the"
                        " scenario name."
                    )
                distribution_layer = self.find(
                    f"./{Svg.GROUP}[@{Inkscape.LABEL}='{scenario_name}']", distribution_layer
                )
                if distribution_layer is None:
                    raise AbortExtension(
                        f"Cannot add territories to scenario '{scenario_name}'. It is not a"
                        f" scenario of distribution mode '{distribution_name}'"
                    )
            elif scenario_name:
                raise AbortExtension(
                    f"'{distribution_name}' is not a scenario distribution. Please remove the"
                    f" scenario name."
                )

            self._validate_add_territory_inputs()

        # noinspection PyUnresolvedReferences
        scenario_names = {
            name for name in self.options.distribution_scenario_names.split('\\n') if name
        }

        if operation == Operation.CREATE and len(scenario_names) == 1:
            raise AbortExtension(
                "If creating a scenario distribution, you must provide at least TWO scenarios."
            )
        if operation == Operation.DELETE:
            scenario_layer_names = {layer.label for layer in distribution_layer.getchildren()}
            if non_existent_layers := scenario_names - scenario_layer_names:
                raise AbortExtension(f"Can't delete non-existent scenarios {non_existent_layers}.")
            if len(remaining_layers := scenario_layer_names - scenario_names) < 2:
                additional_message = (
                    f"The only remaining scenario is '{remaining_layers.pop()}'."
                    if remaining_layers else
                    "There are no remaining layers. \n\nIf you want to delete the whole"
                    " distribution, you shouldn't specify any scenarios."
                )
                raise AbortExtension(
                    "There must be at least TWO scenarios left when deleting scenarios from a"
                    f" scenario distribution. {additional_message}"
                )

        self.options.distribution_name = (
            distribution_name_update if distribution_name_update else distribution_name
        )
        self.options.distribution_layer = distribution_layer
        self.options.distribution_scenario_names = scenario_names

    def _validate_add_territory_inputs(self) -> None:
        if selected_paths := self.svg.selection.filter(inkex.PathElement):
            raise AbortExtension(
                f"Please convert all selected paths into territories before adding them to a"
                f" bonus: {[path.get_id() for path in selected_paths]}."
            )

        territories = [group for group in self.svg.selection if is_territory_group(group)]
        if not territories:
            raise AbortExtension("No territories have been selected.")

        self.options.territories = territories

    #################
    # PARSING UTILS #
    #################

    def find(self, xpath: str, root: inkex.BaseElement = None):
        """
        Finds a single element corresponding to the xpath from the root element. If no root provided
        the svg document root is used.
        :param xpath:
        :param root:
        :return:
        """
        return find(xpath, root if root is not None else self.svg)

    def _get_metadata_layer(
            self,
            metadata_type: str,
            create: bool = False,
            parent: inkex.Layer = None
    ) -> inkex.Layer:
        """
        Returns the specified metadata layer node. If create, will create node if it doesn't exist.
        If parent layer not selected, use svg root layer.
        :param metadata_type:
        :param create:
        :return:
        """
        parent = parent if parent is not None else self.svg
        layer = self.find(f"./{Svg.GROUP}[@{Inkscape.LABEL}='{metadata_type}']", parent)
        if layer is None and create:
            layer = inkex.Layer.new(metadata_type)
            parent.add(layer)
        return layer

    def _get_max_territory_id(self, territories: Set[inkex.PathElement] = None) -> int:
        """
        Gets the maximum territory id as an int in the territories. If territories is None, searches
        the whole svg.
        :return:
        maximum int id
        """
        territories = get_territories(self.svg) if territories is None else territories
        max_id = max([0] + [get_territory_id(territory) for territory in territories])
        return max_id

    def _get_metadata_type_layers(
            self, metadata_type: str, is_recursive: bool = True
    ) -> List[inkex.Layer]:
        """
        Returns all layers of the input type. If not recursive only retrieves top-level layers
        :param metadata_type:
        :param is_recursive:
        :return:
        metadata layers
        """
        slash = '//' if is_recursive else '/'
        bonus_layers = self.svg.xpath(
            f"./{Svg.GROUP}[@{Inkscape.LABEL}='{metadata_type}']"
            f"{slash}{Svg.GROUP}[@{Inkscape.GROUP_MODE}='{Inkscape.LAYER}']",
            namespaces=NSS
        )
        return bonus_layers

    def get_connection_endpoint_id(self, connection: inkex.PathElement, endpoint_type: str) -> int:
        """
        Get the numeric id of the start territory of the connection
        :param connection:
        :param endpoint_type
        :return:
        """
        rectangle_id = connection.get(get_uri(endpoint_type)).split('#')[-1]
        territory_group = self.svg.getElementById(rectangle_id).getparent().getparent()
        return get_territory_id(territory_group)

    def _get_bonus_link_path_from_name(self, bonus_name: str) -> inkex.PathElement:
        """
        Gets a bonus link path from name. Returns None if there aren't any
        :param bonus_name:
        :return:
        """
        bonus_link = self.svg.getElementById(get_bonus_link_id(bonus_name), elm=Svg.PATH)
        return bonus_link

    def _get_bonus_link_path_from_selection(self) -> inkex.PathElement:
        """
        Gets a bonus link path from selection. Returns None if there aren't any and raises an
        exception if there is more than one.
        :return:
        """
        selected_bonus_links = [
            self.find(f"./{Svg.PATH}", group)
            for group in self.svg.selection.filter(inkex.Group) if is_bonus_link_group(group)
        ]
        selected_bonus_links.extend([
            path for path in self.svg.selection.filter(inkex.PathElement)
            if Warzone.BONUS_LINK_IDENTIFIER in path.get_id()
        ])
        if len(selected_bonus_links) == 1:
            bonus_link = selected_bonus_links[0]
        elif not selected_bonus_links:
            bonus_link = None
        else:
            raise AbortExtension("Multiple bonus links have been selected.")
        return bonus_link

    def _get_bonus_layers_with_name(self, bonus_name: str) -> List[inkex.Layer]:
        bonus_link_id = get_bonus_link_id(bonus_name)
        return [
            layer for layer in self._get_metadata_type_layers(MapLayers.BONUSES)
            if bonus_link_id == get_bonus_link_id(get_bonus_name(layer))
        ]

    def _get_distribution_layers_with_name(self, distribution_name_update):
        return (
            self._get_metadata_layer(MapLayers.DISTRIBUTION_MODES)
            .xpath(f"./{Svg.GROUP}[@{Inkscape.LABEL}='{distribution_name_update}']")
        )

    ####################
    # METADATA SETTERS #
    ####################

    def _setup_map_layers(self):
        self._get_metadata_layer(MapLayers.DISTRIBUTION_MODES, create=True)
        self._get_metadata_layer(MapLayers.BONUSES, create=True)
        self._get_metadata_layer(MapLayers.TERRITORIES, create=True)

        connections_layer = self._get_metadata_layer(MapLayers.CONNECTIONS, create=True)
        self._get_metadata_layer(MapLayers.WRAP_VERTICAL, create=True, parent=connections_layer)
        self._get_metadata_layer(MapLayers.WRAP_HORIZONTAL, create=True, parent=connections_layer)
        self._get_metadata_layer(MapLayers.WRAP_NORMAL, create=True, parent=connections_layer)

        self._get_metadata_layer(MapLayers.BONUS_LINKS, create=True)

    def _set_bonus_link(
            self, bonus_link_path: inkex.PathElement,
            bonus_name: str,
            bonus_value: str,
            bonus_color: str
    ) -> inkex.Group:
        """
        Creates a bonus link if it doesn't exist and adds it to the bonus link layer. Updates any
        properties of bonus link it if already exists.

        :return:
        bonus link
        """
        bonus_link_id = get_bonus_link_id(bonus_name)

        # Create bonus link path if it does not exist
        if bonus_link_path is None:
            # todo figure out a good way to position a new bonus link
            location = (
                self.svg.selection.bounding_box().center if self.svg.selection.bounding_box()
                else self.svg.get_page_bbox().center
            )
            bonus_link_path = inkex.Rectangle.new(
                left=location.x - Warzone.BONUS_LINK_SIDE / 2,
                top=location.y - Warzone.BONUS_LINK_SIDE / 2,
                width=Warzone.BONUS_LINK_SIDE,
                height=Warzone.BONUS_LINK_SIDE,
                ry=Warzone.RECT_ROUNDING,
                rx=Warzone.RECT_ROUNDING,
            ).to_path_element()

        bonus_link_path.set_id(bonus_link_id)

        # Set bonus link fill and stroke
        bonus_link_style = bonus_link_path.effective_style()
        bonus_link_style.set_color(Color.BONUS_LINK_STROKE, name=Svg.STROKE)
        bonus_link_style.set_color(bonus_color)

        # Get bonus link group
        parent = bonus_link_path.getparent()
        if is_bonus_link_group(parent):
            bonus_link = parent
        else:
            # Create bonus link group if it doesn't exist
            location = bonus_link_path.bounding_box().center
            bonus_link = inkex.Group.new(
                bonus_link_id,
                bonus_link_path,
                inkex.TextElement.new(
                    create_tspan(bonus_value, font_color=Color.WHITE),
                    x=location.x,
                    y=location.y + Warzone.ARMY_FONT_SIZE * 3 / 8,
                ),
            )

        bonus_link.label = bonus_link_id

        # Set bonus link font color
        tspan = find(f"./{Svg.TEXT}/{Svg.TSPAN}", bonus_link)
        tspan.effective_style().set_color(
            Color.WHITE if bonus_link_style.get_color().to_rgb().to_hsl().lightness < 128
            else Color.BLACK
        )
        # Set bonus link value
        tspan.text = bonus_value

        # Add bonus link to bonus link layer
        bonus_link_layer = self._get_metadata_layer(MapLayers.BONUS_LINKS)
        if bonus_link.getparent() != bonus_link_layer:
            bonus_link_layer.add(bonus_link)
        return bonus_link

    def _get_or_create_bonus_layer(self, bonus_link: inkex.PathElement) -> inkex.Layer:
        """
        Finds the bonus layer corresponding to the old bonus name. Updates the bonus name and value
        if needed. Creates a new bonus layer if no bonus exists for that name. If a bonus link is
        provided, will update that bonus.
        :param bonus_link
        :return:
        bonus layer
        """
        old_bonus_name = self.options.bonus_name
        if bonus_link is not None:
            bonus_layers = self._get_metadata_type_layers(MapLayers.BONUSES)

            def find_bonus_layers_with_name(bonus_name: str) -> List[inkex.Layer]:
                return [
                    layer for layer in bonus_layers
                    if bonus_name == get_bonus_link_id(
                        get_bonus_name(layer)
                    ).split(Warzone.BONUS_LINK_IDENTIFIER)[-1]
                ]

            # raise exception if layer with new bonus name already exists
            if find_bonus_layers_with_name(self.options.bonus_name):
                raise AbortExtension(
                    f"Cannot rename bonus with bonus link to {self.options.bonus_name}. A bonus"
                    f" with that name already exists."
                )

            # set old bonus name to matching bonus layer name if exists
            bonus_link_id = bonus_link.get_id().split(Warzone.BONUS_LINK_IDENTIFIER)[-1]
            matching_bonus_layers = find_bonus_layers_with_name(bonus_link_id)
            if len(matching_bonus_layers) == 1:
                old_bonus_name = get_bonus_name(matching_bonus_layers[0])
            elif len(matching_bonus_layers) > 1:
                raise AbortExtension(
                    f"Multiple bonus layers exist matching bonus link {bonus_link_id}: "
                    f"{[layer.label for layer in matching_bonus_layers]}"
                )

        # get bonuses layer
        bonuses_layer = self._get_metadata_layer(MapLayers.BONUSES)

        # get bonus layer for old bonus name and create if not exists
        bonus_layer = self.find(
            f"./{Svg.GROUP}[contains(@{Inkscape.LABEL}, '{old_bonus_name}: ')]", bonuses_layer
        )
        if bonus_layer is None:
            try:
                bonus_value = int(self.options.bonus_value)
            except ValueError:
                raise AbortExtension(
                    f"If creating a new bonus, a bonus value must be provided as an integer."
                    f" Provided '{self.options.bonus_value}'"
                )
            if not self.options.bonus_name:
                raise AbortExtension("If no bonus link is selected, a bonus name must be provided.")
            bonus_layer = inkex.Layer.new(f'{self.options.bonus_name}: {bonus_value}')
            bonuses_layer.add(bonus_layer)
        else:
            try:
                bonus_value = int(
                    self.options.bonus_value if self.options.bonus_value != ''
                    else get_bonus_name(bonus_layer)[1]
                )
                self.options.bonus_value = str(bonus_value)
            except ValueError:
                raise AbortExtension(
                    f"If a bonus value is provided it must be an integer."
                    f" Provided {self.options.bonus_value}"
                )

            # update bonus name if name or value has changed
            new_bonus_name = self.options.bonus_name if self.options.bonus_name else old_bonus_name
            bonus_layer.label = f'{new_bonus_name}: {bonus_value}'

        return bonus_layer

    def _set_territory_stroke(self) -> None:
        processed_territory_ids = {None}
        for bonus_layer in self._get_metadata_type_layers(MapLayers.BONUSES):
            bonus_color = bonus_layer.find(Svg.TITLE, NSS).text

            for clone in bonus_layer.getchildren():
                if clone.get(XLink.HREF) in processed_territory_ids:
                    continue

                linked_element = clone.href
                if is_territory_group(linked_element):
                    territory = self.find(f"./{Svg.PATH}", linked_element)
                    territory.effective_style().set_color(bonus_color, name=Svg.STROKE)

                processed_territory_ids.add(clone.get(XLink.HREF))


def find(xpath: str, root: inkex.BaseElement):
    """
    Finds a single element corresponding to the xpath from the root element. If no root provided
    the svg document root is used.
    :param xpath:
    :param root:
    :return:
    """
    if 'contains(' in xpath:
        if target := root.xpath(xpath, NSS):
            target = target[0]
        else:
            target = None
    else:
        target = root.find(xpath, NSS)
    return target


def find_clone(element: inkex.BaseElement, root: inkex.Layer) -> inkex.Use:
    """
    Find a clone of the element which is a direct child of the root node.
    :param element:
    :param root:
    :return:
    """
    return find(f"./{Svg.CLONE}[@{XLink.HREF}='#{element.get_id()}']", root)


def is_territory_group(group: inkex.ShapeElement) -> bool:
    """
    Checks if element is a territory group. It is a territory group if it is a non-layer Group
    and has two children, one of which is a territory, the other of which is a center point
    group.
    :param group:
    :return:
    """
    valid = isinstance(group, inkex.Group)
    valid = valid and not isinstance(group, inkex.Layer)
    valid = valid and len(group.getchildren()) in [2, 3]
    valid = valid and len(get_territories(group, is_recursive=False)) == 1
    valid = valid and len(group.xpath(f"./{Svg.GROUP}[{Svg.RECTANGLE} and {Svg.TEXT}]")) == 1
    valid = valid and (len(group.getchildren()) == 2) or (len(group.xpath(f"./{Svg.TITLE}")) == 1)
    return valid


def is_territory(element: inkex.BaseElement) -> bool:
    """
    Checks if the given element is a territory
    :param element:
    :return:
    """
    return Warzone.TERRITORY_IDENTIFIER in element.get_id()


def get_territories(
        root: inkex.BaseElement, is_recursive: bool = True
) -> List[inkex.PathElement]:
    """
    Gets all territory elements that are children of the root node. If not is_recursive, gets
    only direct children.
    :param root:
    :param is_recursive:
    :return:
    """
    slash = '//' if is_recursive else '/'
    return root.xpath(
        f".{slash}{Svg.PATH}[contains(@{Svg.ID}, '{Warzone.TERRITORY_IDENTIFIER}')]",
        namespaces=NSS
    )


def get_territory_groups(
        root: inkex.BaseElement, is_recursive: bool = True
) -> List[inkex.Group]:
    return [
        territory.getparent() for territory in get_territories(root, is_recursive)
        if is_territory_group(territory.getparent())
    ]


def get_territory_id(territory: Union[str,  inkex.PathElement, inkex.Use, inkex.Group]) -> int:
    """
    Returns the id of the territory. If the argument is a string it must be of the form
    'Territory_X'. If the argument is a territory, it gets the int part of the element's id. If
    it is a clone, it gets the int part of the id of the linked element.
    :param territory:
    :return:
    territory id as required by the Warzone API
    """
    if isinstance(territory, str):
        territory_id = territory.split(Warzone.TERRITORY_IDENTIFIER)[-1]
    elif isinstance(territory, inkex.PathElement):
        territory_id = get_territory_id(territory.get(Svg.ID))
    elif isinstance(territory, inkex.Group) and is_territory_group(territory):
        territory_id = get_territory_id(get_territories(territory, is_recursive=False)[0])
    elif isinstance(territory, inkex.Use):
        territory_id = get_territory_id(territory.get(get_uri(XLink.HREF)))
    else:
        raise ValueError(f'Element {territory} is not a valid territory element. It must be a'
                         f' territory path, a territory group or a territory clone.')
    return int(territory_id)


def get_territory_name(territory: inkex.Group) -> str:
    """
    Get the name of the territory from its child title element. If no title, returns
    Warzone.UNNAMED_TERRITORY_NAME
    :param territory:
    :return:
    territory name
    """
    title = territory.find(Svg.TITLE, NSS)
    if title is not None:
        territory_name = title.text
    else:
        territory_name = None
    return territory_name


def get_territory_center(territory: inkex.Group) -> inkex.Vector2d:
    """
    Get the name of the territory from its child title element. If no title, returns
    Warzone.UNNAMED_TERRITORY_NAME
    :param territory:
    :return:
    territory name
    """
    center_rectangle: inkex.Rectangle = territory.find(f"./{Svg.GROUP}/{Svg.RECTANGLE}", NSS)
    return inkex.Vector2d(
        center_rectangle.left + center_rectangle.rx / 2,
        center_rectangle.top + center_rectangle.ry / 2
    )


def get_connections(
        root: inkex.BaseElement, is_recursive: bool = True
) -> List[inkex.PathElement]:
    """
    Gets all connections that are children of the root node. If not is_recursive, gets
    only direct children.
    :param root:
    :param is_recursive:
    :return:
    """
    slash = '//' if is_recursive else '/'
    return root.xpath(
        f".{slash}{Svg.PATH}[@{Inkscape.CONNECTION_START} and @{Inkscape.CONNECTION_END}]",
        namespaces=NSS
    )


def get_bonus_name(bonus_layer: inkex.Layer) -> str:
    """
    Parses a bonus layer's label to get the bonus name
    :param bonus_layer:
    :return:
    """
    return ': '.join(bonus_layer.label.split(': ')[:-1])


def get_bonus_value(bonus_layer: inkex.Layer) -> int:
    """
    Parses a bonus layer's label to get the bonus value.
    :param bonus_layer:
    :return:
    """
    return int(bonus_layer.label.split(': ')[-1])


def get_bonus_color(bonus_layer: inkex.Layer) -> str:
    """
    Parses a bonus layer's title to get the bonus color.
    :param bonus_layer:
    :return:
    """
    return find(Svg.TITLE, bonus_layer).text


def get_bonus_link_id(bonus_name: str) -> str:
    """
    Converts a bonus name to the corresponding ID for its bonus link
    :param bonus_name:
    :return:
    bonus link id
    """
    return Warzone.BONUS_LINK_IDENTIFIER + re.sub(r'[^a-zA-Z0-9]+', '', bonus_name)


def is_bonus_link_group(group: inkex.ShapeElement) -> bool:
    """
    Checks if element is a bonus link group. It is a bonus link group if it is a non-layer Group
    and has two children, one of which is a bonus link, the other of which is a text element.
    :param group:
    :return:
    """
    valid = isinstance(group, inkex.Group)
    valid = valid and not isinstance(group, inkex.Layer)
    valid = valid and len(group.getchildren()) == 2
    valid = valid and find(
        f"./{Svg.PATH}[contains(@{Svg.ID}, '{Warzone.BONUS_LINK_IDENTIFIER}')]", group
    ) is not None
    valid = valid and find(f"./{Svg.TEXT}", group) is not None
    return valid


def is_scenario_distribution(distribution_layer: inkex.Layer) -> bool:
    """
    Checks if the distribution layer is a scenario distribution layer. Assumes the input is a
    distribution layer.
    :param distribution_layer:
    :return:
    """
    return bool(
        [child for child in distribution_layer.getchildren() if isinstance(child, inkex.Layer)]
    )


def create_territory(
        territory_path: inkex.PathElement, max_id: int, territory_layer: inkex.Layer = None
) -> inkex.Group:
    """
    Converts territory path into a Warzone Territory.

    Sets the id of territory to the next Warzone Territory ID after the current maximum and
    creates a territory group containing a center-point and display army numbers. If
    territory_layer argument is passed, move territory group to the Territories layer.

    :param max_id:
    :param territory_path:
    :param territory_layer:
    :return maximum territory id as int
    """
    if Warzone.TERRITORY_IDENTIFIER not in territory_path.get_id():
        max_id += 1
        territory_path.set_id(f"{Warzone.TERRITORY_IDENTIFIER}{max_id}")
    parent: inkex.Group = territory_path.getparent()
    if not is_territory_group(parent):
        territory_group = inkex.Group.new(
            territory_path.get_id(),
            territory_path,
            create_center_point_group(territory_path.bounding_box().center),
        )
    else:
        territory_group = parent
        parent = territory_group.getparent()
    territory_style = territory_path.effective_style()
    territory_style[Svg.STROKE_WIDTH] = 1
    if territory_style.get_color() != Color.TERRITORY_FILL:
        territory_style.set_color(Color.TERRITORY_FILL)
    destination = territory_layer if territory_layer is not None else parent
    if territory_group not in destination:
        destination.add(territory_group)
    return territory_group


def remove_bonus_link(bonus_link: Union[inkex.Group, inkex.PathElement]) -> None:
    """
    Remove bonus link from the map
    :param bonus_link:
    :return:
    """
    if bonus_link is not None:
        if is_bonus_link_group(bonus_link.getparent()):
            element_to_remove = bonus_link.getparent()
        else:
            element_to_remove = bonus_link
        element_to_remove.getparent().remove(element_to_remove)


def create_center_point_group(center: inkex.Vector2d) -> inkex.Group:
    """
    Creates a group containing a rounded rectangle and sample army numbers centered at the
    input center-point
    :param center
    :return:
    center point group
    """
    # todo use https://blog.mapbox.com/a-new-algorithm-for-finding-a-visual-center-of-a-polygon-7c77e6492fbc
    #  to set a default center point
    return inkex.Group.new(
        'center-point',
        inkex.Rectangle.new(
            left=center.x - Warzone.RECT_WIDTH / 2,
            top=center.y - Warzone.RECT_HEIGHT / 2,
            width=Warzone.RECT_WIDTH,
            height=Warzone.RECT_HEIGHT,
            ry=Warzone.RECT_ROUNDING,
            rx=Warzone.RECT_ROUNDING,
            style=inkex.Style(
                fill='none',
                stroke=Color.TERRITORY_FILL,
                stroke_width=1.0,
                stroke_linecap='round',
                stroke_linejoin='round',
            ),
        ),
        inkex.TextElement.new(
            create_tspan('88', font_color=Color.BLACK),
            x=center.x,
            y=center.y + Warzone.ARMY_FONT_SIZE * 3 / 8,
        ),
    )


def create_tspan(bonus_value, font_color: str):
    return inkex.Tspan.new(
        bonus_value,
        style=inkex.Style(
            fill=font_color,
            font_weight='bold',
            font_size=f'{Warzone.ARMY_FONT_SIZE}px',
            text_align='center',
            text_anchor='middle',
        )
    )


WZMapBuilder().run()
