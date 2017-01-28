import colorsys
import time

from pywink.color import color_temperature_to_rgb, color_xy_brightness_to_rgb

class WinkGroup(object):

    def __init__(self, group_state_as_json, api_interface):
        """
        :type api_interface pywink.api.WinkApiInterface:
        :return:
        """
        self.api_interface = api_interface
        self.objectprefix = 'groups'
        self.json_state = group_state_as_json
        subscription = self.json_state.get('subscription')
        if subscription != {} and subscription is not None:
            pubnub = subscription.get('pubnub')
            self.pubnub_key = pubnub.get('subscribe_key')
            self.pubnub_channel = pubnub.get('channel')
        else:
            self.pubnub_key = None
            self.pubnub_channel = None

            
            
    def __str__(self):
        return "%s %s %s" % (self.name(), self.device_id(), self.state())

    def __repr__(self):
        return "<Wink group name:{name} id:{device} state:{state}>".format(name=self.name(),
                                                                            device=self.device_id(),
                                                                            state=self.state())

    def name(self):
        return self.json_state.get('name', "Unknown Name")

    def state(self):
        if not self.available:
            return False
        return self._reading_aggregation.get('powered').get('and', False)

    def device_id(self):
        return self.json_state.get('group_id', self.name())

    @property
    def _reading_aggregation(self):
        return self.json_state.get('reading_aggregation') or {}

    @property
    def available(self):
        return self._reading_aggregation.get('connection').get('or', False)
    
    @property
    def brightness(self):
        return self._reading_aggregation.get('brightness').get('average')

    @property
    def color_xy(self):
        """
        XY colour value: [float, float] or None
        :rtype: list float
        """
        color_x = self._reading_aggregation.get('color_x').get('average')
        color_y = self._reading_aggregation.get('color_y').get('average')

        if color_x is not None and color_y is not None:
            return [float(color_x), float(color_y)]

        return None

    @property
    def color_temperature_kelvin(self):
        """
        Color temperature, in degrees Kelvin.
        Eg: "Daylight" light bulbs are 4600K
        :rtype: int
        """
        return self._reading_aggregation.get('color_temperature').get('average')

    @property
    def color_hue(self):
        """
        Color hue from 0 to 1.0
        """
        return self._reading_aggregation.get('hue').get('average')

    @property
    def color_saturation(self):
        """
        Color saturation from 0 to 1.0
        :return:
        """
        return self._reading_aggregation.get('saturation').get('average')

    
    def set_arbitrary_state(self, state_var, state_val):
        desired_state = {state_var: state_val}

        response = self.api_interface.set_device_state(self, {
            "desired_state": desired_state
        })
        self._update_state_from_response(response)

    
    def set_state(self, state, brightness=None,
                  color_kelvin=None, color_xy=None,
                  color_hue_saturation=None, **kwargs):
        """
        :param state:   a boolean of true (on) or false ('off')
        :param brightness: a float from 0 to 1 to set the brightness of
         this bulb
        :param color_kelvin: an integer greater than 0 which is a color in
         degrees Kelvin
        :param color_xy: a pair of floats in a list which specify the desired
         CIE 1931 x,y color coordinates
        :param color_hue_saturation: a pair of floats in a list which specify
        the desired hue and saturation in that order.  Brightness can be
        supplied via the brightness param
        :return: nothing
        """
        desired_state = {"powered": state}

        color_state = self._format_color_data(color_hue_saturation, color_kelvin, color_xy)
        desired_state.update(color_state)

        brightness = brightness if brightness is not None \
            else self.json_state.get('last_reading', {}).get('desired_brightness', 1)
        desired_state.update({
            'brightness': brightness
        })

        response = self.api_interface.set_group_state(self, {
            "desired_state": desired_state
        })
        self._update_state_from_response(response)

        self._last_call = (time.time(), state)

    def _format_color_data(self, color_hue_saturation, color_kelvin, color_xy):
        if color_hue_saturation is None and color_kelvin is None and color_xy is None:
            return {}

        if self.supports_rgb():
            rgb = _get_color_as_rgb(color_hue_saturation, color_kelvin, color_xy)
            if rgb:
                return {
                    "color_model": "rgb",
                    "color_r": rgb[0],
                    "color_g": rgb[1],
                    "color_b": rgb[2]
                }
                # TODO: Find out if this is the correct format

        if color_hue_saturation is None and color_kelvin is not None and self.supports_temperature():
            return _format_temperature(color_kelvin)

        if self.supports_hue_saturation():
            hsv = _get_color_as_hue_saturation_brightness(color_hue_saturation, color_kelvin, color_xy)
            if hsv is not None:
                return _format_hue_saturation(hsv)

        if self.supports_xy_color():
            if color_xy is not None:
                return _format_xy(color_xy)

        return {}

    def _update_state_from_response(self, response_json):
        """
        :param response_json: the json obj returned from query
        :return:
        """
        _response_json = response_json.get('data')
        self.json_state = _response_json
        return True

    def update_state(self):
        """ Update state with latest info from Wink API. """
        response = self.api_interface.get_device_state(self)
        return self._update_state_from_response(response)

    def pubnub_update(self, json_response):
        self.json_state = json_response

        
def _format_temperature(kelvin):
    return {
        "color_model": "color_temperature",
        "color_temperature": kelvin,
    }


def _format_hue_saturation(hue_saturation):
    hsv_iter = iter(hue_saturation)
    return {
        "color_model": "hsb",
        "hue": next(hsv_iter),
        "saturation": next(hsv_iter),
    }


def _format_xy(xy):
    color_xy_iter = iter(xy)
    return {
        "color_model": "xy",
        "color_x": next(color_xy_iter),
        "color_y": next(color_xy_iter)
    }


def _get_color_as_rgb(hue_sat, kelvin, xy):
    if hue_sat is not None:
        h, s, v = colorsys.hsv_to_rgb(hue_sat[0], hue_sat[1], 1)
        return h, s, v
    if kelvin is not None:
        return color_temperature_to_rgb(kelvin)
    if xy is not None:
        return color_xy_brightness_to_rgb(xy[0], xy[1], 1)
    return None


def _get_color_as_hue_saturation_brightness(hue_sat, kelvin, xy):
    if hue_sat:
        color_hs_iter = iter(hue_sat)
        return (next(color_hs_iter), next(color_hs_iter), 1)
    rgb = _get_color_as_rgb(None, kelvin, xy)
    if not rgb:
        return None
    h, s, v = colorsys.rgb_to_hsv(rgb[0], rgb[1], rgb[2])
    return (h, s, v)