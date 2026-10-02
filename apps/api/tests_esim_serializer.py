"""The eSIM payload's numbers have to arrive as numbers.

The app declares the megabyte fields as integers. They are DecimalField on the
model, and DRF renders a Decimal as a quoted string unless told otherwise, so
the API sent `"3072.00"` where a number was expected. kotlinx.serialization
refuses that at the byte it meets it and abandons the whole document: the eSIM
list did not degrade, it vanished, and the screen read "unexpected json token at
468" instead of showing anybody their eSIMs.

Worth a test rather than a comment because nothing on this side notices. The
serializer is valid, the JSON is valid, the HTTP status is 200, and the only
place the mismatch exists is between a Python type and a Kotlin one.
"""
from __future__ import annotations

import json
from decimal import Decimal

from django.test import TestCase

from apps.api.serializers import EsimSerializer
from apps.orders.models import Esim

MB_FIELDS = ("data_package_mb", "data_used_mb", "data_left_mb")


class EsimPayloadTypeTests(TestCase):
    def test_megabytes_are_numbers_and_not_strings(self):
        esim = Esim.objects.create(
            iccid="8948010010084677458", plan_title="France 3 GB",
            data_package_mb=Decimal("3072.00"), data_used_mb=Decimal("0.00"),
            data_left_mb=Decimal("3072.00"),
        )
        row = EsimSerializer(esim).data
        for field in MB_FIELDS:
            with self.subTest(field=field):
                self.assertIsInstance(row[field], int, f"{field} must not be a string")

    def test_a_fractional_reading_still_serialises_as_a_number(self):
        # The provider reports usage to two places. Whole megabytes is what the
        # screens show; what matters here is that it does not become a string.
        esim = Esim.objects.create(
            iccid="8948010010084666444", plan_title="France 1 GB",
            data_package_mb=Decimal("1024.00"), data_used_mb=Decimal("123.45"),
            data_left_mb=Decimal("900.55"),
        )
        row = EsimSerializer(esim).data
        self.assertEqual(row["data_used_mb"], 123)
        self.assertEqual(row["data_left_mb"], 900)

    def test_an_esim_with_no_usage_yet_keeps_its_nulls(self):
        # A released profile has no plan attached, and null is not zero: zero
        # would draw a full bar on a line that has no allowance at all.
        esim = Esim.objects.create(iccid="8948010010084600000")
        row = EsimSerializer(esim).data
        for field in MB_FIELDS:
            with self.subTest(field=field):
                self.assertIsNone(row[field])

    def test_the_whole_payload_round_trips_as_json(self):
        # The parser that broke read the document end to end, so the test does
        # too rather than inspecting fields it already knows about.
        Esim.objects.create(
            iccid="8948010010084677458", plan_title="France 3 GB",
            data_package_mb=Decimal("3072.00"), data_used_mb=Decimal("0.00"),
            data_left_mb=Decimal("3072.00"),
        )
        rows = json.loads(json.dumps(EsimSerializer(Esim.objects.all(), many=True).data))
        self.assertEqual(len(rows), 1)
        for field in MB_FIELDS:
            self.assertNotIsInstance(rows[0][field], str)
