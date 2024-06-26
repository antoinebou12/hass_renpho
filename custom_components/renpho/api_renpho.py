import asyncio
import datetime
import logging
import time
from base64 import b64encode
from typing import Callable, Dict, Final, List, Optional, Union

import aiohttp
from aiohttp import ClientTimeout
from aiohttp_socks import ProxyConnector
from Crypto.Cipher import PKCS1_v1_5
from Crypto.PublicKey import RSA

from .const import CONF_PUBLIC_KEY

METRIC_TYPE_WEIGHT: Final = "weight"
METRIC_TYPE_GROWTH_RECORD: Final = "growth_record"
METRIC_TYPE_GIRTH: Final = "girth"
METRIC_TYPE_GIRTH_GOAL: Final = "girth_goals"

from .api_object import UserResponse, DeviceBind, MeasurementDetail, Users, GirthGoal, GirthGoalsResponse, Girth, GirthResponse, MeasurementResponse

# Initialize logging
_LOGGER = logging.getLogger(__name__)

# API Endpoints
API_AUTH_URL = "https://renpho.qnclouds.com/api/v3/users/sign_in.json?app_id=Renpho" # Authentication Post
API_SCALE_USERS_URL = "https://renpho.qnclouds.com/api/v3/scale_users/list_scale_user" # Scale users
API_MEASUREMENTS_URL = "https://renpho.qnclouds.com/api/v2/measurements/list.json" # Measurements
DEVICE_INFO_URL = "https://renpho.qnclouds.com/api/v2/device_binds/get_device.json" # Device info
LATEST_MODEL_URL = "https://renpho.qnclouds.com/api/v3/devices/list_lastest_model.json" # Latest model
GIRTH_URL = "https://renpho.qnclouds.com/api/v3/girths/list_girth.json" # Girth
GIRTH_GOAL_URL = "https://renpho.qnclouds.com/api/v3/girth_goals/list_girth_goal.json" # Girth goal
GROWTH_RECORD_URL = "https://renpho.qnclouds.com/api/v3/growth_records/list_growth_record.json" # Growth record
MESSAGE_LIST_URL = "https://renpho.qnclouds.com/api/v2/messages/list.json" # message to support
USER_REQUEST_URL = "https://renpho.qnclouds.com/api/v2/users/request_user.json" # error
USERS_REACH_GOAL = "https://renpho.qnclouds.com/api/v3/users/reach_goal.json" # error 404


class RenphoWeight:
    """
    A class to interact with Renpho's weight scale API.

    Attributes:
        email (str): The email address for the Renpho account.
        password (str): The password for the Renpho account.
        user_id (str, optional): The ID of the user for whom weight data should be fetched.
    """

    def __init__(self, email, password, user_id=None, refresh=60, proxy=None):
        """Initialize a new RenphoWeight instance."""
        self.public_key: str = CONF_PUBLIC_KEY
        self.email: str = email
        self.password: str = password
        if user_id == "":
            user_id = None
        self.user_id: str = user_id
        self.refresh = refresh
        self.token: str = None
        self.session = None
        self.polling = False
        self.login_data = None
        self.users = []
        self.weight_info = None
        self.weight_history = []
        self.weight: float = None
        self.weight_goal = {}
        self.device_info = None
        self.latest_model = None
        self.girth_info = None
        self.girth_goal = None
        self.growth_record = None
        self._last_updated = None
        self._last_updated_weight = None
        self._last_updated_girth = None
        self._last_updated_girth_goal = None
        self._last_updated_growth_record = None
        self.auth_in_progress = False
        self.is_polling_active = False
        self.proxy = proxy

        _LOGGER.info(f"Initializing RenphoWeight instance. Proxy is {'enabled: ' + proxy if proxy else 'disabled.'}")

    @staticmethod
    def get_timestamp() -> int:
        start_date = datetime.date(1998, 1, 1)
        return int(time.mktime(start_date.timetuple()))


    def prepare_data(self, data):
        if isinstance(data, bytes):
            return data.decode("utf-8")
        elif isinstance(data, dict):
            return {key: self.prepare_data(value) for key, value in data.items()}
        elif isinstance(data, list):
            return [self.prepare_data(element) for element in data]
        else:
            return data

    async def open_session(self):
        """
        Open a new aiohttp session if one does not exist or is closed.
        """
        if self.session is None or self.session.closed:
            self.token = None
            self.session = aiohttp.ClientSession(
                headers={"Content-Type": "application/json", "Accept": "application/json"},
            )
        if self.session:
            await self.session.close()
            self.session = aiohttp.ClientSession(
                headers={"Content-Type": "application/json", "Accept": "application/json"},
            )

    async def check_proxy(self):
        """
        Checks if the proxy is working by making a request to a Renpho API endpoint.
        """
        test_url = 'http://httpbin.org/get'
    
        if not self.proxy:
            _LOGGER.info("No proxy configured. Proceeding without proxy.")
        else:
            _LOGGER.info(f"Checking proxy connectivity using proxy: {self.proxy}")
    
        try:
            connector = ProxyConnector.from_url(self.proxy) if self.proxy else None
            session = aiohttp.ClientSession(connector=connector)
            async with session.get(test_url) as response:
                if response.status == 200:
                    _LOGGER.info("Proxy check successful." if self.proxy else "Direct connection successful.")
                    return True
                else:
                    _LOGGER.error(f"Failed to connect using {'proxy' if self.proxy else 'direct connection'}. HTTP Status: {response.status}")
                    return False
        except Exception as e:
            _LOGGER.error(f"Proxy connection failed: {e}")
            return False
        finally:
            await session.close()

    async def _request(self, method: str, url: str, retries: int = 3, skip_auth=False, **kwargs):
        """
        Perform an API request and return the parsed JSON response.

        Parameters:
            method (str): The HTTP method to use for the request (e.g., "GET", "POST").
            url (str): The URL to which the request should be made.
            retries (int, optional): The number of times to retry the request if it fails. Defaults to 3.
            skip_auth (bool, optional): Whether to skip authentication. Defaults to False.
            **kwargs: Additional keyword arguments to pass to the request.

        Returns:
            Union[Dict, List]: The parsed JSON response from the API request.
        """
        if not await self.check_proxy():
            _LOGGER.error("Proxy check failed. Aborting authentication.")
            raise APIError("Proxy check failed. Aborting authentication.")
        while retries > 0:
            connector = ProxyConnector.from_url(self.proxy) if self.proxy else None
            async with aiohttp.ClientSession(connector=connector, headers={
                            "Content-Type": "application/json",
                            "Accept": "application/json",
                            "User-Agent": "Renpho/2.1.0 (iPhone; iOS 14.4; Scale/2.1.0; en-US)"
                        }, timeout=ClientTimeout(total=60)) as session:

                if not self.token and not url.endswith("sign_in.json") or not skip_auth:
                    auth_success = await self.auth()
                    if not auth_success:
                        raise AuthenticationError("Authentication failed. Unable to proceed with the request.")

                kwargs = self.prepare_data(kwargs)

                try:
                    async with session.request(method, url, **kwargs) as response:
                        response.raise_for_status()
                        parsed_response = await response.json()

                        if parsed_response.get("status_code") == "40302":
                            skip_auth = False
                            auth_success = await self.auth()
                            if not auth_success:
                                raise AuthenticationError("Authentication failed. Unable to proceed with the request.")
                            retries -= 1
                            continue # Retry the request
                        if parsed_response.get("status_code") == "50000":
                            raise APIError(f"Internal server error: {parsed_response.get('status_message')}")
                        if parsed_response.get("status_code") == "20000" and parsed_response.get("status_message") == "ok":
                            return parsed_response
                        else:
                            raise APIError(f"API request failed {method} {url}: {parsed_response.get('status_message')}")
                except (aiohttp.ClientResponseError, aiohttp.ClientConnectionError) as e:
                    _LOGGER.error(f"Client error: {e}")
                    raise APIError(f"API request failed {method} {url}") from e

    @staticmethod
    def encrypt_password(public_key_str, password):
        try:
            rsa_key = RSA.importKey(public_key_str)
            cipher = PKCS1_v1_5.new(rsa_key)
            return b64encode(cipher.encrypt(password.encode("utf-8"))).decode("utf-8")
        except Exception as e:
            _LOGGER.error(f"Encryption error: {e}")
            raise

    async def is_valid_session(self):
        """Check if the session key is valid."""
        return self.token is not None

    async def validate_credentials(self):
        """
        Validate the current credentials by attempting to authenticate.
        Returns True if authentication succeeds, False otherwise.
        """
        _LOGGER.debug("Validating credentials for user: %s", self.email)
        try:
            return await self.auth()
        except Exception as e:
            _LOGGER.error("Failed to validate credentials for user: %s. Error: %s", self.email, e)
            raise AuthenticationError(f"Invalid credentials for user {self.email}. Error details: {e}") from e


    async def auth(self):
        """Authenticate with the Renpho API."""

        if self.auth_in_progress:
            return False  # Avoid re-entry if already in progress

        self.auth_in_progress = True

        if not self.email or not self.password:
            raise AuthenticationError("Email and password are required for authentication.")

        if self.public_key is None:
            _LOGGER.error("Public key is None.")
            raise AuthenticationError("Public key is None.")

        encrypted_password = self.encrypt_password(self.public_key, self.password)

        data = self.prepare_data({"secure_flag": "1", "email": self.email,
                "password": encrypted_password})

        for attempt in range(3):
            try:
                self.token = None
                if not await self.check_proxy():
                    _LOGGER.error("Proxy check failed. Aborting authentication.")
                    raise APIError("Proxy check failed. Aborting authentication.")
                
                connector = ProxyConnector.from_url(self.proxy) if self.proxy else None
                async with aiohttp.ClientSession(connector=connector, headers={
                                "Content-Type": "application/json",
                                "Accept": "application/json",
                                "User-Agent": "Renpho/2.1.0 (iPhone; iOS 14.4; Scale/2.1.0; en-US)"
                            }, timeout=ClientTimeout(total=60)) as session:

                    async with session.request("POST", API_AUTH_URL, json=data) as response:
                        response.raise_for_status()
                        parsed = await response.json()

                        if parsed is None:
                            _LOGGER.error("Authentication failed. No response received.")
                            raise AuthenticationError("Authentication failed. No response received.")

                        if parsed.get("status_code") == "50000" and parsed.get("status_message") == "Email was not registered":
                            _LOGGER.warning("Email was not registered.")
                            raise AuthenticationError("Email was not registered.")

                        if parsed.get("status_code") == "500" and parsed.get("status_message") == "Internal Server Error":
                            _LOGGER.warning("Bad Password or Internal Server Error.")
                            raise AuthenticationError("Bad Password or Internal Server Error.")

                        if "terminal_user_session_key" not in parsed:
                            _LOGGER.error(
                                "'terminal_user_session_key' not found in parsed object.")
                            raise AuthenticationError(f"Authentication failed: {parsed}")

                        if parsed.get("status_code") == "20000" and parsed.get("status_message") == "ok":
                            if 'terminal_user_session_key' in parsed:
                                self.token = parsed["terminal_user_session_key"]
                            else:
                                self.token = None
                                raise AuthenticationError("Session key not found in response.")
                            if 'device_binds_ary' in parsed:
                                parsed['device_binds_ary'] = [DeviceBind(**device) for device in parsed['device_binds_ary']]
                            else:
                                parsed['device_binds_ary'] = []
                            self.login_data = UserResponse(**parsed)
                            self.token = parsed["terminal_user_session_key"]
                            if self.user_id is None:
                                self.user_id = self.login_data.get("id", None)
                            return True
            except (aiohttp.ClientResponseError, aiohttp.ClientConnectionError) as e:
                _LOGGER.error(f"Authentication failed: {e}")
                if attempt < 3 - 1:
                    await asyncio.sleep(5)  # Wait before retrying
                else:
                    raise AuthenticationError(f"Authentication failed after retries. {e}") from e
            finally:
                self.auth_in_progress = False

    async def get_scale_users(self):
        """
        Fetch the list of users associated with the scale.
        """
        url = f"{API_SCALE_USERS_URL}?locale=en&app_id=Renpho&terminal_user_session_key={self.token}"
        # Perform the API request
        try:
            parsed = await self._request("GET", url, skip_auth=True)

            if not parsed:
                _LOGGER.error("Failed to fetch scale users.")
                return Users(
                    scale_user_id=None,
                    user_id=None,
                    mac=None,
                    index=None,
                    key=None,
                    method=None
                )

            # Check if the response is valid and contains 'scale_users'
            if "scale_users" in parsed:
                # Update the 'users' attribute with parsed and validated ScaleUser objects
                self.users = [Users(**user) for user in parsed["scale_users"]]
            else:
                _LOGGER.error("Failed to fetch scale users or no scale users found in the response.")

            self.user_id = self.users[0].user_id
            return self.users
        except Exception as e:
            _LOGGER.error(f"Failed to fetch scale users: {e}")
            return []

    async def get_measurements(self):
        """
        Fetch the most recent weight measurements for the user.
        """
        url = f"{API_MEASUREMENTS_URL}?user_id={self.user_id}&last_at={self.get_timestamp()}&locale=en&app_id=Renpho&terminal_user_session_key={self.token}"
        try:
            parsed = await self._request("GET", url, skip_auth=True)

            if not parsed:
                _LOGGER.error("Failed to fetch weight measurements.")
                return

            if "status_code" in parsed and parsed["status_code"] == "20000":
                if "last_ary" not in parsed:
                    _LOGGER.error("No weight measurements found in the response.")
                    return
                if measurements := parsed["last_ary"]:
                    self.weight_history = [MeasurementDetail(**measurement) for measurement in measurements]
                    self.weight_info = self.weight_history[0] if self.weight_history else None
                    self.weight = self.weight_info.weight if self.weight_info else None
                    self.time_stamp = self.weight_info.time_stamp if self.weight_info else None
                    self._last_updated_weight = time.time()
                    return self.weight_info
                else:
                    _LOGGER.error("No weight measurements found in the response.")
                    return None
            else:
                # Handling different error scenarios
                if "status_code" not in parsed:
                    _LOGGER.error("Invalid response format received from weight measurements endpoint.")
                else:
                    _LOGGER.error(f"Error fetching weight measurements: Status Code {parsed.get('status_code')} - {parsed.get('status_message')}")
                return None

        except Exception as e:
            _LOGGER.error(f"Failed to fetch weight measurements: {e}")
            return None

    async def get_weight(self):
        if self.weight and self.weight_info:
            return self.weight, self.weight_info
        self._last_updated_weight = time.time()
        return self.weight, await self.get_measurements()

    async def get_info(self):
        self._last_updated_weight = time.time()
        return await self.get_measurements()

    async def get_device_info(self):
        """
        Fetch device information and update the class attribute with device bind details.
        """
        url = f"{DEVICE_INFO_URL}?user_id={self.user_id}&last_updated_at={self.get_timestamp()}&locale=en&app_id=Renpho&terminal_user_session_key={self.token}"
        try:
            parsed = await self._request("GET", url, skip_auth=True)

            if not parsed:
                _LOGGER.error("Failed to fetch device info.")
                return None

            # Check for successful response code
            if parsed.get("status_code") == "20000" and "device_binds_ary" in parsed:
                device_info = [DeviceBind(**device) for device in parsed["device_binds_ary"]]
                self.device_info = device_info
                return device_info
            else:
                # Handling different error scenarios
                if "status_code" not in parsed:
                    _LOGGER.error("Invalid response format received from device info endpoint.")
                else:
                    _LOGGER.error(f"Error fetching device info: Status Code {parsed.get('status_code')} - {parsed.get('status_message')}")
                return None
        except Exception as e:
            _LOGGER.error(f"Failed to fetch device info: {e}")
            return None

    async def list_latest_model(self):
        """
        Fetch the latest model for the user.
        """
        url = f"{LATEST_MODEL_URL}?user_id={self.user_id}&last_updated_at={self.get_timestamp()}&locale=en&app_id=Renpho&terminal_user_session_key={self.token}$internal_model_json=%5B%22{self.weight_info.internal_model}%22%5D"
        try:
            parsed = await self._request("GET", url, skip_auth=True)

            if not parsed:
                _LOGGER.error("Failed to fetch latest model.")
                return None

            if "status_code" in parsed and parsed["status_code"] == "20000":
                self.latest_model = parsed
                return parsed
            else:
                _LOGGER.error(f"Error fetching latest model: {parsed.get('status_message')}")
                return None
        except Exception as e:
            _LOGGER.error(f"Failed to fetch latest model: {e}")
            return None

    async def list_girth(self):
        url = f"{GIRTH_URL}?user_id={self.user_id}&last_updated_at={self.get_timestamp()}&locale=en&app_id=Renpho&terminal_user_session_key={self.token}"
        try:
            parsed = await self._request("GET", url, skip_auth=True)

            if not parsed:
                _LOGGER.error("Failed to fetch girth info.")
                return None

            if "status_code" in parsed and parsed["status_code"] == "20000":
                response = GirthResponse(**parsed)
                self._last_updated_girth = time.time()
                self.girth_info = response.girths
                return self.girth_info
            else:
                _LOGGER.error(f"Error fetching girth info: {parsed.get('status_message')}")
                return None

        except Exception as e:
            _LOGGER.error(f"Failed to fetch girth info: {e}")
            return None

    async def list_girth_goal(self):
        """
        Fetch the girth goal for the user.
        """
        url = f"{GIRTH_GOAL_URL}?user_id={self.user_id}&last_updated_at={self.get_timestamp()}&locale=en&app_id=Renpho&terminal_user_session_key={self.token}"
        try:
            parsed = await self._request("GET", url, skip_auth=True)

            if not parsed:
                _LOGGER.error("Failed to fetch girth goal.")
                return None

            if "status_code" in parsed and parsed["status_code"] == "20000":
                response = GirthGoalsResponse(**parsed)
                self.girth_goal = response.girth_goals
                self._last_updated_girth_goal = time.time()
                return self.girth_goal
            else:
                _LOGGER.error(f"Error fetching girth goal: {parsed.get('status_message')}")
                return None
        except Exception as e:
            _LOGGER.error(f"Failed to fetch girth goal: {e}")
            return None

    async def list_growth_record(self):
        """
        Fetch the growth record for the user.
        """

        url = f"{GROWTH_RECORD_URL}?user_id={self.user_id}&last_updated_at={self.get_timestamp()}&locale=en&app_id=Renpho&terminal_user_session_key={self.token}"
        try:
            parsed = await self._request("GET", url, skip_auth=True)

            if not parsed:
                _LOGGER.error("Failed to fetch growth record.")
                return None

            if "status_code" in parsed and parsed["status_code"] == "20000":
                self.growth_record = parsed
                self._last_updated_growth_record = time.time()
                return parsed
            else:
                _LOGGER.error(f"Error fetching growth record: {parsed.get('status_message')}")
                return None
        except Exception as e:
            _LOGGER.error(f"Failed to fetch growth record: {e}")
            return None

    async def message_list(self):
        """
        Asynchronously list messages.
        """
        url = f"{MESSAGE_LIST_URL}?user_id={self.user_id}&last_updated_at={self.get_timestamp()}&locale=en&app_id=Renpho&terminal_user_session_key={self.token}"
        try:
            parsed = await self._request("GET", url, skip_auth=True)

            if not parsed:
                _LOGGER.error("Failed to fetch messages.")
                return None

            if "status_code" in parsed and parsed["status_code"] == "20000":
                return parsed
            _LOGGER.error(f"Error fetching messages: {parsed.get('status_message')}")
            return None
        except Exception as e:
            _LOGGER.error(f"Failed to fetch messages: {e}")
            return None

    async def request_user(self):
        """
        Asynchronously request user
        """
        url = f"{USER_REQUEST_URL}?user_id={self.user_id}&last_updated_at={self.get_timestamp()}&locale=en&app_id=Renpho&terminal_user_session_key={self.token}"
        try:
            parsed = await self._request("GET", url, skip_auth=True)

            if not parsed:
                _LOGGER.error("Failed to request user.")
                return None

            if "status_code" in parsed and parsed["status_code"] == "20000":
                return parsed
            _LOGGER.error(f"Error requesting user: {parsed.get('status_message')}")
            return None
        except Exception as e:
            _LOGGER.error(f"Failed to request user: {e}")
            return None

    async def reach_goal(self):
        """
        Asynchronously reach goal
        """

        url = f"{USERS_REACH_GOAL}?user_id={self.user_id}&last_updated_at={self.get_timestamp()}&locale=en&app_id=Renpho&terminal_user_session_key={self.token}"
        try:
            parsed = await self._request("GET", url, skip_auth=True)

            if not parsed:
                _LOGGER.error("Failed to reach goal.")
                return None

            if "status_code" in parsed and parsed["status_code"] == "20000":
                return parsed
            _LOGGER.error(f"Error reaching goal: {parsed.get('status_message')}")
            return None
        except Exception as e:
            _LOGGER.error(f"Failed to reach goal: {e}")
            return None

    async def get_specific_metric(self, metric_type: str, metric: str, user_id: Optional[str] = None):
        """
        Fetch a specific metric for a particular user ID based on the type specified.

        Parameters:
            metric_type (str): The type of metric to fetch.
            metric (str): The specific metric to fetch.
            user_id (Optional[str]): The user ID for whom to fetch the metric. Defaults to None.
        """


        if user_id:
            self.user_id = user_id

        try:
            if metric_type == METRIC_TYPE_WEIGHT:
                if self._last_updated_weight is None or self.weight:
                    if self.weight_info is not None:
                        return self.weight_info.get(metric, None)
                return self.weight_info.get(metric, None) if self.weight_info else None
            elif metric_type == METRIC_TYPE_GIRTH:
                if self._last_updated_girth is None or self.girth_info is None:
                    await self.list_girth()
                if self.girth_info:
                    valid_girths = sorted([g for g in self.girth_info if getattr(g, f"{metric}_value", 0) not in (None, 0.0)], key=lambda x: x.time_stamp, reverse=True)
                    for girth in valid_girths:
                        value = getattr(girth, f"{metric}_value", None)
                        if value not in (None, 0.0):
                            return value
                    return None
            elif metric_type == METRIC_TYPE_GIRTH_GOAL:
                if self._last_updated_girth_goal is None or self.girth_goal is None:
                    await self.list_girth_goal()
                if self.girth_goal:
                    valid_goals = sorted([g for g in self.girth_goal if g.girth_type == metric and g.goal_value not in (None, 0.0)], key=lambda x: x.setup_goal_at, reverse=True)
                    # Iterate to find the first valid goal
                    for goal in valid_goals:
                        if goal.goal_value not in (None, 0.0):
                            return goal.goal_value
                    return None
            else:
                _LOGGER.error(f"Invalid metric type: {metric_type}")
                return None
        except Exception as e:
            _LOGGER.error(f"Failed to fetch specific metric: {e}")
            return None

    async def poll_data(self):
        """
        The core polling logic that fetches data and processes it.
        """
        try:
            asyncio.gather(
                await self.get_info(),
                await self.list_girth(),
                await self.list_girth_goal(),
            )

            _LOGGER.info("Data fetched successfully.")
        except Exception as e:
            _LOGGER.error(f"Error fetching data: {e}")

    async def start_polling(self):
        """
        Start the polling process.
        """
        if self.is_polling_active:
            _LOGGER.warning("Polling is already active.")
            return

        self.is_polling_active = True
        self.polling_task = asyncio.create_task(self.polling_loop())

    async def polling_loop(self):
        """
        The polling loop that runs until is_polling_active is False.
        """
        try:
            while self.is_polling_active:
                await self.poll_data()
                await asyncio.sleep(self.refresh_interval)
        except asyncio.CancelledError:
            _LOGGER.info("Polling task was cancelled.")
        except Exception as e:
            _LOGGER.error(f"Unexpected error in polling loop: {e}")
        finally:
            _LOGGER.info("Polling loop exited.")

    def stop_polling(self):
        """
        Stop the polling process.
        """
        if not self.is_polling_active:
            _LOGGER.warning("Polling is not active.")
            return

        if self.polling_task:
            self.polling_task.cancel()
            _LOGGER.info("Polling has been stopped.")
            self.is_polling_active = False
            self.polling_task = None

    async def close(self):
        """
        Clean up resources, stop polling, and close sessions.
        """
        self.stop_polling()
        if self.session:
            await self.session.close()
            _LOGGER.info("Aiohttp session closed")

class AuthenticationError(Exception):
    pass


class APIError(Exception):
    pass


class ClientSSLError(Exception):
    pass
