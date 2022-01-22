import re
import xml.etree.ElementTree as ET

from warzone_map_utils.constants import svg


def get_layers(map_path: str) -> dict[str, ET.Element]:
    map_xml = ET.parse(map_path)
    root = map_xml.getroot()
    layers = {
        node.get(get_uri(svg.LABEL_ATTRIBUTE)): node
        for node in root.findall(f"./*[@{svg.LABEL_ATTRIBUTE}]", svg.NAMESPACES)
    }
    return layers


def get_metadata_type_layers(
        metadata_layer_node: ET.Element, metadata_type: str, is_recursive: bool = True
) -> list[ET.Element]:
    slash = '//' if is_recursive else '/'
    bonus_layer_nodes = (
        metadata_layer_node.findall(
            f"./{svg.GROUP_TAG}[@{svg.LABEL_ATTRIBUTE}='{metadata_type}']"
            f"{slash}{svg.GROUP_TAG}[@{svg.LABEL_ATTRIBUTE}]", svg.NAMESPACES)
    )
    return bonus_layer_nodes


def parse_bonus_layer_label(node: ET.Element) -> tuple[str, int]:
    bonus_name, bonus_value = node.get(get_uri(svg.LABEL_ATTRIBUTE)).split(': ')
    return bonus_name, int(bonus_value)


def get_uri(key: str) -> str:
    if ':' in key:
        namespace, key = key.split(':')
        key = f'{{{svg.NAMESPACES[namespace]}}}{key}'
    return key


def get_bonus_link_id(bonus_name: str) -> str:
    return svg.BONUS_LINK_IDENTIFIER + re.sub(r'[^a-zA-Z0-9]+', '', bonus_name)
