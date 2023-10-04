# generic_agency/agency.py
# Part of timetable_kit
# Copyright 2022, 2023 Nathanael Nerode.  Licensed under GNU Affero GPL v.3 or later.
"""
timetable_kit.generic_agency.agency module

This holds a class for "Agency" intended to be used as a singleton.
It has an interface; Amtrak and others need to provide the same interface.
This should be made easier by class inheritance.
"""
from __future__ import annotations

from timetable_kit.feed_enhanced import FeedEnhanced
from timetable_kit.debug import debug_print

# For text twiddling
from timetable_kit.text_assembly import href_wrap, and_clause, or_clause


# Intended to be used both directly and by subclasses
class Agency:
    """Agency-specific code for interpreting specs and GTFS feeds for a generic agency"""

    # The following class variables are overridden in subclasses.
    # This is a list of the agency names for the disclaimers and credit
    # (There is typically one, but sometimes more.)
    _agency_names = []
    # This is a list of the agency (ticketing/website) websites, parellel to the list of agency names.
    # These should omit the https:// and be formatted for print.
    _agency_websites = []
    # This is a list of the agency GTFS URLs to publish, parallel to the list of agency names
    _agency_published_gtfs_urls = []
    # This is the dict of *all* the possible connecting services
    # Generally initialized from a static file in the module
    _connecting_services_dict = []

    def __init__(
        self: Agency,
    ) -> None:
        # This is the GTFS feed.
        # It is filled in by init_from_feed, due to complex initialization ordering requirements.
        self._feed = None
        # These are built from the GTFS feed.
        # They start "None" and are filled in by initialization code on first use (memoized)
        self._stop_code_to_stop_id_dict = None
        self._stop_id_to_stop_code_dict = None
        self._stop_code_to_stop_name_dict = None
        self._accessible_platform_dict = None
        self._inaccessible_platform_dict = None
        # Used for the generic get_route_id (but not by Amtrak or VIA)
        self._route_name_dict = None

    def patch_feed(self, feed: FeedEnhanced) -> FeedEnhanced:
        """
        Apply patches suitable for this agency to a feed;
        return a patched feed.

        For a generic agency, this does nothing.

        Does not alter the data in the agency object.
        Do this before init_from_feed.
        """
        return feed

    def patch_feed_wheelchair_access_only(self, feed: FeedEnhanced) -> FeedEnhanced:
        """
        Apply only the patches to add wheelchair boarding information for this agency;
        return a patched feed.

        For a generic agency, this does nothing.

        Does not alter the data in the agency object.
        Do this before init_from_feed.
        """
        return feed

    def init_from_feed(self, feed: FeedEnhanced):
        """
        Initalize this object with an enhanced GTFS feed.
        Used for translating stop_code to and from stop_id.
        Also used for wheelchair boarding info.
        We don't want to do this at object creation for multiple reasons.
        1. We need to call agency routines on the feed before using it.
        2. We may not need to use this agency object at all, but it may need to be created in initialization.
        3. We may not need to initialize these tables in subclasses.
        4. This is expensive in both memory usage and time.

        This must be run before several of the other methods on this are usable.
        """
        if self._feed is not None:
            debug_print(
                1,
                "Warning: resetting feed on agency when it has already been set once: this is discouraged",
            )
        self._feed = feed

    def always_check_disclaimer(self, doing_html: bool = True):
        """Returns a string with a disclaimer about always checking agency websites for times"""
        # Note that this doesn't do the boldfacing, that's done in the Jinja template.
        if doing_html:
            website_hrefs = [
                href_wrap(website, "https://" + website)
                for website in self._agency_websites
            ]
        else:
            website_hrefs = self._agency_websites
        if not website_hrefs:
            # No actual agency website, so say something generic
            website_hrefs = ["agency websites"]
        return " ".join(
            [
                "Always check",
                *or_clause(website_hrefs),
                "for precise times for your exact date of travel.",
            ]
        )

    def unofficial_disclaimer(self, doing_html: bool = True):
        """Returns a string for a disclaimer about this not being an official product"""
        # Agency names in GTFS are a mess and basically unusable.
        # So without a specific agency name, we have to say something very generic.
        return " ".join(
            [
                "This timetable is not an official",
                *or_clause(self._agency_names),
                "product.",
            ]
        )

    def gtfs_data_link(self, doing_html: bool = True):
        """Returns the string "GTFS data", possibly with an appropriate link."""
        if doing_html and len(self._agency_published_gtfs_urls) == 1:
            return href_wrap(
                "GTFS data", self._agency_published_gtfs_urls[0], doing_html
            )
        else:
            # With 0 or 2+ GTFS urls or when not doing HTML, don't make a link.
            return "GTFS data"

    def by_agency_with_gtfs_link(self, doing_html: bool = True):
        """Returns a string like "by Amtrak and by VIA Rail", with the "by Amtrak" being a link to the Amtrak GTFS and similarly for the "by VIA Rail"."""
        # Note that href_wrap has different behavior if doing_html is false
        wrapped_by_names = [
            href_wrap("by " + name, url, doing_html)
            for name, url in zip(self._agency_names, self._agency_published_gtfs_urls)
        ]
        joined_clause = " ".join(and_clause(wrapped_by_names))
        if joined_clause:
            joined_clause += ", "
        # The way this is used in the Jinja template, it's preceded by ", ".
        # If blank, leave blank.
        # If not blank, finish off with ", ".
        # We can't move this all into code because we need to be able to refer to
        # key_on_right to do line breaking in the Jinja template.
        return joined_clause

    def _prepare_dicts(self):
        """
        Prepare the dicts for:
        _stop_code_to_stop_id
        _stop_id_to_stop_code
        _stop_code_to_stop_name
        _accessible_platform_dict
        _inaccessible_platform_dict

        These depend on a previously established feed (set by init_from_feed)
        """
        debug_print(1, "Preparing stop_code / stop_id dicts")
        if self._feed is None:
            raise RuntimeError(
                "in Agency class: init_from_feed must be run before preparing dicts"
            )

        # Create the conversion dicts from the feed
        stop_ids = self._feed.stops["stop_id"].to_list()
        stop_names = self._feed.stops["stop_name"].to_list()

        if "stop_code" not in self._feed.stops.columns:
            # Amtrak doesn't have stop_code, so don't make the translation dicts in this case.
            # Also won't need the stop name dict, as Amtrak has its own way of finding names.
            # In this case, copy the stop_ids into the stop_codes for the wheelchair access dicts later.
            stop_codes = stop_ids
            pass
        else:
            # stop_code exists (as in VIA and Greyhound); make the back-and-forth dicts
            stop_codes = self._feed.stops["stop_code"].to_list()
            self._stop_code_to_stop_id_dict = dict(zip(stop_codes, stop_ids))
            self._stop_id_to_stop_code_dict = dict(zip(stop_ids, stop_codes))

        # We make the stop name dict even if there wasn't a stop_codes column.
        # A generic agency may need it, although Amtrak does not use it.
        self._stop_code_to_stop_name_dict = dict(zip(stop_codes, stop_names))

        # OK.  Now wheelchair boarding.

        # First check for parent_station.
        # If this exists we need to do special stuff, which we have not implemented.
        # Amtrak does not even have the column; in which case, move right along.
        if "parent_station" in self._feed.stops.columns:
            # VIA Rail does not have stops with parents, but it does have the column.
            # So continue to the normal case if the column is empty.
            # FIXME Warning! This depends on retaining the NaN blanks in the GTFS data.
            stops_with_parents = self._feed.stops.dropna(subset=["parent_station"])
            if not stops_with_parents.empty:
                # The column really exists.  This is a problem.
                print(
                    "Warning: Stops with parents found -- this invalidates wheelchair access detection."
                )
                print(stops_with_parents)
                # Default to no wheelchair access information
                self._accessible_platform_dict = {}
                self._inaccessible_platform_dict = {}
                # And bail out early
                return

        if "wheelchair_boarding" not in self._feed.stops.columns:
            # If the wheelchair_boarding column does not exist... bail
            debug_print(1, "Warning: wheelchair_boarding column not found in GTFS data")
            # Default to no information
            self._accessible_platform_dict = {}
            self._inaccessible_platform_dict = {}
            return

        # OK, the normal case for wheelchair boarding.
        # We interpret wheelchair_boarding with strict accuracy.
        # 0 or blank == unknown
        # 1 == accessible, for at least some services
        # 2 == inaccessible
        # gtfs_type_cleanup.py will correctly turn blanks into 0s for us, so don't need to worry about blanks.
        wheelchair_boarding_list = self._feed.stops["wheelchair_boarding"].to_list()
        can_board_list = [bool(x == 1) for x in wheelchair_boarding_list]
        cannot_board_list = [bool(x == 2) for x in wheelchair_boarding_list]
        self._accessible_platform_dict = dict(zip(stop_codes, can_board_list))
        self._inaccessible_platform_dict = dict(zip(stop_codes, cannot_board_list))
        return

    def stop_code_to_stop_id(self, stop_code: str) -> str:
        """Given a stop_code, return a stop_id"""
        # Memoized.  None is a sentinel value meaning uninitalized
        if self._stop_code_to_stop_id_dict is None:
            self._prepare_dicts()
        return self._stop_code_to_stop_id_dict[stop_code]

    def stop_id_to_stop_code(self, stop_id: str) -> str:
        """Given a stop_id, return a stop_code"""
        # Memoized.  None is a sentinel value meaning uninitalized
        if self._stop_id_to_stop_code_dict is None:
            self._prepare_dicts()
        return self._stop_id_to_stop_code_dict[stop_id]

    def stop_code_to_stop_name(self, stop_code: str) -> str:
        """Given a stop_code, return a stop_name -- raw"""
        # Memoized.  None is a sentinel value meaning uninitalized
        if self._stop_code_to_stop_name_dict is None:
            self._prepare_dicts()
        return self._stop_code_to_stop_name_dict[stop_code]

    def station_has_inaccessible_platform(self, station_code: str) -> bool:
        """
        Does the station explicitly have an inaccessible platform?

        This excludes stations which don't say either way.
        """
        # Memoized.  None is a sentinel value meaning uninitalized
        if self._inaccessible_platform_dict is None:
            self._prepare_dicts()
        return self._inaccessible_platform_dict[station_code]

    def station_has_accessible_platform(self, station_code: str) -> bool:
        """
        Does this station explicitly have an accessible platform?

        This excludes stations which don't say either way.
        """
        # Memoized.  None is a sentinel value meaning uninitalized
        if self._accessible_platform_dict is None:
            self._prepare_dicts()
        return self._accessible_platform_dict[station_code]

    def station_has_checked_baggage(self, station_code: str) -> bool:
        """
        Does this station have checked baggage service?
        """
        # For a generic agency, no, it doesn't.
        return False

    def train_has_checked_baggage(self, tsn: str) -> bool:
        """
        Does this train have checked baggage service?
        """
        # For a generic agency, no, it doesn't.
        return False

    def is_sleeper_train(self, tsn: str) -> bool:
        """
        Does this train have sleeper cars?
        """
        # For a generic agency, no, it doesn't.
        return False

    def is_high_speed_train(self, tsn: str) -> bool:
        """
        Should this train be marked as high-speed in the timetable?
        """
        # For a generic agency, no.
        return False

    def is_connecting_service(self, tsn: str) -> bool:
        """
        Should this be marked as a connecting service in the timetable?
        """
        # This should be implemented by checking the agency file,
        # and seeing which trains are run by different agencies.
        # That's complicated.
        # For the default, we return false.
        return False

    def connecting_bus_key_sentence(self, doing_html=True) -> str:
        """
        Sentence to put in the symbol key for connecting bus services
        """
        return "Connecting Bus Service"

    def add_via_disclaimer(self, doing_html=True) -> bool:
        """
        Should we add the VIA disclaimer?

        This is boolean because the disclaimer is multiline and needs Jinja macros.
        """
        # There is probably a better way to do this.
        return False

    def agency_css_class(self) -> str:
        """
        Name of a CSS class for agency-specific styling
        """
        # Default is blank.  This generates class="".
        return ""

    def get_all_connecting_services(self, station_list: list[str]) -> list[str]:
        """
        Given a list of station codes, return a list of services which connect
        (with no duplicates)
        """
        all_services = []
        for station in station_list:
            new_services = self._connecting_services_dict.get(station, [])
            for service in new_services:
                if service not in all_services:
                    all_services.append(service)
        return all_services

    def _prepare_route_name_dict(self, feed: FeedEnhanced):
        """
        Prepare and cache the route name dict.

        Uses the route_long_name from GTFS.

        Requires unique route_id values (no duplicates)
        """
        self._route_name_dict = dict(
            zip(feed.routes["route_id"], feed.routes["route_long_name"])
        )

    def get_route_name(self, feed: FeedEnhanced, route_id: str) -> str:
        """
        Given feed and a route_id, produce a suitable name for a column subheading.
        This is the generic implementation using GTFS data.
        """
        # Memoized.  None is a sentinel value meaning uninitalized
        # This isn't used by subpackages, which won't even load this data.
        if self._route_name_dict is None:
            self._prepare_route_name_dict(feed)
        return self._route_name_dict[route_id]

    def get_station_name_pretty(
        self, station_code: str, doing_multiline_text=False, doing_html=True
    ) -> str:
        """
        Pretty-print a station name.

        The default implementation just prints the station name from GTFS.
        """
        # First, get the raw station name: Memoized
        stop_name_raw = self.stop_code_to_stop_name(station_code)
        return stop_name_raw


# Establish the singleton
_singleton = Agency()


def get_singleton():
    """Get singleton for generic agency"""
    global _singleton
    return _singleton
