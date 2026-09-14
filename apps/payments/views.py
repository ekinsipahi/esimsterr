"""Public webhooks: Stripe, NOWPayments IPN, Yesim notifications, cron trigger."""
from __future__ import annotations

import json
import logging

from django.conf import settings
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.orders.models import Esim, WebhookEvent
from apps.orders.services import apply_sim_info

from . import nowpayments, services, stripe_client

log = logging.getLogger(__name__)

# Event types the subscriptions app owns. Everything else falls through to the
# one-off payment path.
SUBSCRIPTION_EVENTS = {
    "checkout.session.completed",
    # A delayed payment method (some bank redirects) settles after the session
    # closes; without this the first cycle would never provision.
    "checkout.session.async_payment_succeeded",
    "invoice.paid",
    "invoice.payment_succeeded",
    "invoice.payment_failed",
    "customer.subscription.created",
    "customer.subscription.updated",
    "customer.subscription.deleted",
    "customer.subscription.paused",
    "customer.subscription.resumed",
}


@csrf_exempt
@require_POST
def stripe_webhook(request):
    sig = request.headers.get("Stripe-Signature", "")
    try:
        event = stripe_client.construct_event(request.body, sig)
    except stripe_client.StripeError:
        log.exception("Stripe webhook not configured")
        return HttpResponse("not configured", status=500)
    except Exception:  # noqa: BLE001 — bad signature / parse error
        log.warning("Rejected Stripe webhook: bad signature")
        return HttpResponseForbidden("invalid signature")

    # construct_event hands back Stripe's own object types, and in stripe-python
    # v15 those are NOT dicts: calling .get() on one raises AttributeError, which
    # would turn every real webhook into a 500 and make Stripe retry for ever.
    # Flatten once here so everything downstream handles plain data.
    event = event.to_dict() if hasattr(event, "to_dict") else dict(event)
    etype = event["type"]

    # Subscriptions own their whole lifecycle, including the checkout that starts
    # them. Routing on session mode keeps one-off and recurring payments from
    # settling each other's orders.
    if etype in SUBSCRIPTION_EVENTS:
        obj = event["data"]["object"]
        if etype.startswith("checkout.session") and obj.get("mode") != "subscription":
            pass  # a one-off checkout, handled below
        else:
            try:
                from apps.subscriptions.services import handle_stripe_event

                handle_stripe_event(event)
            except Exception:  # noqa: BLE001
                log.exception("Stripe subscription event failed: %s", etype)
                return HttpResponse("error", status=500)
            return JsonResponse({"received": True})

    # In-app purchases have no Checkout session at all: PaymentSheet drives a
    # PaymentIntent straight from the device, so this is the only event that
    # ever tells us the money arrived.
    if etype in ("payment_intent.succeeded", "payment_intent.payment_failed"):
        intent = event["data"]["object"]
        reference = (intent.get("metadata") or {}).get("reference", "")
        try:
            services.settle_stripe_intent(intent, reference, failed=etype.endswith("failed"))
        except Exception:  # noqa: BLE001
            log.exception("Stripe intent settlement failed")
            return HttpResponse("error", status=500)
        return JsonResponse({"received": True})

    if etype in ("checkout.session.completed", "checkout.session.async_payment_succeeded"):
        session = event["data"]["object"]
        if session.get("mode") == "subscription":
            return JsonResponse({"received": True})
        if session.get("payment_status") in ("paid", "no_payment_required"):
            try:
                services.settle_stripe_session(session)
            except Exception:  # noqa: BLE001
                log.exception("Stripe settlement failed")
                return HttpResponse("error", status=500)
    return JsonResponse({"received": True})


@csrf_exempt
@require_POST
def nowpayments_ipn(request):
    sig = request.headers.get("x-nowpayments-sig", "")
    if not nowpayments.verify_ipn_signature(request.body, sig):
        log.warning("Rejected NOWPayments IPN: bad signature")
        return HttpResponseForbidden("invalid signature")
    try:
        payload = json.loads(request.body.decode())
    except ValueError:
        return HttpResponse("bad json", status=400)
    try:
        services.process_nowpayments_ipn(payload)
    except Exception:  # noqa: BLE001
        log.exception("NOWPayments IPN processing failed")
        return HttpResponse("error", status=500)
    return JsonResponse({"status": "ok"})


@csrf_exempt
@require_POST
def yesim_webhook(request, secret):
    """Provider notifications: EsimStatus, PackageUsage, EsimExpirationWarning, EsimExpired.

    Authenticated by the unguessable secret in the path (the provider only lets us
    register a plain URL — there is no signature scheme to verify)."""
    if not settings.YESIM_WEBHOOK_SECRET or secret != settings.YESIM_WEBHOOK_SECRET:
        return HttpResponseForbidden("forbidden")
    try:
        payload = json.loads(request.body.decode() or "{}")
    except ValueError:
        return HttpResponse("bad json", status=400)

    event = WebhookEvent.objects.create(
        source="yesim",
        event_type=str(payload.get("type") or "")[:40],
        iccid=str(payload.get("iccid") or "")[:32],
        payload=payload,
    )
    try:
        _apply_yesim_event(payload)
        event.processed = True
    except Exception as e:  # noqa: BLE001
        event.error = str(e)[:2000]
        log.exception("Yesim webhook processing failed")
    event.save(update_fields=["processed", "error"])
    return JsonResponse({"status": "ok"})


def _apply_yesim_event(payload: dict):
    iccid = str(payload.get("iccid") or "")
    if not iccid:
        return
    esim = Esim.objects.filter(iccid=iccid).first()
    if esim is None:
        return
    etype = payload.get("type")
    if etype == "EsimStatus" and payload.get("status_qr"):
        esim.status_qr = payload["status_qr"]
        esim.save(update_fields=["status_qr", "updated_at"])
        return
    # Usage / expiry events carry no numbers we can trust in full — pull fresh state.
    from apps.providers.yesim import YesimError, client
    try:
        apply_sim_info(esim, client().sim_info(iccid))
    except YesimError as e:
        log.warning("sim_info after webhook failed for %s: %s", iccid, e)


@csrf_exempt
def cron(request, task):
    """HTTP-triggered maintenance (cron-job.org / Render cron).

    /webhooks/cron/<task>/?token=CRON_SECRET  — tasks: sync-usage, retry-orders, sync-plans (also refreshes Stripe prices)
    """
    token = request.GET.get("token") or request.headers.get("X-Cron-Token", "")
    if not settings.CRON_SECRET or token != settings.CRON_SECRET:
        return HttpResponseForbidden("forbidden")

    if task == "retry-orders":
        from apps.orders.services import retry_failed
        ok, failed = retry_failed()
        return JsonResponse({"task": task, "provisioned": ok, "failed": failed})

    if task == "sync-usage":
        from django.core.management import call_command
        call_command("sync_usage")
        return JsonResponse({"task": task, "status": "ok"})

    if task == "sync-plans":
        from django.core.management import call_command
        call_command("sync_plans", "--no-devices")
        # A new unlimited destination needs its Stripe price to exist before
        # somebody tries to subscribe to it. Leaving that to the first customer
        # is how a broken subscribe path went unnoticed for days.
        call_command("sync_stripe_prices")
        return JsonResponse({"task": task, "status": "ok"})

    if task == "sentry-check":
        # Deliberate crash, used to prove error reporting still works after a
        # deploy. It sits behind the cron token rather than on a public URL so
        # nobody can fill the error budget from outside, and it is worth keeping:
        # a monitoring pipeline that is never exercised is a monitoring pipeline
        # that is quietly broken.
        raise RuntimeError(
            "Sentry reachability check from /webhooks/cron/sentry-check/. "
            "This exception is raised on purpose and can be resolved."
        )

    if task == "purge-fingerprints":
        # Enforces the retention window the privacy policy publishes.
        from django.core.management import call_command
        call_command("purge_fingerprints")
        return JsonResponse({"task": task, "status": "ok"})

    return JsonResponse({"error": "unknown task"}, status=404)
