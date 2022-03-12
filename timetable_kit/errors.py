# errors.py
# Part of timetable_kit
# Copyright 2021, 2022 Nathanael Nerode.  Licensed under GNU Affero GPL v.3 or later.
"""
Errors for timetable_kit

Contains:
GTFSError
NoStopError
TwoStopsError
NoTripError
TwoTripsError
InputError
"""

class GTFSError(ValueError):
    """Exception for unexpected data in the GTFS feed."""
    pass

class NoStopError(GTFSError):
    """Exception when a train doesn't stop at a station.  Frequently caught."""

class TwoStopsError(GTFSError):
    """Exception when a train stops at a station twice.  Frequently caught."""

class NoTripError(GTFSError):
    """Exception when no trips where one is expected."""

class TwoTripsError(GTFSError):
    """Exception when several trips where one is expected."""

class InputError(ValueError):
    """Exception for unexpected data passed in by the user."""
    pass