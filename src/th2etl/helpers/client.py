from __future__ import annotations

import logging
from typing import Any

import requests
from requests import Session

logger = logging.getLogger(__name__)


class HttpClient:
    """A generic HTTP client for making API calls to different services."""

    def __init__(self, base_url: str, session: Session | None = None, auth_token: str | None = None):
        """
        Initializes the HTTP client.

        :param base_url: The base URL for the service.
        :param session: An optional requests.Session object for connection pooling.
        :param auth_token: An optional bearer token for authentication.
        """
        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()
        if auth_token:
            self.session.headers.update({"Authorization": f"Bearer {auth_token}"})

    def _request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
        headers: dict[str, Any] | None = None,
    ) -> Any:
        """
        A wrapper function to make HTTP requests and handle responses.

        :param method: The HTTP method (GET, POST, PUT, DELETE).
        :param endpoint: The API endpoint to call (e.g., '/users').
        :param params: URL parameters.
        :param json_data: The JSON payload for the request body.
        :param headers: Additional headers for the request.
        :return: The JSON response from the API.
        """
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        
        try:
            response = self.session.request(
                method=method,
                url=url,
                params=params,
                json=json_data,
                headers=headers,
            )
            response.raise_for_status()
            
            # Handle cases where response may be empty
            if response.status_code == 204 or not response.content:
                return None
                
            return response.json()
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error for {method} {url}: {e.response.status_code} {e.response.text}")
            raise
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed for {method} {url}: {e}")
            raise

    def get(self, endpoint: str, params: dict[str, Any] | None = None, headers: dict[str, Any] | None = None) -> Any:
        """Performs a GET request."""
        return self._request("GET", endpoint, params=params, headers=headers)

    def post(self, endpoint: str, json_data: dict[str, Any] | None = None, headers: dict[str, Any] | None = None) -> Any:
        """Performs a POST request."""
        return self._request("POST", endpoint, json_data=json_data, headers=headers)

    def put(self, endpoint: str, json_data: dict[str, Any] | None = None, headers: dict[str, Any] | None = None) -> Any:
        """Performs a PUT request."""
        return self._request("PUT", endpoint, json_data=json_data, headers=headers)

    def delete(self, endpoint: str, headers: dict[str, Any] | None = None) -> Any:
        """Performs a DELETE request."""
        return self._request("DELETE", endpoint, headers=headers)
