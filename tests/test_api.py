"""HTTP API end to end with Flask's test client (no MQTT broker, no network)."""

import unittest
from datetime import date, timedelta

import _setup
from app import create_app


class Api(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.testing = True

    def setUp(self):
        self.client = self.app.test_client()
        email = f"farmer{id(self)}@test.local"
        r = self.client.post("/api/auth/register", json={"name": "Test Farmer", "email": email, "password": "secret12"})
        self.assertEqual(r.status_code, 201)

    def post(self, url, body):
        return self.client.post(url, json=body)

    def test_login_required(self):
        anon = self.app.test_client()
        for url in ("/api/meta", "/api/history", "/api/tasks/upcoming"):
            self.assertEqual(anon.get(url).status_code, 401, url)
        self.assertEqual(anon.post("/api/plan", json={}).status_code, 401)

    def test_auth_validation(self):
        anon = self.app.test_client()
        self.assertEqual(anon.post("/api/auth/register", json={"name": "a", "email": "b@c", "password": "123"}).status_code, 400)
        self.assertEqual(anon.post("/api/auth/login", json={"email": "nobody@x", "password": "wrongpw"}).status_code, 401)

    def test_meta(self):
        m = self.client.get("/api/meta").get_json()
        self.assertIn("market", m)
        self.assertFalse(m["market"]["configured"])     # tests run without the API key

    def test_recommend(self):
        r = self.post("/api/recommend", {"soil": _setup.SOIL, "area": 2, "irrigation": True,
                                         "taluka": "Haveli", "sowing_date": (date.today() + timedelta(days=10)).isoformat()})
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertTrue(body["sow_now"] or body["later"])
        for c in body["sow_now"]:
            self.assertIn("economics", c)
            self.assertTrue(c["fertilizer"]["schedule"]["steps"])

    def test_recommend_rejects_bad_input(self):
        bad = [
            {"soil": dict(_setup.SOIL, pH=19), "area": 1},
            {"soil": {"pH": 7}, "area": 1},
            {"soil": _setup.SOIL, "area": -1},
            {"soil": _setup.SOIL, "area": 1, "sowing_date": "2020-01-01"},
            {"soil": _setup.SOIL, "area": 1, "sowing_date": "not-a-date"},
        ]
        for body in bad:
            self.assertEqual(self.post("/api/recommend", body).status_code, 400, body)

    def test_plan(self):
        r = self.post("/api/plan", {"total_ha": 12, "plots": 3, "irrigated_ha": 6, "sowing_date": "2026-11-01",
                                    "taluka": "Haveli", "soil": _setup.SOIL})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.get_json()["plots"]), 3)
        r = self.post("/api/plan", {"total_ha": "twelve", "plots": 3, "soil": _setup.SOIL})
        self.assertEqual(r.status_code, 400)

    def test_save_history_and_tasks(self):
        rec = self.post("/api/recommend", {"soil": _setup.SOIL, "area": 1, "irrigation": True, "taluka": "Haveli",
                                           "sowing_date": date.today().isoformat()}).get_json()
        crop = (rec["sow_now"] or rec["later"])[0]
        sched = crop["fertilizer"]["schedule"]
        r = self.post("/api/recommend/save", {"crop_name": crop["crop"], "taluka": "Haveli",
                                              "sowing_date": date.today().isoformat(), "schedule": sched})
        self.assertEqual(r.status_code, 200)
        history = self.client.get("/api/history").get_json()
        self.assertEqual(history[0]["crop_name"], crop["crop"])
        tasks = self.client.get("/api/tasks/upcoming").get_json()
        self.assertTrue(all(t["crop"] == crop["crop"] for t in tasks))
        self.assertEqual(self.post("/api/recommend/save", {"crop_name": "Banana"}).status_code, 400)
        self.assertEqual(self.client.delete(f"/api/history/{history[0]['id']}").status_code, 200)

    def test_irrigation_config(self):
        r = self.post("/api/irrigation/config", {"mode": "manual"})
        self.assertEqual(r.get_json()["mode"], "manual")
        r = self.post("/api/irrigation/config", {"pump": True})
        self.assertTrue(r.get_json()["pump_on"])
        self.post("/api/irrigation/config", {"pump": False})
        r = self.post("/api/irrigation/config", {"mode": "auto"})
        self.assertEqual(self.post("/api/irrigation/config", {"pump": True}).status_code, 400)
        self.assertEqual(self.post("/api/irrigation/config", {"mode": "x"}).status_code, 400)

    def test_pages_served(self):
        for url in ("/", "/dashboard", "/js/dashboard.js", "/css/style.css"):
            self.assertEqual(self.client.get(url).status_code, 200, url)


if __name__ == "__main__":
    unittest.main()
