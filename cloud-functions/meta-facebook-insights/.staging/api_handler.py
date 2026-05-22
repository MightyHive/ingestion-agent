from urllib.parse import urlencode
import time
import requests
import logging


class UnauthorizedException(Exception):
    """Exception raised when API returns 401 Unauthorized."""
    def __init__(self, message="Unauthorized access - invalid or expired token", response_data=None):
        super().__init__(message)
        self.status_code = 401
        self.response_data = response_data


class ForbiddenException(Exception):
    """Exception raised when API returns 403 Forbidden."""
    def __init__(self, message="Access forbidden - insufficient permissions", response_data=None):
        super().__init__(message)
        self.status_code = 403
        self.response_data = response_data


class ApiHandler(object):
    """
    Base ApiHandler class for HTTP API interactions.
    Designed to be subclassed for specific APIs.
    Subclasses should set self._base_url and may override _create_header() and request_api().

    Retry behavior:
        - Retries are configurable via constructor params `max_retries` and `retry_delay`.
        - A request will be retried on transient failures: HTTP 429, any 5xx,
          and network-level errors like ConnectionError and Timeout.
        - The number of attempts executed is `max_retries + 1` (initial try + retries).
        - `retry_delay` specifies the fixed wait time (in seconds) between attempts.
    """

    def __init__(self, access_token=None, timeout=None, max_retries=3, retry_delay=2.0):
        self._base_url = None  # Should be set in subclass
        self._access_token = access_token
        self._timeout = timeout
        self._session = requests.Session()
        self._max_retries = max(0, int(max_retries) if max_retries is not None else 0)
        self._retry_delay = float(retry_delay) if retry_delay is not None else 2.0
        self._create_header()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def close(self):
        return self._session.close()

    def _create_header(self):
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"
        self._session.headers.update(headers)

    @staticmethod
    def handle_response(response):
        try:
            return response.json()
        except ValueError:
            logging.warning("Received response with no content")
            return {}
        except Exception as e:
            logging.warning(e)
            return {}

    @staticmethod
    def url_joiner(url, path, params=None, trailing=None):
        url_link = path
        if url:
            url_link = "/".join(s.strip("/") for s in [url, path])
        if params:
            url_link += "?" + urlencode(params or {})
        if trailing:
            url_link += "/"
        return url_link

    def _get(self, path, _url=None, params=None, trailing=None):
        if _url is not None:
            url = _url
        else:
            if not self._base_url:
                raise ValueError("Base URL is not set.")
            url = self.url_joiner(
                url=self._base_url,
                path=path,
                params=params,
                trailing=trailing,
            )

        response = self._session.request(
            method="GET",
            url=url,
            headers=self._session.headers,
            timeout=self._timeout,
        )
        response.encoding = "utf-8"
        logging.info(f"HTTP: GET {url} -> {response.status_code} {response.reason}")

        if response.status_code == 401:
            raise UnauthorizedException(response_data=self.handle_response(response))
        elif response.status_code == 403:
            raise ForbiddenException(response_data=self.handle_response(response))
        print(response.text)
        response.raise_for_status()
        return response

    def request(self, path, _url=None, params=None, trailing=None):
        attempts = self._max_retries + 1
        for attempt_index in range(attempts):
            try:
                response = self._get(path=path, _url=_url, params=params, trailing=trailing)
                break
            except requests.exceptions.HTTPError as http_error:
                status_code = getattr(http_error.response, "status_code", None)
                should_retry = status_code in ([429] + list(range(500, 600)))
                if attempt_index >= attempts - 1 or not should_retry:
                    raise
                logging.info(f"Retry {attempt_index+1}/{self._max_retries} after HTTP {status_code}. Waiting {self._retry_delay}s ...")
                time.sleep(self._retry_delay)
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                if attempt_index >= attempts - 1:
                    raise
                logging.info(f"Retry {attempt_index+1}/{self._max_retries} after {type(e).__name__}. Waiting {self._retry_delay}s ...")
                time.sleep(self._retry_delay)

        if not response.text:
            return {}
        return self.handle_response(response)