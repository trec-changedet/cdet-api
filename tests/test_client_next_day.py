"""
Tests for CDetClient.next_day() error handling.

Regression test for the UnboundLocalError introduced when session.get()
raises a transport-level exception before a response is received.
"""

import pytest
import requests
from unittest.mock import MagicMock, patch

from cdet_api.client import CDetClient, NoMoreDaysException


@pytest.fixture
def client():
    return CDetClient(base_url="http://localhost:8000")


class TestNextDayErrorHandling:

    def test_404_raises_no_more_days_exception(self, client):
        """Server returning 404 signals end-of-stream → NoMoreDaysException."""
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.raise_for_status.side_effect = requests.HTTPError(response=mock_resp)

        with patch.object(client.session, "get", return_value=mock_resp):
            with pytest.raises(NoMoreDaysException):
                client.next_day(token="test-token")

    def test_connection_error_does_not_raise_unbound_local_error(self, client):
        """
        Regression test: when session.get() itself raises (transport failure),
        the except block must not reference the unbound local `response`.

        Before the fix, this crashed with:
            UnboundLocalError: cannot access local variable 'response'
            where it is not associated with a value

        Full traceback (Python 3.14):

            File "client.py", line 39, in next_day
                response = self.session.get(url, params=params, timeout=self.timeout)
            File "mock.py", in _execute_mock_call
                raise effect
            requests.exceptions.ConnectionError: connection refused

            During handling of the above exception, another exception occurred:

            File "client.py", line 46, in next_day
                if response.status_code == 404:
            UnboundLocalError: cannot access local variable 'response'
            where it is not associated with a value
        """
        with patch.object(client.session, "get",
                          side_effect=requests.ConnectionError("connection refused")):
            # Must not raise UnboundLocalError — transport failures should be
            # handled gracefully (logged) and return None.
            result = client.next_day(token="test-token")
            assert result is None

    def test_timeout_does_not_raise_unbound_local_error(self, client):
        """Timeout is another transport-level failure that never assigns response."""
        with patch.object(client.session, "get",
                          side_effect=requests.Timeout("timed out")):
            result = client.next_day(token="test-token")
            assert result is None

    def test_200_returns_documents(self, client):
        """Sanity check: a successful response returns the document list."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = []

        with patch.object(client.session, "get", return_value=mock_resp):
            result = client.next_day(token="test-token")
            assert result == []
