"""Yesim Partner API client (https://partners-api.yesim.biz).

Auth: `token` query param on every request. Wholesale prices are in the partner
account currency (EUR for us). All calls are synchronous with short timeouts;
callers decide how to degrade (queue for retry, notify admin).
"""
from __future__ import annotations

import logging
from typing import Any

import requests
from django.conf import settings

log = logging.getLogger(__name__)


class YesimError(Exception):
    def __init__(self, message, *, status=None, payload=None):
        super().__init__(message)
        self.status = status
        self.payload = payload


class YesimClient:
    def __init__(self, token: str | None = None, base: str | None = None, timeout: int = 40):
        self.token = token or settings.YESIM_API_TOKEN
        self.base = (base or settings.YESIM_API_BASE).rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers["User-Agent"] = "esimsterr/1.0 (+https://esimsterr.com)"

    @property
    def configured(self) -> bool:
        return bool(self.token)

    def _call(self, method: str, path: str, **params) -> Any:
        if not self.token:
            raise YesimError("YESIM_API_TOKEN is not configured")
        params = {k: v for k, v in params.items() if v is not None and v != ""}
        params["token"] = self.token
        url = f"{self.base}/{path.lstrip('/')}"
        try:
            r = self.session.request(method, url, params=params, timeout=self.timeout)
        except requests.RequestException as e:
            raise YesimError(f"Yesim request failed: {e}") from e
        try:
            data = r.json()
        except ValueError:
            data = r.text
        if r.status_code >= 400:
            raise YesimError(f"Yesim {method} {path} -> {r.status_code}: {str(data)[:300]}",
                             status=r.status_code, payload=data)
        # Some error cases come back as 200 with a bare list of messages.
        if isinstance(data, list) and data and isinstance(data[0], str):
            raise YesimError("; ".join(data), status=r.status_code, payload=data)
        return data

    # ---- catalogue -----------------------------------------------------------
    def plans(self, plan_type: str | None = None, plan_id: str | None = None) -> list[dict]:
        data = self._call("GET", "/plans", filter=plan_type, plan_id=plan_id)
        return data if isinstance(data, list) else [data]

    def balance(self) -> dict:
        return self._call("GET", "/balance")

    def supported_devices(self) -> list[dict]:
        return self._call("GET", "/supported_devices")

    def allowed_operators(self, country: str | None = None) -> list[dict]:
        return self._call("GET", "/allowed_operators", country=country)

    # ---- users / eSIMs ---------------------------------------------------------
    def new_user(self, email: str) -> dict:
        return self._call("POST", "/new_user", email=email)

    def user(self, user_id: str) -> dict:
        return self._call("GET", "/user", user_id=user_id)

    def new_esim(self, plan_id: str | None = None, user_id: str | None = None) -> dict:
        """Issue a fresh eSIM; with plan_id the plan is bought+attached in one go."""
        return self._call("GET", "/new_esim", plan_id=plan_id, user_id=user_id)

    def add_plan(self, iccid: str, plan_id: str, payment_id: str | None = None) -> dict:
        """Top-up / attach a plan to an existing eSIM. Charges the partner balance."""
        data = self._call("POST", "/add_plan_iccid", iccid=iccid, plan_id=plan_id, payment_id=payment_id)
        if isinstance(data, dict) and data.get("status") not in (None, "success"):
            raise YesimError(data.get("description") or "Plan activation declined", payload=data)
        return data

    def cancel_plan(self, iccid: str) -> Any:
        return self._call("POST", "/cancel_plan", iccid=iccid)

    def sim_info(self, iccid: str) -> dict:
        return self._call("GET", "/sim_info", iccid=iccid)

    def change_esim(self, iccid: str) -> dict:
        return self._call("POST", "/change_esim", iccid=iccid)

    def orders(self, search: str | None = None) -> list[dict]:
        return self._call("GET", "/orders", search=search)

    def set_notification_url(self, url: str) -> Any:
        return self._call("POST", "/set_notification_url", url=url)


def client() -> YesimClient:
    return YesimClient()
