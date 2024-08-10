from __future__ import annotations

import json
from functools import partial
from typing import Any, Final, Protocol

import tomlkit

from timetable_kit.errors import GTFSError
from timetable_kit.load_resources import get_style_toml
from timetable_kit.time import explode_timestr

EXPECTED_KEYS: Final[set[str]] = {"time", "day", "css"}


class StyleHandler:
    class InvalidStyleError(ValueError):
        pass

    @staticmethod
    def _read_toml(filename: str) -> dict[str, Any]:
        return tomlkit.parse(get_style_toml(filename))

    def __init__(self, style_name: str):
        # Load default style values first, then overwrite what changes in the specified style
        config = self._read_toml("default")
        config.update(self._read_toml(style_name))

        match config:  # now read that
            # I love using this to destructure things it's so convenient
            case {
                "time": {
                    "24h": using_24h,
                    "am": {"style": am_style, "string": am_string},
                    "pm": {"style": pm_style, "string": pm_string},
                },
                "day": {"format": day_format, "week_start": week_start},
                "css": {"tag": special_css_tag},
            }:

                self._using_24h: bool = using_24h
                self._am_style: str = am_style
                self._pm_style: str = pm_style
                self._am_string: str = am_string
                self._pm_string: str = pm_string
                self._day_format: dict[str, str] = (
                    {"all": day_format, "some": day_format}
                    if type(day_format) is str
                    else day_format
                )
                self._week_start: str = week_start
                self._special_css_tag: str = special_css_tag

            case _:
                err = "Style config not valid. "
                unexpected_keys = set(config.keys()) - EXPECTED_KEYS
                missing_keys = EXPECTED_KEYS - set(config.keys())

                if unexpected_keys:
                    err += "\nUnexpected value(s): "
                    err += ", ".join(unexpected_keys)

                if missing_keys:
                    err += "\nMissing value(s): "
                    err += ", ".join(missing_keys)

                err += "\nFull config: \n\n"
                err += json.dumps(config, indent=2)
                err += "\n"

                raise StyleHandler.InvalidStyleError(err)

    def format_time(
        self,
        gtfs_timestr: str | int,
        *,
        tz_difference: int = 0,
        html: bool = False,
        spans: bool = False,
    ) -> str:
        """
        Given a GTFS time, make a formatted time string.
        """
        time_stuff = explode_timestr(gtfs_timestr, tz_difference)

        # these are agnostic to whether you're using 12h or 24h time
        # meridiem is just the m in am/pm - I couldn't think of another variable name lol
        if time_stuff.pm:
            meridiem_style = self._pm_style
            meridiem_string = self._pm_string
        else:
            meridiem_style = self._am_style
            meridiem_string = self._am_string

        string = ""

        if self._using_24h:
            string += f"{time_stuff.hour24: >2}:{time_stuff.min:02}"
            assert len(string) == 5

        else:
            hour = time_stuff.hour if time_stuff.hour != 0 else 12
            string += f"{hour: >2}:{time_stuff.min:0>2}"
            assert len(string) == 5
            string += meridiem_string

        if html:
            if spans:

                def span(class_name: str = "") -> str:
                    return f'<span class="{class_name}">' if class_name else "</span>"

                if self._using_24h:
                    string = (
                        f"{span('box-digit')}{string[0]}{span()}"
                        f"{span('box-digit')}{string[1]}{span()}"
                        f"{span('box-colon')}{string[2]}{span()}"
                        f"{span('box-digit')}{string[3]}{span()}"
                        f"{span('box-digit')}{string[4]}{span()}"
                        f"{string[5:]}"  # will correctly add nothing if there are only 5 characters
                    )
                else:
                    string = (
                        f"{span('box-1')}{string[0]}{span()}"
                        f"{span('box-digit')}{string[1]}{span()}"
                        f"{span('box-colon')}{string[2]}{span()}"
                        f"{span('box-digit')}{string[3]}{span()}"
                        f"{span('box-digit')}{string[4]}{span()}"
                        f"{span('box-ap')}{string[5:]}{span()}"
                    )

            # html style tags like b, i, strong, etc separated by spaces
            for html_style in meridiem_style.split():
                string = f"<{html_style}>{string}</{html_style}>"

        return string

    _DAYS_IN_WEEK = [
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
    ]

    _DAY_INITIAL_EN = "MTWTFSS"
    _DAY_INITIAL_FR = "LMMJVSD"

    def _daystring_numbers(
        self, days_of_service: dict[str, int], *, html: bool = False, **_
    ):
        """
        Presents days of service in numeric form, starting from the day of choice.
        Out of service days are given their own class for custom styling later,
        such as crossing or greying out digits. Information on what day "1" is
        should be provided elsewhere on the timetable.

        For CSV-only presentation, out of service day digits are presented as an underscore.
        """
        week_start = self._DAYS_IN_WEEK.index(self._week_start)
        days_in_week = self._DAYS_IN_WEEK[week_start:] + self._DAYS_IN_WEEK[:week_start]

        string = ""
        for num, day in enumerate(days_in_week, start=1):
            if html:
                html_class = "running" if days_of_service[day] else "absent"
                string += f'<span class="number_day_{html_class}">{num}</span>'
            else:
                string += str(num) if days_of_service[day] else "_"

        return string

    def _daystring_letters(
        self,
        days_of_service: dict[str, int],
        *,
        html: bool = False,
        locale_initials: str,
        **_,
    ) -> str:
        """
        Presents days of service in the form of days' initials, starting from the day of choice.
        Out of service days are given their own class for custom styling later,
        such as crossing or greying out letters. This function can be given any seven-character
        string for locale_initials to be adapted to whatever language one desires.

        For CSV-only presentation, out of service day initials are presented as an underscore.
        """
        week_start = self._DAYS_IN_WEEK.index(self._week_start)
        days_in_week = self._DAYS_IN_WEEK[week_start:] + self._DAYS_IN_WEEK[:week_start]
        initials_in_week = locale_initials[week_start:] + locale_initials[:week_start]

        string = ""
        for let, day in zip(initials_in_week, days_in_week):
            if html:
                html_class = "running" if days_of_service[day] else "absent"
                string += f'<span class="letter_day_{html_class}">{let}</span>'
            else:
                string += let if days_of_service[day] else "_"

        return string

    _daystring_letters_en = partial(_daystring_letters, locale_initials=_DAY_INITIAL_EN)
    _daystring_letters_fr = partial(_daystring_letters, locale_initials=_DAY_INITIAL_FR)

    def _daystring_letters_ca_bilingual(
        self, days_of_service: dict[str, int], *, html: bool = False, **_
    ) -> str:
        """
        Uses the English and French day initials together for extra maple syrup.
        """
        return (
            self._daystring_letters_en(days_of_service, html=html)
            + ("<br>" if html else "\n")
            + self._daystring_letters_fr(days_of_service, html=html)
        )

    # This dictionary of special cases for daystring is easier to read
    # than hand-writing all the if-thens.
    # The special cases are ones which don't need the "rotation trick"
    # (or, in the case of SaSu, where we want to *avoid* it)
    _daystring_special_cases: Final[dict[tuple[...], str]] = {
        (1, 1, 1, 1, 1, 1, 1): "Daily",
        # Missing only one day
        (1, 1, 1, 1, 1, 1, 0): "Mo-Sa",
        (0, 1, 1, 1, 1, 1, 1): "Tu-Su",
        (1, 0, 1, 1, 1, 1, 1): "We-Mo",
        (1, 1, 0, 1, 1, 1, 1): "Th-Tu",
        (1, 1, 1, 0, 1, 1, 1): "Fr-We",
        (1, 1, 1, 1, 0, 1, 1): "Sa-Th",
        (1, 1, 1, 1, 1, 0, 1): "Su-Fr",
        # Missing two consecutive days (including Mo-Fr)
        (1, 1, 1, 1, 1, 0, 0): "Mo-Fr",
        (0, 1, 1, 1, 1, 1, 0): "Tu-Sa",
        (0, 0, 1, 1, 1, 1, 1): "We-Su",
        (1, 0, 0, 1, 1, 1, 1): "Th-Mo",
        (1, 1, 0, 0, 1, 1, 1): "Fr-Tu",
        (1, 1, 1, 0, 0, 1, 1): "Sa-We",
        (1, 1, 1, 1, 0, 0, 1): "Su-Th",
        # Missing three consecutive days
        (1, 1, 1, 1, 0, 0, 0): "Mo-Th",
        (0, 1, 1, 1, 1, 0, 0): "Tu-Fr",
        (0, 0, 1, 1, 1, 1, 0): "We-Sa",
        (0, 0, 0, 1, 1, 1, 1): "Th-Su",
        (1, 0, 0, 0, 1, 1, 1): "Fr-Mo",
        (1, 1, 0, 0, 0, 1, 1): "Sa-Tu",
        (1, 1, 1, 0, 0, 0, 1): "Su-We",
        # Missing four consecutive days
        (1, 1, 1, 0, 0, 0, 0): "Mo-We",
        (0, 1, 1, 1, 0, 0, 0): "Tu-Th",
        (0, 0, 1, 1, 1, 0, 0): "We-Fr",
        (0, 0, 0, 1, 1, 1, 0): "Th-Sa",
        (0, 0, 0, 0, 1, 1, 1): "Fr-Su",
        (1, 0, 0, 0, 0, 1, 1): "Sa-Mo",
        (1, 1, 0, 0, 0, 0, 1): "Su-Tu",
        # Only running two consecutive days
        # (including SaSu, which we need to avoid SuSa in -1 offset cases)
        (1, 1, 0, 0, 0, 0, 0): "MoTu",
        (0, 1, 1, 0, 0, 0, 0): "TuWe",
        (0, 0, 1, 1, 0, 0, 0): "WeTh",
        (0, 0, 0, 1, 1, 0, 0): "ThFr",
        (0, 0, 0, 0, 1, 1, 0): "FrSa",
        (0, 0, 0, 0, 0, 1, 1): "SaSu",
        (1, 0, 0, 0, 0, 0, 1): "SuMo",
        # Only running on one day a week
        (1, 0, 0, 0, 0, 0, 0): "Mo",
        (0, 1, 0, 0, 0, 0, 0): "Tu",
        (0, 0, 1, 0, 0, 0, 0): "We",
        (0, 0, 0, 1, 0, 0, 0): "Th",
        (0, 0, 0, 0, 1, 0, 0): "Fr",
        (0, 0, 0, 0, 0, 1, 0): "Sa",
        (0, 0, 0, 0, 0, 0, 1): "Su",
    }

    # The following function and above LUT is copied from the original monolithic implementation.
    # It's quite verbose, but I see no better way for it to be implemented. - Borketh
    def _daystring_neroden_hyphens_2l(
        self, days_of_service: dict[str, int], *, offset: int = 0, **_
    ) -> str:
        """
        Return "MoWeFr" style string for days of week.

        Given a calendar DataTable which contains only a single row for a single service,
        this returns a string like "Daily" or "MoWeFr" for the serviced days of the week.

        Use offset to get the string for stops which are more than 24 hours after initial
        departure. Beware of time zone changes!

        I have had more requests for tweaks to this format than anything else!
        """

        # Use modulo to correct the offset to the range 0:6
        # Note timezone differences can lead to -1 offset.
        # Later stations on the route lead to positive offset.
        offset %= 7

        # OK.  Fast encoding version here as a list of 1s and 0s.
        days_of_service_vector = [days_of_service[day] for day in self._DAYS_IN_WEEK]

        # Do the offset rotation.
        def rotate_right(vec: list, n: int) -> list:
            return vec[-n:] + vec[:-n]

        days_of_service_vector = rotate_right(days_of_service_vector, offset)

        # Try the lookup-table path.
        try:
            daystring = self._daystring_special_cases[tuple(days_of_service_vector)]
            return daystring
        except KeyError:
            pass

        # Lookup-table path failed.
        # Now we have to do it the hard way, by just patching days of the week together.
        # This probably means the days of non-operation are non-consecutive (MWF or whatever).

        # Now we get tricky.  We want the days of the week to line up as they cycle around the clock.
        # This is kind of messy!  We always use the order of the original, zero-offset day.
        # That's slightly wacky for the -1 offsets -- Su is first instead of Mo -- but that is OK.
        daystring = ""
        if days_of_service["monday"]:
            daystring += ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"][offset]
        if days_of_service["tuesday"]:
            daystring += ["Tu", "We", "Th", "Fr", "Sa", "Su", "Mo"][offset]
        if days_of_service["wednesday"]:
            daystring += ["We", "Th", "Fr", "Sa", "Su", "Mo", "Tu"][offset]
        if days_of_service["thursday"]:
            daystring += ["Th", "Fr", "Sa", "Su", "Mo", "Tu", "We"][offset]
        if days_of_service["friday"]:
            daystring += ["Fr", "Sa", "Su", "Mo", "Tu", "We", "Th"][offset]
        if days_of_service["saturday"]:
            daystring += ["Sa", "Su", "Mo", "Tu", "We", "Th", "Fr"][offset]
        if days_of_service["sunday"]:
            daystring += ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"][offset]

        if daystring == "":
            raise GTFSError("No days of operation?!?")

        # Generic case
        return daystring

    class DaystringHandler(Protocol):
        def __call__(
            self,
            self2: StyleHandler,
            days_of_service: dict[str, int],
            *,
            offset: int,
            html: bool,
            **_,
        ) -> str: ...

    _daystring_formats: dict[str, DaystringHandler] = {
        "hyphen-2l": _daystring_neroden_hyphens_2l,
        "numbers": _daystring_numbers,
        "letters-en": _daystring_letters_en,
        "letters-fr": _daystring_letters_fr,
        "letters-CA": _daystring_letters_ca_bilingual,
    }

    def format_daystring(
        self, days_of_service: dict[str, int], offset: int = 0, html: bool = False
    ) -> str:
        every_day_string = self._day_format["all"]  # For example, "Daily"
        some_days_format = self._day_format["some"]

        if every_day_string != some_days_format and all(days_of_service.values()):
            return every_day_string

        return self._daystring_formats[some_days_format](
            self, days_of_service, offset=offset, html=html
        )

    @property
    def special_css_tag(self) -> str:
        return self._special_css_tag
