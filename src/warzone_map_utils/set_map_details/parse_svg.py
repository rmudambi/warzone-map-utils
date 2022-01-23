from lxml import etree

from warzone_map_utils.constants import types
from warzone_map_utils.constants.svg import Color, Inkscape, Map, Svg, Warzone, NAMESPACES
from warzone_map_utils.set_map_details import utilities


def get_set_map_details_commands(map_path: str) -> list[types.Command]:
    layers = utilities.get_layers(map_path)

    commands = (
        get_set_territory_name_commands(layers[Map.TERRITORIES_LAYER])
        + get_add_bonus_commands(layers[Map.BONUS_LINKS_LAYER], layers[Map.METADATA_LAYER])
        + get_add_territory_to_bonus_commands(layers[Map.METADATA_LAYER])
        + get_add_distribution_mode_commands(layers[Map.METADATA_LAYER])
        + get_add_territory_to_distribution_commands(layers[Map.METADATA_LAYER])
    )
    return commands


def get_set_territory_name_commands(territory_layer_node: etree.Element) -> list[types.Command]:
    territory_nodes = territory_layer_node.xpath(
        f".//{Svg.PATH}[contains(@{Svg.ID}, '{Warzone.TERRITORY_IDENTIFIER}') and {Svg.TITLE}]",
        namespaces=NAMESPACES
    )

    def get_set_territory_name_command(territory_node: etree.Element) -> types.Command:
        territory_id = int(
            territory_node.get(Svg.ID)
            .replace(Warzone.TERRITORY_IDENTIFIER, '')
        )

        title_node = territory_node.find(Svg.TITLE, NAMESPACES)
        territory_name = title_node.text
        command = {
            'command': 'setTerritoryName',
            'id': territory_id,
            'name': territory_name
        }
        return command

    commands = [
        get_set_territory_name_command(territory_node) for territory_node in territory_nodes
    ]
    return commands


def get_add_bonus_commands(
        bonus_link_layer_node: etree.Element, metadata_layer_node: etree.Element
) -> list[types.Command]:
    bonus_link_nodes = {
        node.get(Svg.ID): node for node in bonus_link_layer_node.xpath(
            f"./{Svg.PATH}[contains(@{Svg.ID}, '{Warzone.BONUS_LINK_IDENTIFIER}')]",
            namespaces=NAMESPACES
        )
    }
    bonus_layer_nodes = utilities.get_metadata_type_nodes(metadata_layer_node, Map.BONUSES_LAYER)

    def get_add_bonus_command(node: etree.Element) -> types.Command:
        bonus_name, bonus_value = utilities.parse_bonus_layer_label(node)

        bonus_link_node = bonus_link_nodes.get(utilities.get_bonus_link_id(bonus_name))
        if bonus_link_node is not None:
            node_style = {
                key: value for key, value in (
                    field.split(':') for field in bonus_link_node.get(Svg.STYLE).split(';')
                )
            }
            bonus_color = node_style[Svg.FILL].upper()
        else:
            bonus_color = Color.BLACK

        command = {
            'command': 'addBonus',
            'name': bonus_name,
            'armies': bonus_value,
            'color': bonus_color
        }
        return command

    commands = [get_add_bonus_command(node) for node in bonus_layer_nodes]
    return commands


def get_add_territory_to_bonus_commands(metadata_layer_node: etree.Element) -> list[types.Command]:
    bonus_layer_nodes = utilities.get_metadata_type_nodes(metadata_layer_node, Map.BONUSES_LAYER)

    def get_add_territory_to_bonus_command(
            territory_node: etree.Element, bonus_node: etree.Element
    ) -> types.Command:
        territory_id = utilities.get_territory_id_from_clone(territory_node)
        bonus_name, _ = utilities.parse_bonus_layer_label(bonus_node)

        command = {
            'command': 'addTerritoryToBonus',
            'id': territory_id,
            'bonusName': bonus_name
        }
        return command

    commands = [
        get_add_territory_to_bonus_command(territory_node, bonus_node)
        for bonus_node in bonus_layer_nodes
        for territory_node in bonus_node.xpath(f"./{Svg.CLONE}", namespaces=NAMESPACES)
    ]
    return commands


def get_add_distribution_mode_commands(metadata_layer_node: etree.Element) -> list[types.Command]:
    distribution_mode_layer_nodes = utilities.get_metadata_type_nodes(
        metadata_layer_node, Map.DISTRIBUTION_MODES_LAYER, is_recursive=False
    )

    def get_add_distribution_mode_command(distribution_mode_node: etree.Element) -> types.Command:
        distribution_mode_name = distribution_mode_node.get(utilities.get_uri(Inkscape.LABEL))
        # todo implement adding scenario distributions modes
        #  determine if scenario distribution mode
        #  get scenario names

        command = {
            'command': 'addDistributionMode',
            'name': distribution_mode_name,
        }
        return command

    commands = [get_add_distribution_mode_command(node) for node in distribution_mode_layer_nodes]
    return commands


def get_add_territory_to_distribution_commands(
        metadata_layer_node: etree.Element
) -> list[types.Command]:
    distribution_mode_layer_nodes = utilities.get_metadata_type_nodes(
        metadata_layer_node, Map.DISTRIBUTION_MODES_LAYER, is_recursive=False
    )

    def get_add_territory_to_distribution_command(
            territory_node: etree.Element, distribution_mode_node: etree.Element
    ) -> types.Command:
        territory_id = utilities.get_territory_id_from_clone(territory_node)
        distribution_mode_name = distribution_mode_node.get(utilities.get_uri(Inkscape.LABEL))
        # todo implement adding scenario distributions modes
        #  determine if scenario distribution mode
        #  get scenario names

        command = {
            'command': 'addTerritoryToDistribution',
            'id': territory_id,
            'distributionName': distribution_mode_name
        }
        return command

    commands = [
        get_add_territory_to_distribution_command(territory_node, distribution_mode_node)
        for distribution_mode_node in distribution_mode_layer_nodes
        for territory_node in distribution_mode_node.xpath(
            f"./{Svg.CLONE}", namespaces=NAMESPACES
        )
    ]
    return commands
