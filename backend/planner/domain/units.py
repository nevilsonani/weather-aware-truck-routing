"""Unit conversions. Internally everything is SI (metres, seconds, kilograms) and UTC."""

METERS_PER_MILE = 1609.344
METERS_PER_KM = 1000.0
KG_PER_LB = 0.45359237
SECONDS_PER_HOUR = 3600.0
MPS_PER_MPH = METERS_PER_MILE / SECONDS_PER_HOUR


def miles_to_meters(miles: float) -> float:
    return miles * METERS_PER_MILE


def meters_to_miles(meters: float) -> float:
    return meters / METERS_PER_MILE


def lbs_to_tonnes(lbs: float) -> float:
    return lbs * KG_PER_LB / 1000.0


def mph_to_mps(mph: float) -> float:
    return mph * MPS_PER_MPH
