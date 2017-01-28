from pywink.groups.group import WinkGroup



# pylint: disable=redefined-variable-type,too-many-branches
def build_group(group_state_as_json, api_interface):

    return WinkGroup(group_state_as_json, api_interface)
