"""The operator inbox at /admin/assistant/.

What this page has to get right is a short list, and every item on it is here:
a customer's private chat is only readable by staff; a customer who is waiting
is visible as waiting; an operator's reply reaches them and silences the AI; and
the whole thing can be left open all day without becoming a load generator.

That last one is why the query counts are asserted. A polling page whose cost
grows with the size of the queue is fine on the day it ships and a problem three
months later, and nothing about the page looks different when it happens.
"""
from __future__ import annotations

import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import AssistantConversation, AssistantMessage

User = get_user_model()
_C, _M = AssistantConversation, AssistantMessage


class InboxBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.operator = User.objects.create_superuser(
            email="operator@esimsterr.com", password="Pa55!operator")
        cls.customer = User.objects.create_user(
            email="traveller@example.com", password="Pa55!customer")

        cls.conv = _C.objects.create(user=cls.customer, intent_flags="connection,urgent")
        cls.first = _M.objects.create(conversation=cls.conv, role=_M.Role.USER,
                                      content="No data in Spain, see https://esimsterr.com/faq")
        cls.closed = _C.objects.create(user=cls.customer, status=_C.Status.CLOSED)

    def setUp(self):
        self.client.force_login(self.operator)

    def data(self, **params):
        return self.client.get(reverse("assistant_inbox_data"), params)

    def post(self, payload):
        return self.client.post(reverse("assistant_inbox_reply"),
                                data=json.dumps(payload),
                                content_type="application/json")


class AccessTests(InboxBase):
    def test_staff_can_open_the_console(self):
        self.assertEqual(self.client.get(reverse("assistant_inbox")).status_code, 200)

    def test_signed_out_visitors_are_sent_to_the_login(self):
        self.client.logout()
        for name in ("assistant_inbox", "assistant_inbox_data", "assistant_inbox_reply"):
            with self.subTest(view=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 302)

    def test_a_customer_cannot_read_other_peoples_chats(self):
        """These threads are private correspondence, not user-visible history."""
        self.client.force_login(self.customer)
        self.assertEqual(self.data().status_code, 302)
        self.assertEqual(self.post({"conv": str(self.conv.id), "message": "hi"}).status_code, 302)


class QueueTests(InboxBase):
    def test_the_queue_lists_open_conversations_and_flags_the_waiting_one(self):
        body = self.data().json()
        ids = [c["id"] for c in body["conversations"]]
        self.assertIn(str(self.conv.id), ids)
        self.assertNotIn(str(self.closed.id), ids, "a closed chat is not in the queue")
        row = body["conversations"][ids.index(str(self.conv.id))]
        self.assertTrue(row["waiting"], "the customer wrote last, so they are waiting")
        self.assertEqual(body["waiting"], 1)
        self.assertEqual(row["flags"], ["connection", "urgent"])

    def test_the_customer_stops_waiting_once_the_operator_answers(self):
        self.post({"conv": str(self.conv.id), "message": "On it — give me a minute."})
        self.assertEqual(self.data().json()["waiting"], 0)

    def test_an_unchanged_queue_answers_without_sending_it_again(self):
        cursor = self.data().json()["v"]
        again = self.data(v=cursor).json()
        self.assertTrue(again["unchanged"])
        self.assertNotIn("conversations", again)

    def test_a_new_message_moves_the_cursor(self):
        cursor = self.data().json()["v"]
        self.post({"conv": str(self.conv.id), "message": "Sorry about that."})
        self.assertNotEqual(self.data(v=cursor).json().get("v"), cursor)

    def test_the_queue_costs_the_same_however_many_conversations_there_are(self):
        """The guard against the obvious N+1: one query per conversation for its
        last message would be invisible here and fatal with a real queue."""
        self.data()  # warm the session/auth queries out of the measurement
        with self.assertNumQueries(4):
            self.data()
        for i in range(12):
            other = User.objects.create_user(email=f"c{i}@example.com", password="x")
            conv = _C.objects.create(user=other)
            _M.objects.create(conversation=conv, role=_M.Role.USER, content=f"hello {i}")
        with self.assertNumQueries(4):
            self.assertEqual(len(self.data().json()["conversations"]), 13)


class ThreadTests(InboxBase):
    def test_the_thread_returns_the_conversation_in_full(self):
        body = self.data(conv=str(self.conv.id)).json()
        self.assertEqual(body["user"], self.customer.email)
        self.assertFalse(body["incremental"])
        self.assertEqual([m["content"] for m in body["messages"]], [self.first.content])

    def test_an_unchanged_thread_answers_without_reading_the_messages(self):
        cursor = self.data(conv=str(self.conv.id)).json()["v"]
        with self.assertNumQueries(4):
            body = self.data(conv=str(self.conv.id), v=cursor).json()
        self.assertTrue(body["unchanged"])

    def test_after_returns_only_what_the_screen_does_not_have(self):
        first = self.data(conv=str(self.conv.id)).json()
        newest = first["messages"][-1]["created_at"]
        self.post({"conv": str(self.conv.id), "message": "Try toggling data roaming."})
        body = self.data(conv=str(self.conv.id), after=newest).json()
        self.assertTrue(body["incremental"])
        self.assertEqual([m["content"] for m in body["messages"]],
                         ["Try toggling data roaming."])

    def test_taking_over_changes_the_cursor_even_with_no_new_message(self):
        """The other pane has to notice a takeover made in another tab."""
        cursor = self.data(conv=str(self.conv.id)).json()["v"]
        self.post({"conv": str(self.conv.id), "action": "take"})
        self.assertNotEqual(self.data(conv=str(self.conv.id), v=cursor).json().get("v"), cursor)

    def test_a_missing_conversation_is_a_404_not_a_crash(self):
        self.assertEqual(
            self.data(conv="00000000-0000-0000-0000-000000000000").status_code, 404)


class TakeoverTests(InboxBase):
    def test_replying_silences_the_ai_and_badges_the_customer(self):
        self.post({"conv": str(self.conv.id), "message": "Hi, this is Ekin from support."})
        self.conv.refresh_from_db()
        self.assertTrue(self.conv.owner_joined, "the AI must not answer over a human")
        self.assertEqual(self.conv.user_unread, 1, "the widget needs a badge to show")
        last = self.conv.messages.last()
        self.assertEqual(last.role, _M.Role.OWNER)

    def test_taking_over_without_typing_stops_the_ai_immediately(self):
        """Read the thread first, answer second — without the AI replying in the
        gap and contradicting whatever the operator is about to say."""
        self.post({"conv": str(self.conv.id), "action": "take"})
        self.conv.refresh_from_db()
        self.assertTrue(self.conv.owner_joined)
        self.assertEqual(self.conv.messages.count(), 1, "no message is invented")

    def test_handing_back_tells_the_customer_the_ai_is_answering_again(self):
        self.post({"conv": str(self.conv.id), "message": "All sorted?"})
        self.post({"conv": str(self.conv.id), "action": "release"})
        self.conv.refresh_from_db()
        self.assertFalse(self.conv.owner_joined)
        self.assertEqual(self.conv.status, _C.Status.OPEN)
        self.assertEqual(self.conv.messages.last().role, _M.Role.ASSISTANT)
        self.assertTrue(self.conv.timeout_notified,
                        "a person did turn up, so never apologise for nobody being there")

    def test_closing_takes_it_out_of_the_queue(self):
        self.post({"conv": str(self.conv.id), "action": "close"})
        self.conv.refresh_from_db()
        self.assertEqual(self.conv.status, _C.Status.CLOSED)
        self.assertNotIn(str(self.conv.id),
                         [c["id"] for c in self.data().json()["conversations"]])

    def test_an_empty_reply_is_refused(self):
        self.assertEqual(self.post({"conv": str(self.conv.id), "message": "   "}).status_code, 400)
        self.assertEqual(self.conv.messages.count(), 1)

    def test_malformed_json_is_refused(self):
        response = self.client.post(reverse("assistant_inbox_reply"),
                                    data="not json", content_type="application/json")
        self.assertEqual(response.status_code, 400)
