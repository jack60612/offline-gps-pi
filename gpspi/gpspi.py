import json
import logging
import time
from typing import Any, Optional

import gps

from gpspi.button_handler import ButtonHandler, LCDButton
from gpspi.LCD_handler import LCDHandler
from gpspi.mapping.coord_utils import (
    get_distance_feet,
    get_magnetic_bearing,
    get_nearest_city,
)
#from gpspi.mapping.WIP.path_finder import GPSPathFinder
from gpspi.types.GPS_data import GPSData
from gpspi.types.page import Page
from gpspi.types.saved_data import DictSavedData, SavedData, Waypoint

# GPIO Pins
KEY_UP_PIN: int = 6
KEY_DOWN_PIN: int = 19
KEY_LEFT_PIN: int = 5
KEY_RIGHT_PIN: int = 26
KEY_PRESS_PIN: int = 13
KEY1_PIN: int = 21
KEY2_PIN: int = 20
KEY3_PIN: int = 16


class GPSDisplay:
    def __init__(self, lcd_handler: LCDHandler, gpio_handler: ButtonHandler) -> None:
        self.lcd_handler: LCDHandler = lcd_handler
        self.gpio_handler: ButtonHandler = gpio_handler
        #self.gps_path_finder = GPSPathFinder("north-america-all-roads.graphml")

        # GPS setup
        logging.info("Connecting to GPSD")
        self.session = gps.gps(host="127.0.0.1", port="2947", reconnect=True)
        self.session.stream(gps.WATCH_ENABLE | gps.WATCH_NEWSTYLE)
        logging.info("Connected to GPSD")

        # GPS data
        self.gps_data: GPSData = GPSData()

        # Screen variables
        self.current_screen: Page = Page.TIME_AND_SATELLITES
        self.total_screens: int = 6
        self.saved_data: SavedData = self.load_data()
        self.cur_waypoint_index: int = 0

        # Configure button callbacks
        self.gpio_handler.configure_callbacks(self.button_callback)
        logging.info("Button callbacks configured")

    # Util Functions

    def load_data(self) -> SavedData:
        try:
            with open("destination.json", "r") as f:
                return SavedData.from_dict(DictSavedData(**json.load(f)))  # type: ignore[typeddict-item]
        except FileNotFoundError:
            return SavedData()

    def save_data(self) -> None:
        with open("destination.json", "w") as f:
            json.dump(self.saved_data.to_dict(), f)

    def button_callback(self, button: LCDButton) -> None:
        if button == LCDButton.UP:
            self.current_screen = Page((self.current_screen.value - 1) % self.total_screens)
        elif button == LCDButton.DOWN:
            self.current_screen = Page((self.current_screen.value + 1) % self.total_screens)
        else:
            self.update_display(button)

    # Parse GPS Data

    def update_gps_data(self) -> None:
        try:
            report = dict(self.session.next())
            if report["class"] == "TPV":  # Time, Position, Velocity report
                # parse data
                latitude: Optional[float] = report.get("lat")
                longitude: Optional[float] = report.get("lon")
                altitude: Optional[float] = report.get("alt")
                speed: Optional[float] = report.get("speed")
                time: Optional[str] = report.get("time")
                true_heading: Optional[float] = report.get("track")
                mag_heading: Optional[float] = report.get("magtrack")

                self.gps_data.update_position_data(
                    latitude=latitude,
                    longitude=longitude,
                    altitude=altitude,
                    speed=speed,
                    time=time,
                    true_heading=true_heading,
                    mag_heading=mag_heading,
                )

            if report["class"] == "SKY":  # Satellite information
                time = report.get("time")
                satellites: list[dict[str, Any]] = list(report.get("satellites", [{}]))
                self.gps_data.update_satellite_data(time=time, satellites=satellites)

        except (TypeError, KeyError, StopIteration):
            return None

    def get_nearest_city(self) -> Waypoint:
        """Return the coordinates of the nearest town."""
        # Now Implemented YAY
        return get_nearest_city(self.gps_data.as_waypoint()).as_waypoint()

    def navigate_to_city(self) -> list[Waypoint]:
        """start navigation to the nearest city"""
        # Now Implemented YAY
        if not self.gps_data.in_sync:
            return []
        nearest_city: Waypoint = get_nearest_city(self.gps_data.as_waypoint()).as_waypoint()
        # generate route to the nearest city, this is disabled to save processing power.
        #return self.gps_path_finder.navigate_to_waypoint(self.gps_data, nearest_city)
        return [nearest_city]

    def get_nearest_road(self) -> Waypoint:
        """Navigate to the nearest road"""
        # Now Implemented YAY
        if not self.gps_data.in_sync:
            return Waypoint(0.0, 0.0, 0.0)
        #return self.gps_path_finder.navigate_to_nearest_road(self.gps_data)
        #this code should not be called
        return self.get_nearest_city()

    def compass_heading(self, destination) -> float:
        """Return the compass heading from the current location to the destination, ex 60 degrees east."""
        # Implemented this
        return get_magnetic_bearing(self.gps_data.as_waypoint(), destination)

    def calculate_distance(self, destination) -> float:
        """Return the distance from the current location to the destination in feet."""
        # Implemented this
        return get_distance_feet(self.gps_data.as_waypoint(), destination)

    # GUI Functions

    def update_display(self, button: Optional[LCDButton] = None) -> None:
        if self.gps_data.time is None:
            self.lcd_handler.display_text(Page.TIME_AND_SATELLITES, ["No GPS data"])
            return
        if self.current_screen == Page.TIME_AND_SATELLITES:
            self.display_time_and_satellites(button)
        elif self.current_screen == Page.GPS_COORDINATES:
            self.display_gps_coordinates(button)
        elif self.current_screen == Page.SELECT_DESTINATION:
            self.display_select_destination(button)
        elif self.current_screen == Page.SELECT_WAYPOINTS:
            self.display_select_waypoints(button)
        elif self.current_screen == Page.COMPASS_HEADING_AND_SPEED:
            self.display_compass_heading_and_speed(button)
        elif self.current_screen == Page.COORDINATES_AND_DISTANCE:
            self.display_coordinates_and_distance(button)

    def display_time_and_satellites(self, button: Optional[LCDButton] = None) -> None:
        assert self.gps_data.time is not None
        if button == LCDButton.KEY1:
            # increase brightness
            self.lcd_handler.raise_brightness()
        elif button == LCDButton.KEY2:
            # decrease brightness
            self.lcd_handler.lower_brightness()
        elif button == LCDButton.KEY3:
            # reset brightness
            self.lcd_handler.reset_brightness()
        self.lcd_handler.display_text(
            Page.TIME_AND_SATELLITES,
            [
                time.strftime("%Y-%m-%d %H:%M:%S", self.gps_data.time.timetuple()),
                f"Sats connected: {self.gps_data.num_satellites}",
                f"Synced: {'Yes' if self.gps_data.in_sync else 'No'}",
            ],
            buttons=["B+", "B-", "RB"],
        )

    def display_gps_coordinates(self, button: Optional[LCDButton] = None) -> None:
        color = (0, 255, 0) if self.gps_data.in_sync else (255, 0, 0)
        self.lcd_handler.display_text(
            Page.GPS_COORDINATES,
            ["Current Cords", "Green = recent", f"Lat: {self.gps_data.latitude}", f"Lon: {self.gps_data.longitude}"],
            colors=[color, color],
            buttons=["N/A", "N/A", "N/A"],
        )

    def display_select_destination(self, button: Optional[LCDButton] = None) -> None:
        buttons = ["NR", "NC", "WP"]
        if button == LCDButton.KEY1:
            # Set the destination to the nearest road
            #self.saved_data.destination = self.get_nearest_road()
            self.save_data()
        elif button == LCDButton.KEY2:
            # navigate to the nearest city
            nav_output = self.navigate_to_city()
            self.saved_data.destination = nav_output[0]
            self.saved_data.waypoints += nav_output[1:]
            self.save_data()
        elif button == LCDButton.KEY3:
            # Select the destination from a list of waypoints
            if self.saved_data.waypoints:
                self.saved_data.destination = self.saved_data.waypoints[self.cur_waypoint_index]
                self.save_data()
            else:
                self.lcd_handler.display_text(Page.SELECT_DESTINATION, ["No waypoints saved"], buttons=buttons)
                return

        if self.saved_data.destination:
            self.lcd_handler.display_text(
                Page.SELECT_DESTINATION,
                [
                    f"Destination set to:",
                    f"Lat: {self.saved_data.destination.latitude}",
                    f"Lon: {self.saved_data.destination.longitude}",
                    f"Name: {self.saved_data.destination.name}",
                ],
                buttons=buttons,
            )
        else:
            self.lcd_handler.display_text(Page.SELECT_DESTINATION, ["No destination set"], buttons=buttons)

    def display_select_waypoints(self, button: Optional[LCDButton] = None) -> None:
        buttons = ["DEL", "PREV", "NEXT"]
        if button == LCDButton.SELECT:
            if self.gps_data.in_sync:
                assert self.gps_data.latitude is not None
                assert self.gps_data.longitude is not None
                assert self.gps_data.altitude is not None
                new_waypoint = Waypoint(
                    latitude=float(self.gps_data.latitude),
                    longitude=float(self.gps_data.longitude),
                    altitude=float(self.gps_data.altitude),
                )
                self.saved_data.waypoints.append(new_waypoint)
                self.save_data()
                self.lcd_handler.display_text(Page.SELECT_WAYPOINTS, ["Waypoint saved!"], buttons=buttons)
        elif len(self.saved_data.waypoints) == 0:  # all other button presses are invalid if there are no waypoints
            self.lcd_handler.display_text(Page.SELECT_WAYPOINTS, ["No waypoints saved"], buttons=buttons)
            return
        elif button == LCDButton.KEY1:
            # Delete the current waypoint (confirmation can be added if needed)
            del self.saved_data.waypoints[self.cur_waypoint_index]
            self.save_data()
            self.cur_waypoint_index = max(0, self.cur_waypoint_index - 1)
            self.lcd_handler.display_text(Page.SELECT_WAYPOINTS, ["Waypoint deleted!"], buttons=buttons)
            return
        elif button == LCDButton.KEY2:
            # Move to the previous waypoint
            self.cur_waypoint_index = (self.cur_waypoint_index - 1) % len(self.saved_data.waypoints)
        elif button == LCDButton.KEY3:
            # Move to the next waypoint
            self.cur_waypoint_index = (self.cur_waypoint_index + 1) % len(self.saved_data.waypoints)

        waypoint = self.saved_data.waypoints[self.cur_waypoint_index]
        self.lcd_handler.display_text(
            Page.SELECT_WAYPOINTS,
            [
                f"Waypoint {self.cur_waypoint_index + 1}/{len(self.saved_data.waypoints)}",
                f"Lat: {waypoint.latitude}",
                f"Lon: {waypoint.longitude}",
                f"Alt: {waypoint.altitude}",
                f"Name: {waypoint.name}",
            ],
            buttons=buttons,
        )

    def display_compass_heading_and_speed(self, button) -> None:
        assert self.gps_data.mag_heading is not None
        buttons = ["N/A", "N/A", "N/A"]
        if self.saved_data.destination:
            self.lcd_handler.display_text(
                Page.COMPASS_HEADING_AND_SPEED,
                [
                    f"Cur Speed:{round(self.gps_data.speed * gps.MPS_TO_MPH,2)}MPH",
                    f"CurH:{round(self.gps_data.mag_heading,2)}",
                    f"TgtH:{self.compass_heading(self.saved_data.destination)}",
                    "Headings are in",
                    "Magnetic Degrees",
                ],
                buttons=buttons,
            )
        else:
            self.lcd_handler.display_text(Page.COMPASS_HEADING_AND_SPEED, ["No destination set"], buttons=buttons)

    def display_coordinates_and_distance(self, button) -> None:
        assert self.gps_data.speed is not None
        buttons = ["N/A", "N/A", "N/A"]
        if self.saved_data.destination:
            self.lcd_handler.display_text(
                Page.COORDINATES_AND_DISTANCE,
                [
                    f"LAT: {self.gps_data.latitude}",
                    f"Lng: {self.gps_data.longitude}",
                    "Current Cords^",
                    f"LAT: {self.saved_data.destination.latitude}",
                    f"Lng: {self.saved_data.destination.longitude}",
                    "Target Cords^",
                    "Dist to Tgt:",
                    f"{round(self.calculate_distance(self.saved_data.destination) / 5280,2)} Mi",
                ],
                buttons=buttons,
            )
        else:
            self.lcd_handler.display_text(Page.COORDINATES_AND_DISTANCE, ["No destination set"], buttons=buttons)

    def main_loop(self) -> None:
        try:
            while True:
                self.update_gps_data()
                self.update_display()
                time.sleep(1)
        except KeyboardInterrupt:
            pass  # gpiozero does not require explicit cleanup


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    # Create instances of the handlers
    lcd_handler = LCDHandler()
    gpio_handler = ButtonHandler(
        up_pin=KEY_UP_PIN,
        down_pin=KEY_DOWN_PIN,
        left_pin=KEY_LEFT_PIN,
        right_pin=KEY_RIGHT_PIN,
        select_pin=KEY_PRESS_PIN,
        key1_pin=KEY1_PIN,
        key2_pin=KEY2_PIN,
        key3_pin=KEY3_PIN,
    )
    gps_display = GPSDisplay(lcd_handler, gpio_handler)
    # start program run loop
    logging.info("Starting Main loop")
    gps_display.main_loop()


if __name__ == "__main__":
    main()
