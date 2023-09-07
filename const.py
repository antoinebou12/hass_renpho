# Constants for the Renpho integration

# The domain of the component. Used to store data in hass.data.
from typing import Final


DOMAIN: Final = "renpho"
VERSION: Final = "1.0.0"
EVENT_HOMEASSISTANT_CLOSE: Final = "homeassistant_close"
EVENT_HOMEASSISTANT_START: Final = "homeassistant_start"
EVENT_HOMEASSISTANT_STARTED: Final = "homeassistant_started"
EVENT_HOMEASSISTANT_STOP: Final = "homeassistant_stop"
MASS_KILOGRAMS: Final = "kg"
TIME_SECONDS: Final = "s"

# Configuration keys
CONF_EMAIL: Final = 'email'        # The email used for Renpho login
CONF_PASSWORD: Final = 'password'  # The password used for Renpho login
CONF_REFRESH: Final = 'refresh'    # Refresh rate for pulling new data
CONF_UNIT: Final = 'unit'          # Unit of measurement for weight (kg/lbs)
CONF_USER_ID: Final = 'user_id'    # The ID of the user for whom weight data should be fetched

KG_TO_LBS: Final = 2.20462
CM_TO_INCH: Final = 0.393701

# General Information Metrics
ID: Final = "id"
B_USER_ID: Final = "b_user_id"
TIME_STAMP: Final = "time_stamp"
CREATED_AT: Final = "created_at"
CREATED_STAMP: Final = "created_stamp"

# Device Information Metrics
SCALE_TYPE: Final = "scale_type"
SCALE_NAME: Final = "scale_name"
MAC: Final = "mac"
INTERNAL_MODEL: Final = "internal_model"
TIME_ZONE: Final = "time_zone"

# User Profile Metrics
GENDER: Final = "gender"
HEIGHT: Final = "height"
HEIGHT_UNIT: Final = "height_unit"
BIRTHDAY: Final = "birthday"

# Physical Metrics
WEIGHT: Final = "weight"
BMI: Final = "bmi"
MUSCLE: Final = "muscle"
BONE: Final = "bone"
WAISTLINE: Final = "waistline"
HIP: Final = "hip"
STATURE: Final = "stature"

# Body Composition Metrics
BODYFAT: Final = "bodyfat"
WATER: Final = "water"
SUBFAT: Final = "subfat"
VISFAT: Final = "visfat"

# Metabolic Metrics
BMR: Final = "bmr"
PROTEIN: Final = "protein"

# Age Metrics
BODYAGE: Final = "bodyage"

# Public key for encrypting the password
CONF_PUBLIC_KEY: Final = '''-----BEGIN PUBLIC KEY-----
MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQC+25I2upukpfQ7rIaaTZtVE744
u2zV+HaagrUhDOTq8fMVf9yFQvEZh2/HKxFudUxP0dXUa8F6X4XmWumHdQnum3zm
Jr04fz2b2WCcN0ta/rbF2nYAnMVAk2OJVZAMudOiMWhcxV1nNJiKgTNNr13de0EQ
IiOL2CUBzu+HmIfUbQIDAQAB
-----END PUBLIC KEY-----'''
