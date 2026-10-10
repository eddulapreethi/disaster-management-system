import json
import unittest
from unittest.mock import MagicMock, patch

from app.services import geocoding_service as service


class GeocodingServiceTests(unittest.TestCase):
    def test_search_locations_normalizes_open_meteo_results(self) -> None:
        payload = {
            "results": [
                {
                    "id": 1,
                    "name": "Hyderabad",
                    "admin1": "Telangana",
                    "admin2": "Hyderabad",
                    "country": "India",
                    "latitude": 17.385,
                    "longitude": 78.4867,
                    "timezone": "Asia/Kolkata",
                    "population": 6800000,
                }
            ]
        }
        mock_response = MagicMock()
        mock_response.__enter__.return_value.read.return_value = json.dumps(payload).encode("utf-8")

        with patch.object(service, "urlopen", return_value=mock_response):
            results = service.search_locations("Hyderabad", limit=5)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["name"], "Hyderabad")
        self.assertEqual(results[0]["admin1"], "Telangana")
        self.assertEqual(results[0]["country"], "India")
        self.assertEqual(results[0]["display_name"], "Hyderabad, Telangana, Hyderabad, India")
        self.assertAlmostEqual(results[0]["latitude"], 17.385)
        self.assertAlmostEqual(results[0]["longitude"], 78.4867)

    def test_search_locations_rejects_short_query_and_network_failures(self) -> None:
        self.assertEqual(service.search_locations("H"), [])

        with patch.object(service, "urlopen", side_effect=TimeoutError("timed out")):
            with self.assertRaisesRegex(RuntimeError, "Location search failed"):
                service.search_locations("Kolkata")

    def test_search_locations_ignores_malformed_response_entries(self) -> None:
        payload = {
            "results": [
                {"name": "Paris", "latitude": "48.8566", "longitude": "2.3522", "country": "France"},
                {"name": "", "latitude": 10, "longitude": 20, "country": "Bad data"},
            ]
        }
        mock_response = MagicMock()
        mock_response.__enter__.return_value.read.return_value = json.dumps(payload).encode("utf-8")

        with patch.object(service, "urlopen", return_value=mock_response):
            results = service.search_locations("Paris")

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["country"], "France")
